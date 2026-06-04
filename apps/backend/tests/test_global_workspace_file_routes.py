from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core import config as config_module
from app.services import workspace_registry as workspace_registry_module
from app.api.routes import data_tables as data_tables_route_module
from app.api.routes import workspaces_resources_files as files_route_module
from app.api.routes import workspaces_resources_tree as tree_route_module
from app.api.routes.files_utils import (
    CreateGraphDbRequest,
    CreateKnowledgeDbRequest,
    FileContentRequest,
    FileCreateRequest,
)
from app.models.user import UserInfo
from app.services.data_table_service import DataTableColumnDef, DataTableCreateRequest
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _find_node(nodes: list[dict], path: str) -> dict:
    for node in nodes:
        if node["path"] == path:
            return node
        found = _find_node(node.get("children") or [], path)
        if found:
            return found
    return {}


def _write_resource_metadata_db(path: Path, metadata: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE _aiasys_metadata (key TEXT PRIMARY KEY, value TEXT)")
        conn.executemany(
            "INSERT INTO _aiasys_metadata (key, value) VALUES (?, ?)",
            [(key, str(value)) for key, value in metadata.items()],
        )
        conn.commit()
    finally:
        conn.close()


def _read_resource_metadata_db(path: Path) -> dict[str, str]:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("SELECT key, value FROM _aiasys_metadata").fetchall()
        return {str(key): str(value) for key, value in rows}
    finally:
        conn.close()


def _read_table_columns(path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row[1]) for row in rows}
    finally:
        conn.close()


def _patch_runtime_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    service: WorkspaceRegistryService,
) -> None:
    monkeypatch.setattr(config_module, "WORKSPACE_DIR", tmp_path, raising=False)
    monkeypatch.setattr(
        workspace_registry_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        files_route_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        tree_route_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        data_tables_route_module.config_module,
        "WORKSPACE_DIR",
        tmp_path,
        raising=False,
    )


@pytest.mark.asyncio
async def test_workspace_resource_db_create_routes_register_file_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-resource-create",
        title="资源创建工作区",
    )
    _patch_runtime_roots(monkeypatch, tmp_path, service)

    knowledge_response = await files_route_module.create_knowledge_db_file(
        "workspace-resource-create",
        CreateKnowledgeDbRequest(
            path="resources/analysis-note.kb.db",
            name="analysis-note",
            description="",
        ),
        current_user=_build_user(),
    )
    graph_response = await files_route_module.create_graph_db_file(
        "workspace-resource-create",
        CreateGraphDbRequest(
            path="resources/project.graph.db",
            graph_id="project",
            name="project",
            description="",
        ),
        current_user=_build_user(),
    )

    workspace_root = service.get_workspace_root("local_default", "workspace-resource-create")
    knowledge_path = workspace_root / "resources" / "analysis-note.kb.db"
    graph_path = workspace_root / "resources" / "project.graph.db"
    assert knowledge_response.filename == "resources/analysis-note.kb.db"
    assert knowledge_response.path == "/workspace/resources/analysis-note.kb.db"
    assert knowledge_response.meta is not None
    assert knowledge_response.meta["resource_type"] == "knowledge"
    assert knowledge_path.exists()
    assert graph_response.filename == "resources/project.graph.db"
    assert graph_response.path == "/workspace/resources/project.graph.db"
    assert graph_response.meta is not None
    assert graph_response.meta["resource_type"] == "graph"
    assert graph_path.exists()

    knowledge_meta = _read_resource_metadata_db(knowledge_path)
    assert knowledge_meta["resource_type"] == "knowledge"
    assert knowledge_meta["renderer_hint"] == "knowledge_base_preview"
    assert knowledge_meta["db_path"] == "/workspace/resources/analysis-note.kb.db"
    assert knowledge_meta["name"] == "analysis-note"
    assert knowledge_meta["id"]
    assert knowledge_response.meta["id"] == knowledge_meta["id"]
    assert knowledge_response.meta["db_path"] == "/workspace/resources/analysis-note.kb.db"

    kb = files_route_module.SQLiteKBService().get_knowledge_base(
        "local_default",
        knowledge_meta["id"],
    )
    assert kb is not None
    assert kb.id == knowledge_meta["id"]
    assert kb.name == "analysis-note"

    graph_meta = _read_resource_metadata_db(graph_path)
    assert graph_meta["resource_type"] == "graph"
    assert graph_meta["renderer_hint"] == "knowledge_graph_preview"
    assert graph_meta["db_path"] == "/workspace/resources/project.graph.db"
    assert graph_meta["id"] == "project"
    assert graph_response.meta["id"] == "project"
    assert graph_response.meta["db_path"] == "/workspace/resources/project.graph.db"
    assert _read_table_columns(graph_path, "graph_metadata") >= {
        "key",
        "value",
        "layout_positions",
        "layout_updated_at",
        "entity_count",
        "relation_count",
        "community_count",
    }

    tree = await tree_route_module.get_workspace_resources_tree(
        "workspace-resource-create",
        current_user=_build_user(),
    )
    nodes = tree.model_dump()["nodes"]
    knowledge_node = _find_node(nodes, "resources/analysis-note.kb.db")
    assert knowledge_node["resource_type"] == "knowledge"
    assert knowledge_node["meta"]["id"] == knowledge_meta["id"]
    assert knowledge_node["meta"]["db_path"] == "/workspace/resources/analysis-note.kb.db"
    graph_node = _find_node(nodes, "resources/project.graph.db")
    assert graph_node["resource_type"] == "graph"
    assert graph_node["meta"]["id"] == "project"
    assert graph_node["meta"]["db_path"] == "/workspace/resources/project.graph.db"


