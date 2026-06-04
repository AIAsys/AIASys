from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

from filelock import FileLock

from app.models.canvas import CanvasBatchOperation, CanvasEdge, CanvasFile, CanvasNode
from app.services.file_history import file_history_service


def _new_id(prefix: str = "node") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _resolve_canvas_file_path(workspace_root: Path, relative_path: str) -> Path:
    normalized = str(relative_path or "").replace("\\", "/").strip()
    if not normalized.endswith(".canvas"):
        raise ValueError("Canvas 文件必须使用 .canvas 后缀")
    candidate = Path(normalized)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Canvas 文件路径包含非法路径片段")
    root = workspace_root.resolve()
    file_path = (root / candidate).resolve()
    if not (file_path == root or file_path.is_relative_to(root)):
        raise ValueError("Canvas 文件路径超出工作区范围")
    return file_path


def _normalize_canvas(canvas: CanvasFile) -> CanvasFile:
    node_ids: set[str] = set()
    edge_ids: set[str] = set()
    nodes: list[CanvasNode] = []
    edges: list[CanvasEdge] = []

    for node in canvas.nodes:
        if node.id in node_ids:
            continue
        node_ids.add(node.id)
        nodes.append(node)

    for edge in canvas.edges:
        if (
            edge.id in edge_ids
            or edge.fromNode not in node_ids
            or edge.toNode not in node_ids
            or edge.fromNode == edge.toNode
        ):
            continue
        edge_ids.add(edge.id)
        edges.append(edge)

    canvas.nodes = nodes
    canvas.edges = edges
    return canvas


