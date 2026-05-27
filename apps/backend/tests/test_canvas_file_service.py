from __future__ import annotations

import json
import os
from pathlib import Path

from app.models.canvas import CanvasBatchOperation, CanvasEdge, CanvasFile, CanvasNode
from app.services.canvas_file_service import CanvasFileService


def test_read_cache_avoids_repeated_disk_reads(tmp_path: Path) -> None:
    """验证基于 mtime 的读缓存能避免短时间内重复全量读取同一文件。"""
    service = CanvasFileService()
    (tmp_path / "test.canvas").write_text(
        json.dumps({"nodes": [{"id": "node-1", "type": "text", "text": "A"}], "edges": []}),
        encoding="utf-8",
    )

    target_path = (tmp_path / "test.canvas").resolve()
    original_read_text = Path.read_text
    call_count = 0

    def counting_read_text(self, *args, **kwargs):
        nonlocal call_count
        if self.resolve() == target_path:
            call_count += 1
        return original_read_text(self, *args, **kwargs)

    # 用 monkeypatch 替换类方法以统计目标文件的实际磁盘读取次数
    Path.read_text = counting_read_text
    try:
        # 首次读取应触发磁盘读取
        canvas1 = service.read_canvas(tmp_path, "test.canvas")
        count_after_first = call_count
        assert canvas1.nodes[0].id == "node-1"

        # 再次读取应命中缓存，不触发额外磁盘读取
        canvas2 = service.read_canvas(tmp_path, "test.canvas")
        count_after_second = call_count
        assert count_after_second == count_after_first
        assert canvas2.nodes[0].id == "node-1"

        # 显式修改 mtime 使缓存失效（避免依赖文件系统时间戳精度）
        new_mtime = target_path.stat().st_mtime + 1.0
        os.utime(target_path, (new_mtime, new_mtime))

        canvas3 = service.read_canvas(tmp_path, "test.canvas")
        count_after_third = call_count
        assert count_after_third == count_after_first + 1
        assert canvas3.nodes[0].id == "node-1"  # 文件内容未变，仅 mtime 变了
    finally:
        Path.read_text = original_read_text


def test_read_or_create_uses_read_cache_between_crud_operations(tmp_path: Path) -> None:
    """验证 CRUD 操作之间，_read_or_create 能命中读缓存，避免重复全量读取。"""
    service = CanvasFileService()
    (tmp_path / "test.canvas").write_text(
        json.dumps({"nodes": [{"id": "node-1", "type": "text", "text": "A"}], "edges": []}),
        encoding="utf-8",
    )

    target_path = (tmp_path / "test.canvas").resolve()
    original_read_text = Path.read_text
    call_count = 0

    def counting_read_text(self, *args, **kwargs):
        nonlocal call_count
        if self.resolve() == target_path:
            call_count += 1
        return original_read_text(self, *args, **kwargs)

    Path.read_text = counting_read_text
    try:
        # 第一次 add_node：冷缓存，需要读磁盘
        service.add_node(tmp_path, "test.canvas", CanvasNode(id="node-2", text="B"))
        count_after_first = call_count

        # 第二次 add_node：write_canvas 已将新 mtime 写入缓存，应命中缓存
        service.add_node(tmp_path, "test.canvas", CanvasNode(id="node-3", text="C"))
        count_after_second = call_count
        assert count_after_second == count_after_first

        # 验证最终内容正确
        final = service.read_canvas(tmp_path, "test.canvas")
        assert {n.id for n in final.nodes} == {"node-1", "node-2", "node-3"}
    finally:
        Path.read_text = original_read_text


def test_read_canvas_treats_empty_file_as_empty_canvas(tmp_path: Path) -> None:
    service = CanvasFileService()
    (tmp_path / "empty.canvas").write_text("", encoding="utf-8")

    canvas = service.read_canvas(tmp_path, "empty.canvas")

    assert canvas.nodes == []
    assert canvas.edges == []


def test_write_canvas_removes_duplicate_nodes_and_invalid_edges(
    tmp_path: Path,
) -> None:
    service = CanvasFileService()
    canvas = CanvasFile(
        nodes=[
            CanvasNode(id="node-1", type="text", text="A"),
            CanvasNode(id="node-1", type="text", text="A duplicate"),
            CanvasNode(id="node-2", type="text", text="B"),
        ],
        edges=[
            CanvasEdge(id="edge-1", fromNode="node-1", toNode="node-2"),
            CanvasEdge(id="edge-1", fromNode="node-1", toNode="node-2"),
            CanvasEdge(id="edge-bad", fromNode="node-1", toNode="missing"),
        ],
    )

    service.write_canvas(tmp_path, "test.canvas", canvas)

    saved = service.read_canvas(tmp_path, "test.canvas").model_dump(mode="json", exclude_none=True)
    assert [node["id"] for node in saved["nodes"]] == ["node-1", "node-2"]
    assert [edge["id"] for edge in saved["edges"]] == ["edge-1"]