@pytest.mark.asyncio
async def test_global_workspace_resource_db_create_routes_use_global_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-global-resource-create",
        title="全局资源创建工作区",
    )
    _patch_runtime_roots(monkeypatch, tmp_path, service)

    knowledge_response = await files_route_module.create_global_workspace_knowledge_db_file(
        "workspace-global-resource-create",
        CreateKnowledgeDbRequest(
            path="resources/shared.kb.db",
            name="shared",
            description="",
        ),
        current_user=_build_user(),
    )
    graph_response = await files_route_module.create_global_workspace_graph_db_file(
        "workspace-global-resource-create",
        CreateGraphDbRequest(
            path="resources/shared.graph.db",
            graph_id="shared-graph",
            name="shared graph",
            description="",
        ),
        current_user=_build_user(),
    )

    global_root = tmp_path / "local_default" / "global_workspace"
    workspace_root = service.get_workspace_root(
        "local_default",
        "workspace-global-resource-create",
    )
    knowledge_path = global_root / "resources" / "shared.kb.db"
    graph_path = global_root / "resources" / "shared.graph.db"
    assert knowledge_response.path == "/global/resources/shared.kb.db"
    assert graph_response.path == "/global/resources/shared.graph.db"
    assert knowledge_response.meta is not None
    assert knowledge_response.meta["resource_type"] == "knowledge"
    assert graph_response.meta is not None
    assert graph_response.meta["resource_type"] == "graph"
    assert knowledge_path.exists()
    assert graph_path.exists()
    assert not (workspace_root / "resources" / "shared.kb.db").exists()
    assert not (workspace_root / "resources" / "shared.graph.db").exists()

    knowledge_meta = _read_resource_metadata_db(knowledge_path)
    assert knowledge_meta["resource_type"] == "knowledge"
    assert knowledge_meta["db_path"] == "/global/resources/shared.kb.db"
    assert knowledge_meta["id"]
    assert knowledge_response.meta["id"] == knowledge_meta["id"]
    assert knowledge_response.meta["db_path"] == "/global/resources/shared.kb.db"
    graph_meta = _read_resource_metadata_db(graph_path)
    assert graph_meta["resource_type"] == "graph"
    assert graph_meta["db_path"] == "/global/resources/shared.graph.db"
    assert graph_meta["id"] == "shared-graph"
    assert graph_response.meta["id"] == "shared-graph"
    assert graph_response.meta["db_path"] == "/global/resources/shared.graph.db"
    assert _read_table_columns(graph_path, "graph_metadata") >= {
        "key",
        "value",
        "layout_positions",
        "layout_updated_at",
        "entity_count",
        "relation_count",
        "community_count",
    }

    tree = await files_route_module.get_global_workspace_resources_tree(
        "workspace-global-resource-create",
        current_user=_build_user(),
    )
    nodes = tree.model_dump()["nodes"]
    knowledge_node = _find_node(nodes, "resources/shared.kb.db")
    assert knowledge_node["resource_type"] == "knowledge"
    assert knowledge_node["meta"]["id"] == knowledge_meta["id"]
    assert knowledge_node["meta"]["db_path"] == "/global/resources/shared.kb.db"
    assert knowledge_node["meta"]["source"] == "global_workspace_asset"
    graph_node = _find_node(nodes, "resources/shared.graph.db")
    assert graph_node["resource_type"] == "graph"
    assert graph_node["meta"]["id"] == "shared-graph"
    assert graph_node["meta"]["db_path"] == "/global/resources/shared.graph.db"
    assert graph_node["meta"]["source"] == "global_workspace_asset"


