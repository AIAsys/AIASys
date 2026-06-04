#!/usr/bin/env python3
"""Shared helpers for JSON Canvas scripts."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

NODE_TYPES = {"text", "file", "link", "group"}
SIDES = {"top", "right", "bottom", "left"}
EDGE_ENDS = {"none", "arrow"}


def get_workspace_root() -> Path:
    ws_root = os.environ.get("AIASYS_WORKSPACE_ROOT", "")
    if ws_root:
        return Path(ws_root).resolve()
    raise RuntimeError("无法确定工作区根目录")


def resolve_file(raw: str, workspace_root: Path) -> Path:
    p = Path(raw)
    if p.is_absolute():
        rel = (
            Path(*p.parts[2:])
            if str(p) == "/workspace" or str(p).startswith("/workspace/")
            else p
        )
    else:
        rel = p
    host = (workspace_root / rel).resolve()
    try:
        host.relative_to(workspace_root)
    except ValueError as exc:
        raise PermissionError(f"路径超出工作区: {raw}") from exc
    return host


def load_canvas(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"nodes": [], "edges": []}


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def next_grid_position(
    canvas: dict[str, Any],
    width: float = 280,
    height: float = 140,
) -> tuple[float, float]:
    nodes = [node for node in canvas.get("nodes", []) if isinstance(node, dict)]
    if not nodes:
        return 0, 0

    gap_x = max(72, width * 0.35)
    gap_y = max(56, height * 0.35)
    columns = 4
    index = len(nodes)
    min_x = min(float(node.get("x", 0)) for node in nodes)
    min_y = min(float(node.get("y", 0)) for node in nodes)
    row = index // columns
    column = index % columns
    return min_x + column * (width + gap_x), min_y + row * (height + gap_y)


def validate_canvas(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("canvas JSON 必须是对象")
    nodes = data.get("nodes")
    edges = data.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("canvas JSON 必须包含 nodes 和 edges 数组")

    warnings: list[str] = []
    custom = data.get("custom")
    if custom is not None and not isinstance(custom, dict):
        warnings.append("顶层 custom 不是对象，AIASys 不会解读该字段")

    node_ids: set[str] = set()
    edge_ids: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValueError(f"nodes[{index}] 必须是对象")
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            raise ValueError(f"nodes[{index}] 缺少 id")
        if node_id in node_ids:
            raise ValueError(f"重复节点 id: {node_id}")
        node_ids.add(node_id)
        node_type = node.get("type")
        if node_type not in NODE_TYPES:
            raise ValueError(f"节点 {node_id} 的 type 不受支持: {node_type}")
        for key in ("x", "y", "width", "height"):
            if key not in node or not isinstance(node[key], (int, float)):
                raise ValueError(f"节点 {node_id} 缺少数值字段 {key}")
        for key in ("text", "file", "url", "label", "subpath", "color"):
            if key in node and not isinstance(node[key], (str, int, float)):
                raise ValueError(f"节点 {node_id} 的 {key} 字段类型不受支持")
        if node_type == "file" and "file" not in node:
            warnings.append(f"file 节点 {node_id} 缺少 file 字段")
        if node_type == "link" and "url" not in node:
            warnings.append(f"link 节点 {node_id} 缺少 url 字段")
        if "custom" in node and not isinstance(node["custom"], dict):
            warnings.append(f"节点 {node_id} 的 custom 不是对象")
        elif isinstance(node.get("custom"), dict):
            aiasys = node["custom"].get("aiasys")
            if aiasys is not None and not isinstance(aiasys, dict):
                warnings.append(f"节点 {node_id} 的 custom.aiasys 不是对象")

    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            raise ValueError(f"edges[{index}] 必须是对象")
        edge_id = str(edge.get("id") or "").strip()
        if not edge_id:
            raise ValueError(f"edges[{index}] 缺少 id")
        if edge_id in edge_ids:
            raise ValueError(f"重复边 id: {edge_id}")
        edge_ids.add(edge_id)
        from_node = str(edge.get("fromNode") or "").strip()
        to_node = str(edge.get("toNode") or "").strip()
        if from_node not in node_ids:
            raise ValueError(f"边 {edge_id} 的 fromNode 不存在: {from_node}")
        if to_node not in node_ids:
            raise ValueError(f"边 {edge_id} 的 toNode 不存在: {to_node}")
        for key in ("fromSide", "toSide"):
            if key in edge and edge[key] not in SIDES:
                raise ValueError(f"边 {edge_id} 的 {key} 不受支持: {edge[key]}")
        for key in ("fromEnd", "toEnd"):
            if key in edge and edge[key] not in EDGE_ENDS:
                raise ValueError(f"边 {edge_id} 的 {key} 不受支持: {edge[key]}")
        for key in ("label", "color"):
            if key in edge and not isinstance(edge[key], (str, int, float)):
                raise ValueError(f"边 {edge_id} 的 {key} 字段类型不受支持")
        if "custom" in edge and not isinstance(edge["custom"], dict):
            warnings.append(f"边 {edge_id} 的 custom 不是对象")
        elif isinstance(edge.get("custom"), dict):
            aiasys = edge["custom"].get("aiasys")
            if aiasys is not None and not isinstance(aiasys, dict):
                warnings.append(f"边 {edge_id} 的 custom.aiasys 不是对象")

    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "warnings": warnings,
    }


def save_canvas(path: Path, data: dict[str, Any]) -> None:
    validate_canvas(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