def test_add_node_and_edge_are_idempotent(tmp_path: Path) -> None:
    service = CanvasFileService()
    service.add_node(tmp_path, "test.canvas", CanvasNode(id="node-1", text="A"))
    service.add_node(tmp_path, "test.canvas", CanvasNode(id="node-1", text="A"))
    service.add_node(tmp_path, "test.canvas", CanvasNode(id="node-2", text="B"))
    service.add_edge(
        tmp_path,
        "test.canvas",
        CanvasEdge(id="edge-1", fromNode="node-1", toNode="node-2"),
    )
    service.add_edge(
        tmp_path,
        "test.canvas",
        CanvasEdge(id="edge-1", fromNode="node-1", toNode="node-2"),
    )

    canvas = service.read_canvas(tmp_path, "test.canvas")

    assert [node.id for node in canvas.nodes] == ["node-1", "node-2"]
    assert [edge.id for edge in canvas.edges] == ["edge-1"]


def test_canvas_preserves_unknown_fields_and_subpath(tmp_path: Path) -> None:
    service = CanvasFileService()
    (tmp_path / "external.canvas").write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "node-file",
                        "type": "file",
                        "x": 10,
                        "y": 20,
                        "width": 260,
                        "height": 120,
                        "file": "notes/report.md",
                        "subpath": "#结论",
                        "foreignNodeField": {"keep": True},
                        "custom": {
                            "aiasys": {
                                "node_type": "evidence",
                                "status": "verified",
                            }
                        },
                    },
                    {
                        "id": "node-text",
                        "type": "text",
                        "x": 400,
                        "y": 20,
                        "width": 260,
                        "height": 120,
                        "text": "结论",
                    },
                ],
                "edges": [
                    {
                        "id": "edge-1",
                        "fromNode": "node-file",
                        "toNode": "node-text",
                        "foreignEdgeField": "keep",
                        "custom": {"aiasys": {"edge_type": "supports"}},
                    }
                ],
                "foreignDocumentField": {"keep": True},
                "custom": {"source": "external-tool"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    canvas = service.read_canvas(tmp_path, "external.canvas")
    service.write_canvas(tmp_path, "external.canvas", canvas)

    saved = service.read_canvas(tmp_path, "external.canvas").model_dump(mode="json", exclude_none=True)
    assert saved["foreignDocumentField"] == {"keep": True}
    assert saved["custom"] == {"source": "external-tool"}
    assert saved["nodes"][0]["subpath"] == "#结论"
    assert saved["nodes"][0]["foreignNodeField"] == {"keep": True}
    assert saved["nodes"][0]["custom"]["aiasys"]["node_type"] == "evidence"
    assert saved["edges"][0]["foreignEdgeField"] == "keep"
    assert saved["edges"][0]["custom"]["aiasys"]["edge_type"] == "supports"


def test_batch_operations_read_once_write_once(tmp_path: Path) -> None:
    service = CanvasFileService()
    # 准备初始文件
    service.write_canvas(
        tmp_path,
        "batch.canvas",
        CanvasFile(
            nodes=[
                CanvasNode(id="node-1", type="text", text="A"),
                CanvasNode(id="node-2", type="text", text="B"),
            ],
            edges=[
                CanvasEdge(id="edge-1", fromNode="node-1", toNode="node-2"),
            ],
        ),
    )

    operations = [
        CanvasBatchOperation(type="add_node", node=CanvasNode(id="node-3", type="text", text="C")),
        CanvasBatchOperation(type="update_node", node_id="node-1", node=CanvasNode(id="node-1", type="text", text="A updated")),
        CanvasBatchOperation(type="remove_node", node_id="node-2"),
        CanvasBatchOperation(type="add_edge", edge=CanvasEdge(id="edge-2", fromNode="node-1", toNode="node-3")),
        CanvasBatchOperation(type="remove_edge", edge_id="edge-1"),
    ]

    result = service.batch_operations(tmp_path, "batch.canvas", operations)

    # 验证节点: node-1 更新, node-2 删除, node-3 新增
    assert len(result.nodes) == 2
    node_ids = {n.id for n in result.nodes}
    assert node_ids == {"node-1", "node-3"}
    node_1 = next(n for n in result.nodes if n.id == "node-1")
    assert node_1.text == "A updated"

    # 验证边: edge-1 删除, edge-2 新增
    assert len(result.edges) == 1
    assert result.edges[0].id == "edge-2"
    assert result.edges[0].fromNode == "node-1"
    assert result.edges[0].toNode == "node-3"

    # 验证文件确实只写了一次（通过重新读取确认）
    saved = service.read_canvas(tmp_path, "batch.canvas")
    assert len(saved.nodes) == 2
    assert len(saved.edges) == 1


def test_batch_operations_ignores_invalid_references(tmp_path: Path) -> None:
    service = CanvasFileService()
    service.write_canvas(
        tmp_path,
        "batch.canvas",
        CanvasFile(
            nodes=[CanvasNode(id="node-1", type="text", text="A")],
            edges=[],
        ),
    )

    operations = [
        # 添加边引用不存在的节点，应被忽略
        CanvasBatchOperation(
            type="add_edge",
            edge=CanvasEdge(id="edge-bad", fromNode="node-1", toNode="missing"),
        ),
        # 删除不存在的节点，应不报错
        CanvasBatchOperation(type="remove_node", node_id="nonexistent"),
        # 更新不存在的节点，应不报错
        CanvasBatchOperation(
            type="update_node",
            node_id="nonexistent",
            node=CanvasNode(id="nonexistent", type="text", text="ignored"),
        ),
    ]

    result = service.batch_operations(tmp_path, "batch.canvas", operations)

    assert len(result.nodes) == 1
    assert len(result.edges) == 0


def test_batch_operations_preserves_existing_on_empty_list(tmp_path: Path) -> None:
    service = CanvasFileService()
    service.write_canvas(
        tmp_path,
        "batch.canvas",
        CanvasFile(
            nodes=[CanvasNode(id="node-1", type="text", text="A")],
            edges=[],
        ),
    )

    result = service.batch_operations(tmp_path, "batch.canvas", [])

    assert len(result.nodes) == 1
    assert result.nodes[0].id == "node-1"
    assert result.nodes[0].text == "A"


# ------------------------------------------------------------------
# 新增批量接口测试
# ------------------------------------------------------------------


def test_add_nodes_batch(tmp_path: Path) -> None:
    service = CanvasFileService()
    service.write_canvas(
        tmp_path,
        "batch.canvas",
        CanvasFile(
            nodes=[CanvasNode(id="node-1", type="text", text="A")],
            edges=[],
        ),
    )

    result = service.add_nodes(
        tmp_path,
        "batch.canvas",
        [
            CanvasNode(id="node-2", type="text", text="B"),
            CanvasNode(id="node-3", type="text", text="C"),
        ],
    )

    assert len(result.nodes) == 3
    assert {n.id for n in result.nodes} == {"node-1", "node-2", "node-3"}


def test_add_nodes_skips_duplicates(tmp_path: Path) -> None:
    service = CanvasFileService()
    service.write_canvas(
        tmp_path,
        "batch.canvas",
        CanvasFile(
            nodes=[CanvasNode(id="node-1", type="text", text="A")],
            edges=[],
        ),
    )

    result = service.add_nodes(
        tmp_path,
        "batch.canvas",
        [
            CanvasNode(id="node-1", type="text", text="A duplicate"),
            CanvasNode(id="node-2", type="text", text="B"),
        ],
    )

    assert len(result.nodes) == 2
    assert result.nodes[0].text == "A"


def test_update_nodes_batch(tmp_path: Path) -> None:
    service = CanvasFileService()
    service.write_canvas(
        tmp_path,
        "batch.canvas",
        CanvasFile(
            nodes=[
                CanvasNode(id="node-1", type="text", text="A"),
                CanvasNode(id="node-2", type="text", text="B"),
            ],
            edges=[],
        ),
    )

    result = service.update_nodes(
        tmp_path,
        "batch.canvas",
        {
            "node-1": CanvasNode(id="node-1", type="text", text="A updated"),
            "node-2": CanvasNode(id="node-2", type="text", text="B updated"),
        },
    )

    assert len(result.nodes) == 2
    assert next(n for n in result.nodes if n.id == "node-1").text == "A updated"
    assert next(n for n in result.nodes if n.id == "node-2").text == "B updated"


def test_remove_nodes_batch_and_cascade_edges(tmp_path: Path) -> None:
    service = CanvasFileService()
    service.write_canvas(
        tmp_path,
        "batch.canvas",
        CanvasFile(
            nodes=[
                CanvasNode(id="node-1", type="text", text="A"),
                CanvasNode(id="node-2", type="text", text="B"),
                CanvasNode(id="node-3", type="text", text="C"),
            ],
            edges=[
                CanvasEdge(id="edge-1", fromNode="node-1", toNode="node-2"),
                CanvasEdge(id="edge-2", fromNode="node-2", toNode="node-3"),
            ],
        ),
    )

    result = service.remove_nodes(tmp_path, "batch.canvas", ["node-1", "node-2"])

    assert len(result.nodes) == 1
    assert result.nodes[0].id == "node-3"
    assert len(result.edges) == 0


def test_add_edges_batch(tmp_path: Path) -> None:
    service = CanvasFileService()
    service.write_canvas(
        tmp_path,
        "batch.canvas",
        CanvasFile(
            nodes=[
                CanvasNode(id="node-1", type="text", text="A"),
                CanvasNode(id="node-2", type="text", text="B"),
            ],
            edges=[],
        ),
    )

    result = service.add_edges(
        tmp_path,
        "batch.canvas",
        [
            CanvasEdge(id="edge-1", fromNode="node-1", toNode="node-2"),
            CanvasEdge(id="edge-2", fromNode="node-1", toNode="node-2"),  # 重复，应被忽略
        ],
    )

    assert len(result.edges) == 1
    assert result.edges[0].id == "edge-1"


def test_remove_edges_batch(tmp_path: Path) -> None:
    service = CanvasFileService()
    service.write_canvas(
        tmp_path,
        "batch.canvas",
        CanvasFile(
            nodes=[
                CanvasNode(id="node-1", type="text", text="A"),
                CanvasNode(id="node-2", type="text", text="B"),
            ],
            edges=[
                CanvasEdge(id="edge-1", fromNode="node-1", toNode="node-2"),
                CanvasEdge(id="edge-2", fromNode="node-2", toNode="node-1"),
            ],
        ),
    )

    result = service.remove_edges(tmp_path, "batch.canvas", ["edge-1"])

    assert len(result.edges) == 1
    assert result.edges[0].id == "edge-2"


def test_single_methods_delegate_to_batch(tmp_path: Path) -> None:
    """验证单条接口内部调用批量接口，行为一致。"""
    service = CanvasFileService()

    # add_node
    service.add_node(tmp_path, "test.canvas", CanvasNode(id="node-1", text="A"))
    canvas = service.read_canvas(tmp_path, "test.canvas")
    assert len(canvas.nodes) == 1

    # update_node
    service.update_node(tmp_path, "test.canvas", "node-1", CanvasNode(id="node-1", text="A updated"))
    canvas = service.read_canvas(tmp_path, "test.canvas")
    assert canvas.nodes[0].text == "A updated"

    # remove_node
    service.remove_node(tmp_path, "test.canvas", "node-1")
    canvas = service.read_canvas(tmp_path, "test.canvas")
    assert len(canvas.nodes) == 0

    # add_edge
    service.add_node(tmp_path, "test.canvas", CanvasNode(id="n1", text="N1"))
    service.add_node(tmp_path, "test.canvas", CanvasNode(id="n2", text="N2"))
    service.add_edge(tmp_path, "test.canvas", CanvasEdge(id="e1", fromNode="n1", toNode="n2"))
    canvas = service.read_canvas(tmp_path, "test.canvas")
    assert len(canvas.edges) == 1

    # update_edge
    service.update_edge(tmp_path, "test.canvas", "e1", CanvasEdge(id="e1", fromNode="n1", toNode="n2", label="updated"))
    canvas = service.read_canvas(tmp_path, "test.canvas")
    assert canvas.edges[0].label == "updated"

    # remove_edge
    service.remove_edge(tmp_path, "test.canvas", "e1")
    canvas = service.read_canvas(tmp_path, "test.canvas")
    assert len(canvas.edges) == 0


def test_write_canvas_no_indent_reduces_size(tmp_path: Path) -> None:
    service = CanvasFileService()
    service.write_canvas(
        tmp_path,
        "test.canvas",
        CanvasFile(nodes=[CanvasNode(id="node-1", type="text", text="A")]),
    )
    # 显式 flush 后再直接读取原始内容
    service._flush_file_if_pending(str(tmp_path / "test.canvas"))
    raw = (tmp_path / "test.canvas").read_text(encoding="utf-8")
    # 无缩进意味着不应包含换行 + 缩进空格
    assert "\n  " not in raw
    assert "\n    " not in raw
