from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.tools import canvas_tool, data_table_tool
from app.models.canvas import CanvasBatchOperation, CanvasEdge, CanvasFile, CanvasNode
from app.services.history import current_global_workspace, current_workspace


@pytest.fixture
def workspace_context(tmp_path: Path):
    workspace = tmp_path / "workspace"
    global_workspace = tmp_path / "global_workspace"
    workspace.mkdir()
    global_workspace.mkdir()
    workspace_token = current_workspace.set(workspace)
    global_token = current_global_workspace.set(global_workspace)
    try:
        yield workspace, global_workspace
    finally:
        current_global_workspace.reset(global_token)
        current_workspace.reset(workspace_token)


@pytest.mark.asyncio
async def test_data_table_tools_manage_workspace_table(workspace_context) -> None:
    workspace, _global_workspace = workspace_context

    create_result = await data_table_tool.CreateDataTable().invoke(
        name="实验记录",
        table_id="experiment-log",
        directory="tables",
        columns=[
            {"name": "实验名", "type": "text"},
            {"name": "准确率", "type": "number", "precision": 4},
        ],
    )
    table_path = "/workspace/tables/实验记录.table.db"

    schema_result = await data_table_tool.ReadDataTableSchema().invoke(
        table_path=table_path,
    )
    insert_result = await data_table_tool.InsertDataTableRecords().invoke(
        table_path=table_path,
        records=[{"实验名": "baseline", "准确率": 0.82}],
    )
    record_id = insert_result.artifacts[0]["data_table_insert"]["inserted_ids"][0]
    records_result = await data_table_tool.QueryDataTable().invoke(
        table_path=table_path,
        sql="SELECT * FROM records LIMIT 10",
    )
    update_result = await data_table_tool.UpdateDataTableRecord().invoke(
        table_path=table_path,
        record_id=record_id,
        data={"准确率": 0.86},
    )
    add_column_result = await data_table_tool.AddDataTableColumn().invoke(
        table_path=table_path,
        name="状态",
        type="single_select",
        options=["进行中", "完成"],
    )
    update_column_result = await data_table_tool.UpdateDataTableColumn().invoke(
        table_path=table_path,
        column_name="状态",
        column={"name": "结论", "type": "text"},
    )
    remove_column_result = await data_table_tool.RemoveDataTableColumn().invoke(
        table_path=table_path,
        column_name="结论",
    )
    delete_result = await data_table_tool.DeleteDataTableRecord().invoke(
        table_path=table_path,
        record_id=record_id,
    )

    assert create_result.is_error is False
    assert (workspace / "tables" / "实验记录.table.db").exists()
    assert "实验名: text" in schema_result.output
    assert insert_result.is_error is False
    assert "baseline" in records_result.output
    assert update_result.is_error is False
    assert add_column_result.is_error is False
    assert update_column_result.is_error is False
    assert remove_column_result.is_error is False
    assert delete_result.is_error is False


@pytest.mark.asyncio
async def test_data_table_tool_rejects_path_escape(workspace_context) -> None:
    result = await data_table_tool.ReadDataTableSchema().invoke(
        table_path="/workspace/../outside.table.db",
    )

    assert result.is_error is True
    assert "非法路径片段" in result.output


@pytest.mark.asyncio
async def test_data_table_tools_support_global_workspace(workspace_context) -> None:
    _workspace, global_workspace = workspace_context

    result = await data_table_tool.CreateDataTable().invoke(
        name="共享清单",
        table_id="shared-list",
        scope="global",
        columns=[{"name": "名称", "type": "text"}],
    )
    read_result = await data_table_tool.ReadDataTableSchema().invoke(
        table_path="/global/共享清单.table.db",
    )

    assert result.is_error is False
    assert (global_workspace / "共享清单.table.db").exists()
    assert read_result.is_error is False
    assert "位置: 全局工作区" in read_result.output


@pytest.mark.asyncio
async def test_canvas_tools_read_write_and_batch(workspace_context) -> None:
    workspace, _global_workspace = workspace_context

    write_result = await canvas_tool.WriteCanvas().invoke(
        canvas_path="/workspace/boards/plan.canvas",
        canvas=CanvasFile(
            nodes=[
                CanvasNode(
                    id="node-a",
                    type="text",
                    x=0,
                    y=0,
                    width=240,
                    height=120,
                    text="开始",
                )
            ],
            edges=[],
        ).model_dump(),
    )
    batch_result = await canvas_tool.BatchCanvasOperations().invoke(
        canvas_path="/workspace/boards/plan.canvas",
        operations=[
            CanvasBatchOperation(
                type="add_node",
                node=CanvasNode(
                    id="node-b",
                    type="text",
                    x=320,
                    y=0,
                    width=240,
                    height=120,
                    text="结束",
                ),
            ).model_dump(),
            CanvasBatchOperation(
                type="add_edge",
                edge=CanvasEdge(id="edge-a", fromNode="node-a", toNode="node-b"),
            ).model_dump(),
        ],
    )
    read_result = await canvas_tool.ReadCanvas().invoke(
        canvas_path="boards/plan.canvas",
    )

    assert write_result.is_error is False
    assert (workspace / "boards" / "plan.canvas").exists()
    assert batch_result.is_error is False
    assert "节点数: 2" in batch_result.output
    assert "边数: 1" in batch_result.output
    assert read_result.artifacts[0]["canvas"]["document"]["nodes"][1]["id"] == "node-b"
    assert read_result.artifacts[0]["canvas"]["document"]["edges"][0]["id"] == "edge-a"


@pytest.mark.asyncio
async def test_canvas_tool_supports_global_workspace(workspace_context) -> None:
    _workspace, global_workspace = workspace_context

    result = await canvas_tool.WriteCanvas().invoke(
        canvas_path="/global/shared.canvas",
        canvas={"nodes": [], "edges": []},
    )
    read_result = await canvas_tool.ReadCanvas().invoke(
        canvas_path="/global/shared.canvas",
    )

    assert result.is_error is False
    assert (global_workspace / "shared.canvas").exists()
    assert read_result.is_error is False
    assert "Canvas: /global/shared.canvas" in read_result.output


@pytest.mark.asyncio
async def test_canvas_tool_rejects_path_escape(workspace_context) -> None:
    result = await canvas_tool.ReadCanvas().invoke(
        canvas_path="/workspace/../escape.canvas",
    )

    assert result.is_error is True
    assert "非法路径片段" in result.output