@pytest.mark.asyncio
async def test_resource_db_create_routes_reject_wrong_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-resource-suffix",
        title="资源后缀测试",
    )
    _patch_runtime_roots(monkeypatch, tmp_path, service)

    with pytest.raises(HTTPException) as knowledge_exc:
        await files_route_module.create_knowledge_db_file(
            "workspace-resource-suffix",
            CreateKnowledgeDbRequest(path="bad.db", name="bad"),
            current_user=_build_user(),
        )
    assert knowledge_exc.value.status_code == 400

    with pytest.raises(HTTPException) as graph_exc:
        await files_route_module.create_graph_db_file(
            "workspace-resource-suffix",
            CreateGraphDbRequest(path="bad.db", graph_id="bad", name="bad"),
            current_user=_build_user(),
        )
    assert graph_exc.value.status_code == 400


@pytest.mark.asyncio
async def test_global_workspace_file_crud_uses_user_global_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-a",
        title="任务 A",
    )
    _patch_runtime_roots(monkeypatch, tmp_path, service)

    response = await files_route_module.create_global_workspace_file(
        "workspace-a",
        FileCreateRequest(path="docs/shared.md", content="# shared\n"),
        current_user=_build_user(),
    )

    global_file = tmp_path / "local_default" / "global_workspace" / "docs" / "shared.md"
    workspace_file = tmp_path / "local_default" / "workspace-a" / "docs" / "shared.md"
    assert response.path == "/global/docs/shared.md"
    assert global_file.read_text(encoding="utf-8") == "# shared\n"
    assert not workspace_file.exists()

    content = await files_route_module.get_global_workspace_file_content(
        "workspace-a",
        "docs/shared.md",
        current_user=_build_user(),
    )
    assert content.filename == "docs/shared.md"
    assert content.content == "# shared\n"
    assert content.editable is True

    updated = await files_route_module.update_global_workspace_file_content(
        "workspace-a",
        "docs/shared.md",
        FileContentRequest(content="# updated\n"),
        current_user=_build_user(),
    )
    assert updated["success"] is True
    assert global_file.read_text(encoding="utf-8") == "# updated\n"

    tree = await files_route_module.get_global_workspace_resources_tree(
        "workspace-a",
        current_user=_build_user(),
    )
    nodes = tree.model_dump()["nodes"]
    docs_node = _find_node(nodes, "docs")
    file_node = _find_node(nodes, "docs/shared.md")
    assert docs_node["node_type"] == "directory"
    assert docs_node["absolute_path"] == str(global_file.parent.absolute())
    assert file_node["node_type"] == "resource"
    assert file_node["absolute_path"] == str(global_file.absolute())
    assert file_node["meta"]["db_path"] == "/global/docs/shared.md"
    assert file_node["meta"]["source"] == "global_workspace_asset"

    deleted = await files_route_module.delete_global_workspace_file(
        "workspace-a",
        "docs/shared.md",
        current_user=_build_user(),
    )
    assert deleted["success"] is True
    assert not global_file.exists()


