from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.api.routes import files as files_route
from app.api.routes import files_core as files_core_route
from app.api.routes import files_utils as files_utils_route
from app.api.routes import workspaces as workspaces_route
from app.api.routes import workspaces_resources_files as workspace_files_route
from app.models.user import UserInfo
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService
from scripts import init_resource_db_test_assets as seed_script


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_workspace_service(tmp_path: Path) -> WorkspaceRegistryService:
    return WorkspaceRegistryService(tmp_path, session_manager=SessionManager(tmp_path))


def _patch_file_route_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    service: WorkspaceRegistryService,
) -> None:
    for module in (
        files_route,
        files_core_route,
        files_utils_route,
        workspaces_route,
        workspace_files_route,
    ):
        monkeypatch.setattr(module, "WORKSPACE_DIR", tmp_path, raising=False)
        monkeypatch.setattr(
            module,
            "get_workspace_registry_service",
            lambda: service,
            raising=False,
        )


async def _list_workspace_files(
    workspace_id: str,
    **kwargs: object,
) -> dict[str, object]:
    response = await workspace_files_route.list_workspace_files(
        workspace_id,
        current_user=_build_user(),
        **kwargs,
    )
    payload = response.model_dump(exclude_none=True)
    payload["files"] = [
        {key: value for key, value in item.items() if not (key == "meta" and value == {})}
        for item in payload["files"]
    ]
    return payload


def _read_metadata(db_path: Path) -> dict[str, object]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT key, value FROM _aiasys_metadata ORDER BY key").fetchall()
    finally:
        conn.close()

    metadata: dict[str, object] = {}
    for key, value in rows:
        text_value = str(value)
        if (value and text_value[0] in '[{"-') or text_value.isdigit():
            try:
                metadata[key] = json.loads(value)
                continue
            except json.JSONDecodeError:
                pass
        metadata[key] = value
    return metadata


def test_write_resource_db_assets_creates_three_resource_databases(
    tmp_path: Path,
) -> None:
    result = seed_script.write_resource_db_assets(tmp_path, overwrite=True)

    assert [item["relative_path"] for item in result] == [
        "knowledge/product-docs.knowledge.db",
        "graphs/project.graph.db",
        "databases/workspace.sqlite.db",
    ]
    assert {item["status"] for item in result} == {"created"}

    knowledge_db = tmp_path / "knowledge/product-docs.knowledge.db"
    graph_db = tmp_path / "graphs/project.graph.db"
    database_db = tmp_path / "databases/workspace.sqlite.db"

    assert _read_metadata(knowledge_db)["resource_type"] == "knowledge"
    assert _read_metadata(graph_db)["resource_type"] == "graph"
    assert _read_metadata(database_db)["resource_type"] == "database"
    assert _read_metadata(database_db)["meta"] == {"readonly": False}

    conn = sqlite3.connect(knowledge_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 3
    finally:
        conn.close()

    conn = sqlite3.connect(graph_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0] == 2
    finally:
        conn.close()

    conn = sqlite3.connect(database_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM sample_metrics").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM sample_events").fetchone()[0] == 2
    finally:
        conn.close()


def test_write_resource_db_assets_preserves_existing_files_without_overwrite(
    tmp_path: Path,
) -> None:
    seed_script.write_resource_db_assets(tmp_path, overwrite=True)
    knowledge_db = tmp_path / "knowledge/product-docs.knowledge.db"
    before_mtime = knowledge_db.stat().st_mtime_ns

    result = seed_script.write_resource_db_assets(tmp_path, overwrite=False)

    assert {item["status"] for item in result} == {"exists"}
    assert knowledge_db.stat().st_mtime_ns == before_mtime


def test_seed_resource_db_assets_binds_requested_session_to_workspace(
    tmp_path: Path,
) -> None:
    service = _build_workspace_service(tmp_path)
    service.create_workspace(
        user_id="local_default",
        workspace_id="resource-db-existing",
        title="资源 DB 已有工作区",
        initial_conversation_id="resource-db-existing-main",
        initial_conversation_title="已有会话",
    )

    result = seed_script.seed_resource_db_test_assets(
        user_id="local_default",
        workspace_id="resource-db-existing",
        session_id="resource-db-requested-session",
        create_workspace=True,
        overwrite=True,
        registry=service,
    )

    assert result["workspace_id"] == "resource-db-existing"
    assert result["session_id"] == "resource-db-requested-session"
    assert (
        service.find_workspace_id_by_session_id(
            "local_default",
            "resource-db-requested-session",
        )
        == "resource-db-existing"
    )
    assert Path(result["workspace_root"]) == service.get_workspace_root(
        "local_default",
        "resource-db-existing",
    )
    assert (
        tmp_path / "local_default" / "resource-db-existing" / "knowledge/product-docs.knowledge.db"
    ).exists()


@pytest.mark.asyncio
async def test_seed_resource_db_assets_are_visible_through_file_list_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    _patch_file_route_workspace(monkeypatch, tmp_path, service)

    result = seed_script.seed_resource_db_test_assets(
        user_id="local_default",
        workspace_id="resource-db-test",
        session_id=None,
        create_workspace=True,
        overwrite=True,
        registry=service,
    )
    assert result["workspace_id"] == "resource-db-test"
    assert result["session_id"] == "resource-db-smoke-main"

    listing = await _list_workspace_files(
        result["workspace_id"],
        recursive=True,
    )
    files_by_name = {item["name"]: item for item in listing["files"]}

    knowledge = files_by_name["knowledge/product-docs.knowledge.db"]
    assert knowledge["resource_type"] == "knowledge"
    assert knowledge["schema_kind"] == "aiasys.knowledge_base.sqlite.v1"
    assert knowledge["preview_kind"] == "knowledge_base"
    assert knowledge["renderer_hint"] == "knowledge_base_preview"
    assert knowledge["meta"]["id"] == "kb-product-docs"
    assert knowledge["meta"]["document_count"] == 3
    assert knowledge["meta"]["db_path"] == ("/workspace/knowledge/product-docs.knowledge.db")

    graph = files_by_name["graphs/project.graph.db"]
    assert graph["resource_type"] == "graph"
    assert graph["preview_kind"] == "knowledge_graph"
    assert graph["meta"]["entity_count"] == 3
    assert graph["meta"]["relation_count"] == 2

    database = files_by_name["databases/workspace.sqlite.db"]
    assert database["resource_type"] == "database"
    assert database["renderer_hint"] == "database_preview"
    assert database["meta"]["handle"] == "workspace-sqlite"
    assert database["meta"]["readonly"] is False