class CanvasFileService:
    """.canvas 文件读写服务。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, tuple[Path, str, CanvasFile, float]] = {}
        self._timer: threading.Timer | None = None
        # 读缓存：file_path -> (mtime, CanvasFile)
        self._read_cache: dict[str, tuple[float, CanvasFile]] = {}
        # 写序列化缓存：file_path -> (canvas_hash, json_string)
        self._write_json_cache: dict[str, tuple[int, str]] = {}

    def _read_from_disk(self, file_path: Path) -> CanvasFile:
        """从磁盘读取并缓存。调用方必须确保并发安全。"""
        file_path_str = str(file_path)
        with self._lock:
            cached = self._read_cache.get(file_path_str)
            if cached and cached[0] == file_path.stat().st_mtime:
                return cached[1]

        content = file_path.read_text(encoding="utf-8")
        if not content.strip():
            canvas = CanvasFile()
        else:
            data = json.loads(content)
            canvas = _normalize_canvas(CanvasFile.model_validate(data))

        with self._lock:
            # 双检：读取期间可能有其他线程更新了缓存
            cached = self._read_cache.get(file_path_str)
            if cached and cached[0] == file_path.stat().st_mtime:
                return cached[1]
            self._read_cache[file_path_str] = (file_path.stat().st_mtime, canvas)
        return canvas

    def read_canvas(self, workspace_root: Path, relative_path: str) -> CanvasFile:
        file_path = _resolve_canvas_file_path(workspace_root, relative_path)
        file_path_str = str(file_path)
        with self._lock:
            if file_path_str in self._pending:
                return self._pending[file_path_str][2]
        if not file_path.exists():
            raise FileNotFoundError(f"Canvas 文件不存在: {relative_path}")
        return self._read_from_disk(file_path)

    def _write_canvas_to_disk(
        self,
        workspace_root: Path,
        relative_path: str,
        canvas: CanvasFile,
    ) -> None:
        file_path = _resolve_canvas_file_path(workspace_root, relative_path)
        file_path_str = str(file_path)

        dumped = canvas.model_dump(mode="json", exclude_none=True)
        canvas_hash = hash(json.dumps(dumped, sort_keys=True, ensure_ascii=False))

        with self._lock:
            cached = self._write_json_cache.get(file_path_str)
            if cached and cached[0] == canvas_hash:
                json_str = cached[1]
            else:
                json_str = json.dumps(dumped, ensure_ascii=False)
                self._write_json_cache[file_path_str] = (canvas_hash, json_str)

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_history_service.record_file_before_change(
            workspace_root,
            relative_path,
            operation="before_update",
            source="canvas_service",
            source_detail="write_canvas",
        )
        tmp_path = file_path.with_suffix(".tmp")
        lock_path = str(tmp_path) + ".lock"
        with FileLock(lock_path):
            tmp_path.write_text(json_str, encoding="utf-8")
        tmp_path.replace(file_path)

        new_mtime = file_path.stat().st_mtime
        with self._lock:
            self._read_cache[file_path_str] = (new_mtime, canvas)

    def write_canvas(
        self,
        workspace_root: Path,
        relative_path: str,
        canvas: CanvasFile,
    ) -> CanvasFile:
        canvas = _normalize_canvas(canvas)
        file_path = _resolve_canvas_file_path(workspace_root, relative_path)
        file_path_str = str(file_path)
        with self._lock:
            existing = self._pending.get(file_path_str)
            if existing and existing[2] is canvas:
                # 同一对象原地修改，仅更新时间戳
                self._pending[file_path_str] = (
                    workspace_root,
                    relative_path,
                    canvas,
                    time.time(),
                )
                return canvas

            self._pending[file_path_str] = (
                workspace_root,
                relative_path,
                canvas,
                time.time(),
            )
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(0.1, self._flush_pending)
            self._timer.daemon = True
            self._timer.start()
        # 同步落盘，保证调用方可以立即读取
        self._flush_file_if_pending(file_path_str)
        return canvas

    def _flush_pending(self) -> None:
        with self._lock:
            pending = dict(self._pending)
            self._pending.clear()
            self._timer = None
        for workspace_root, relative_path, canvas, _ in pending.values():
            self._write_canvas_to_disk(workspace_root, relative_path, canvas)

    def _flush_file_if_pending(self, file_path_str: str) -> None:
        with self._lock:
            if file_path_str not in self._pending:
                return
            workspace_root, relative_path, canvas, _ = self._pending.pop(file_path_str)
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        self._write_canvas_to_disk(workspace_root, relative_path, canvas)

    def _read_or_create(self, workspace_root: Path, relative_path: str) -> CanvasFile:
        """读取 canvas，不存在时返回空对象（用于写入操作）。优先返回 pending 中的内存对象。"""
        file_path = _resolve_canvas_file_path(workspace_root, relative_path)
        file_path_str = str(file_path)
        with self._lock:
            if file_path_str in self._pending:
                return self._pending[file_path_str][2]
        if not file_path.exists():
            return CanvasFile()
        return self._read_from_disk(file_path)

    # ------------------------------------------------------------------
    # 批量节点接口
    # ------------------------------------------------------------------

    def add_nodes(
        self,
        workspace_root: Path,
        relative_path: str,
        nodes: list[CanvasNode],
    ) -> CanvasFile:
        canvas = self._read_or_create(workspace_root, relative_path)
        existing_ids = {n.id for n in canvas.nodes}
        for node in nodes:
            if not node.id:
                node.id = _new_id("node")
            if node.id in existing_ids:
                continue
            canvas.nodes.append(node)
            existing_ids.add(node.id)
        self.write_canvas(workspace_root, relative_path, canvas)
        return canvas

    def add_node(
        self,
        workspace_root: Path,
        relative_path: str,
        node: CanvasNode,
    ) -> CanvasFile:
        return self.add_nodes(workspace_root, relative_path, [node])

    def update_nodes(
        self,
        workspace_root: Path,
        relative_path: str,
        node_map: dict[str, CanvasNode],
    ) -> CanvasFile:
        canvas = self._read_or_create(workspace_root, relative_path)
        for i, n in enumerate(canvas.nodes):
            if n.id in node_map:
                updated = node_map[n.id]
                updated.id = n.id
                canvas.nodes[i] = updated
        self.write_canvas(workspace_root, relative_path, canvas)
        return canvas

    def update_node(
        self,
        workspace_root: Path,
        relative_path: str,
        node_id: str,
        node: CanvasNode,
    ) -> CanvasFile:
        return self.update_nodes(workspace_root, relative_path, {node_id: node})

    def remove_nodes(
        self,
        workspace_root: Path,
        relative_path: str,
        node_ids: list[str],
    ) -> CanvasFile:
        canvas = self._read_or_create(workspace_root, relative_path)
        remove_set = set(node_ids)
        canvas.nodes = [n for n in canvas.nodes if n.id not in remove_set]
        canvas.edges = [
            e for e in canvas.edges if e.fromNode not in remove_set and e.toNode not in remove_set
        ]
        self.write_canvas(workspace_root, relative_path, canvas)
        return canvas

    def remove_node(
        self,
        workspace_root: Path,
        relative_path: str,
        node_id: str,
    ) -> CanvasFile:
        return self.remove_nodes(workspace_root, relative_path, [node_id])

    # ------------------------------------------------------------------
    # 批量边接口
    # ------------------------------------------------------------------

    def add_edges(
        self,
        workspace_root: Path,
        relative_path: str,
        edges: list[CanvasEdge],
    ) -> CanvasFile:
        canvas = self._read_or_create(workspace_root, relative_path)
        node_ids = {node.id for node in canvas.nodes}
        existing_edge_keys = {(e.fromNode, e.toNode) for e in canvas.edges}
        existing_edge_ids = {e.id for e in canvas.edges}

        for edge in edges:
            if not edge.id:
                edge.id = _new_id("edge")
            if (
                edge.id in existing_edge_ids
                or (edge.fromNode, edge.toNode) in existing_edge_keys
                or edge.fromNode not in node_ids
                or edge.toNode not in node_ids
                or edge.fromNode == edge.toNode
            ):
                continue
            canvas.edges.append(edge)
            existing_edge_ids.add(edge.id)
            existing_edge_keys.add((edge.fromNode, edge.toNode))

        self.write_canvas(workspace_root, relative_path, canvas)
        return canvas

    def add_edge(
        self,
        workspace_root: Path,
        relative_path: str,
        edge: CanvasEdge,
    ) -> CanvasFile:
        return self.add_edges(workspace_root, relative_path, [edge])

    def update_edges(
        self,
        workspace_root: Path,
        relative_path: str,
        edge_map: dict[str, CanvasEdge],
    ) -> CanvasFile:
        canvas = self._read_or_create(workspace_root, relative_path)
        for i, e in enumerate(canvas.edges):
            if e.id in edge_map:
                updated = edge_map[e.id]
                updated.id = e.id
                canvas.edges[i] = updated
        self.write_canvas(workspace_root, relative_path, canvas)
        return canvas

    def update_edge(
        self,
        workspace_root: Path,
        relative_path: str,
        edge_id: str,
        edge: CanvasEdge,
    ) -> CanvasFile:
        return self.update_edges(workspace_root, relative_path, {edge_id: edge})

    def remove_edges(
        self,
        workspace_root: Path,
        relative_path: str,
        edge_ids: list[str],
    ) -> CanvasFile:
        canvas = self._read_or_create(workspace_root, relative_path)
        remove_set = set(edge_ids)
        canvas.edges = [e for e in canvas.edges if e.id not in remove_set]
        self.write_canvas(workspace_root, relative_path, canvas)
        return canvas

    def remove_edge(
        self,
        workspace_root: Path,
        relative_path: str,
        edge_id: str,
    ) -> CanvasFile:
        return self.remove_edges(workspace_root, relative_path, [edge_id])

    # ------------------------------------------------------------------
    # 通用批量操作（混合类型）
    # ------------------------------------------------------------------

    def batch_operations(
        self,
        workspace_root: Path,
        relative_path: str,
        operations: list[CanvasBatchOperation],
    ) -> CanvasFile:
        """批量执行节点和边的增删改操作，只读写一次文件。"""
        canvas = self._read_or_create(workspace_root, relative_path)

        for op in operations:
            if op.type == "add_node":
                node = op.node
                if node is None:
                    continue
                if not node.id:
                    node.id = _new_id("node")
                if not any(existing.id == node.id for existing in canvas.nodes):
                    canvas.nodes.append(node)

            elif op.type == "update_node":
                node = op.node
                target_id = op.node_id or (node.id if node else None)
                if node is None or target_id is None:
                    continue
                for i, n in enumerate(canvas.nodes):
                    if n.id == target_id:
                        node.id = target_id
                        canvas.nodes[i] = node
                        break

            elif op.type == "remove_node":
                target_id = op.node_id or (op.node.id if op.node else None)
                if target_id is None:
                    continue
                canvas.nodes = [n for n in canvas.nodes if n.id != target_id]
                canvas.edges = [
                    e for e in canvas.edges if e.fromNode != target_id and e.toNode != target_id
                ]

            elif op.type == "add_edge":
                edge = op.edge
                if edge is None:
                    continue
                if not edge.id:
                    edge.id = _new_id("edge")
                node_ids = {node.id for node in canvas.nodes}
                has_duplicate = any(
                    existing.id == edge.id
                    or (existing.fromNode == edge.fromNode and existing.toNode == edge.toNode)
                    for existing in canvas.edges
                )
                if (
                    not has_duplicate
                    and edge.fromNode in node_ids
                    and edge.toNode in node_ids
                    and edge.fromNode != edge.toNode
                ):
                    canvas.edges.append(edge)

            elif op.type == "update_edge":
                edge = op.edge
                target_id = op.edge_id or (edge.id if edge else None)
                if edge is None or target_id is None:
                    continue
                for i, e in enumerate(canvas.edges):
                    if e.id == target_id:
                        edge.id = target_id
                        canvas.edges[i] = edge
                        break

            elif op.type == "remove_edge":
                target_id = op.edge_id or (op.edge.id if op.edge else None)
                if target_id is None:
                    continue
                canvas.edges = [e for e in canvas.edges if e.id != target_id]

        self.write_canvas(workspace_root, relative_path, canvas)
        return canvas


_service: CanvasFileService | None = None


def get_canvas_file_service() -> CanvasFileService:
    global _service
    if _service is None:
        _service = CanvasFileService()
    return _service