@pytest.mark.asyncio
async def test_workspace_and_global_csv_preview_routes_page_and_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-csv",
        title="CSV 工作区",
    )
    _patch_runtime_roots(monkeypatch, tmp_path, service)

    workspace_root = service.get_workspace_root("local_default", "workspace-csv")
    workspace_csv = workspace_root / "tables" / "local.csv"
    workspace_csv.parent.mkdir(parents=True, exist_ok=True)
    workspace_csv.write_text(
        "a,b,c\n"
        "1,2,3\n"
        "4,5,6\n"
        "7,8,9\n"
        "10,11,12\n",
        encoding="utf-8",
    )

    workspace_page = await files_route_module.get_workspace_csv_preview(
        "workspace-csv",
        "tables/local.csv",
        page=1,
        page_size=2,
        column_offset=1,
        column_limit=2,
        current_user=_build_user(),
    )
    assert workspace_page.headers == ["b", "c"]
    assert workspace_page.rows == [["2", "3"], ["5", "6"]]
    assert workspace_page.has_next is True

    workspace_update = await files_route_module.update_workspace_csv_preview(
        "workspace-csv",
        "tables/local.csv",
        files_route_module.CsvPageUpdateRequest(
            rows=[["20", "30"], ["50", "60"]],
            page=1,
            page_size=2,
            column_offset=1,
            column_limit=2,
        ),
        current_user=_build_user(),
    )
    assert workspace_update["updated_rows"] == 2
    assert workspace_csv.read_text(encoding="utf-8") == (
        "a,b,c\n"
        "1,20,30\n"
        "4,50,60\n"
        "7,8,9\n"
        "10,11,12\n"
    )

    workspace_page_two = await files_route_module.get_workspace_csv_preview(
        "workspace-csv",
        "tables/local.csv",
        page=2,
        page_size=2,
        column_offset=1,
        column_limit=2,
        current_user=_build_user(),
    )
    assert workspace_page_two.rows == [["8", "9"], ["11", "12"]]

    global_csv = tmp_path / "local_default" / "global_workspace" / "tables" / "shared.csv"
    global_csv.parent.mkdir(parents=True, exist_ok=True)
    global_csv.write_text("x,y\nalpha,beta\ngamma,delta\n", encoding="utf-8")

    global_page = await files_route_module.get_global_workspace_csv_preview(
        "workspace-csv",
        "tables/shared.csv",
        page=1,
        page_size=1,
        column_offset=0,
        column_limit=1,
        current_user=_build_user(),
    )
    assert global_page.headers == ["x"]
    assert global_page.rows == [["alpha"]]
    assert global_page.has_next is True
    assert global_page.has_more_columns is True

    global_update = await files_route_module.update_global_workspace_csv_preview(
        "workspace-csv",
        "tables/shared.csv",
        files_route_module.CsvPageUpdateRequest(
            rows=[["ALPHA"]],
            page=1,
            page_size=1,
            column_offset=0,
            column_limit=1,
        ),
        current_user=_build_user(),
    )
    assert global_update["updated_rows"] == 1
    assert global_csv.read_text(encoding="utf-8") == "x,y\nALPHA,beta\ngamma,delta\n"


@pytest.mark.asyncio
async def test_global_workspace_copy_and_move_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(tmp_path, session_manager=SessionManager(tmp_path))
    _patch_runtime_roots(monkeypatch, tmp_path, service)

    service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-copy-move",
        title="复制移动工作区",
        initial_conversation_id="conversation-copy-move-001",
        initial_conversation_title="复制移动对话",
    )

    global_root = tmp_path / "local_default" / "global_workspace"
    source = global_root / "docs" / "source.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# source\n", encoding="utf-8")

    copied = await files_route_module.copy_global_workspace_file(
        "workspace-copy-move",
        files_route_module.FileCopyRequest(
            source="docs/source.md",
            target="docs/source copy.md",
        ),
        current_user=_build_user(),
    )

    assert copied.success is True
    copied_path = global_root / "docs" / "source copy.md"
    assert copied_path.read_text(encoding="utf-8") == "# source\n"

    moved = await files_route_module.move_global_workspace_file(
        "workspace-copy-move",
        files_route_module.FileMoveRequest(
            source="docs/source copy.md",
            target="archive/source copy.md",
        ),
        current_user=_build_user(),
    )

    assert moved.success is True
    assert not copied_path.exists()
    assert (global_root / "archive" / "source copy.md").read_text(
        encoding="utf-8",
    ) == "# source\n"


@pytest.mark.asyncio
async def test_global_workspace_tree_isolated_from_workspace_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-b",
        title="任务 B",
    )
    _patch_runtime_roots(monkeypatch, tmp_path, service)

    workspace_root = service.get_workspace_root("local_default", "workspace-b")
    (workspace_root / "current-only.md").write_text("current", encoding="utf-8")

    await files_route_module.create_global_workspace_file(
        "workspace-b",
        FileCreateRequest(path="global-only.md", content="global"),
        current_user=_build_user(),
    )

    workspace_tree = await tree_route_module.get_workspace_resources_tree(
        "workspace-b",
        current_user=_build_user(),
    )
    global_tree = await files_route_module.get_global_workspace_resources_tree(
        "workspace-b",
        current_user=_build_user(),
    )

    workspace_nodes = workspace_tree.model_dump()["nodes"]
    global_nodes = global_tree.model_dump()["nodes"]
    assert _find_node(workspace_nodes, "current-only.md") != {}
    assert _find_node(workspace_nodes, "global-only.md") == {}
    assert _find_node(global_nodes, "global-only.md") != {}
    assert _find_node(global_nodes, "current-only.md") == {}


@pytest.mark.asyncio
async def test_global_workspace_rejects_path_traversal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    _patch_runtime_roots(monkeypatch, tmp_path, service)

    with pytest.raises(HTTPException) as exc_info:
        await files_route_module.create_global_workspace_file(
            "workspace-c",
            FileCreateRequest(path="../escape.md", content="bad"),
            current_user=_build_user(),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_global_workspace_tree_preserves_folder_markers_and_resource_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-d",
        title="任务 D",
    )
    _patch_runtime_roots(monkeypatch, tmp_path, service)

    global_root = tmp_path / "local_default" / "global_workspace"
    marker = global_root / "reports/2026/__aiasys_folder__.md"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("", encoding="utf-8")
    _write_resource_metadata_db(
        global_root / "resources/shared.table.db",
        {
            "resource_type": "data_table",
            "id": "shared-table",
            "renderer_hint": "data_table_preview",
        },
    )

    tree = await files_route_module.get_global_workspace_resources_tree(
        "workspace-d",
        current_user=_build_user(),
    )
    nodes = tree.model_dump()["nodes"]

    reports_dir = _find_node(nodes, "reports")
    assert reports_dir["node_type"] == "directory"
    assert reports_dir["absolute_path"] == str((global_root / "reports").absolute())
    year_dir = _find_node(nodes, "reports/2026")
    assert year_dir["node_type"] == "directory"
    assert year_dir["absolute_path"] == str((global_root / "reports/2026").absolute())
    assert _find_node(nodes, "reports/2026/__aiasys_folder__.md") == {}

    table_node = _find_node(nodes, "resources/shared.table.db")
    assert table_node["absolute_path"] == str((global_root / "resources/shared.table.db").absolute())
    assert table_node["resource_type"] == "data_table"
    assert table_node["meta"]["id"] == "shared-table"
    assert table_node["meta"]["db_path"] == "/global/resources/shared.table.db"
    assert table_node["meta"]["source"] == "global_workspace_asset"


@pytest.mark.asyncio
async def test_global_workspace_data_table_routes_use_global_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-e",
        title="任务 E",
    )
    _patch_runtime_roots(monkeypatch, tmp_path, service)

    created = await data_tables_route_module.create_global_workspace_data_table(
        "workspace-e",
        DataTableCreateRequest(
            name="共享表",
            id="shared-table",
            directory="resources",
            columns=[
                DataTableColumnDef(name="名称", type="text", required=True),
                DataTableColumnDef(
                    name="状态",
                    type="single_select",
                    options=["待办", "完成"],
                ),
            ],
        ),
        current_user=_build_user(),
    )

    global_table = (
        tmp_path
        / "local_default"
        / "global_workspace"
        / "resources"
        / "共享表.table.db"
    )
    workspace_table = (
        tmp_path
        / "local_default"
        / "workspace-e"
        / "resources"
        / "共享表.table.db"
    )
    assert created.relative_path == "resources/共享表.table.db"
    assert global_table.exists()
    assert not workspace_table.exists()

    schema = await data_tables_route_module.get_global_data_table_schema(
        "workspace-e",
        "resources/共享表.table.db",
        current_user=_build_user(),
    )
    assert schema["metadata"]["resource_type"] == "data_table"
    assert [column["name"] for column in schema["columns"]] == ["名称", "状态"]

    inserted = await data_tables_route_module.post_global_data_table_records(
        "workspace-e",
        "resources/共享表.table.db",
        data_tables_route_module.InsertRecordsRequest(
            records=[{"名称": "验证记录", "状态": "待办"}],
        ),
        current_user=_build_user(),
    )
    record_id = inserted.inserted_ids[0]

    updated = await data_tables_route_module.put_global_data_table_record(
        "workspace-e",
        "resources/共享表.table.db",
        record_id,
        data_tables_route_module.UpdateRecordRequest(
            data={"状态": "完成"},
        ),
        current_user=_build_user(),
    )
    assert updated.updated is True

    records = await data_tables_route_module.get_global_data_table_records(
        "workspace-e",
        "resources/共享表.table.db",
        current_user=_build_user(),
    )
    assert records.records[0]["名称"] == "验证记录"
    assert records.records[0]["状态"] == "完成"

    column_result = await data_tables_route_module.add_global_column_endpoint(
        "workspace-e",
        "resources/共享表.table.db",
        data_tables_route_module.AddColumnRequest(name="备注", type="text"),
        current_user=_build_user(),
    )
    assert column_result.success is True

    deleted = await data_tables_route_module.delete_global_data_table_record_endpoint(
        "workspace-e",
        "resources/共享表.table.db",
        record_id,
        current_user=_build_user(),
    )
    assert deleted.deleted is True
