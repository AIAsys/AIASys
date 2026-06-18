from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.core import config as config_module
from app.api.routes import files as files_route
from app.api.routes import files_core as files_core_route
from app.api.routes import files_utils as files_utils_route
from app.api.routes import workspaces as workspaces_route
from app.api.routes import workspaces_resources_files as workspace_files_route
from app.models.user import UserInfo
from app.services import workspace_registry as workspace_registry_module
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_workspace_service(tmp_path: Path) -> WorkspaceRegistryService:
    return WorkspaceRegistryService(tmp_path, session_manager=SessionManager(tmp_path))


def _patch_file_route_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    service: WorkspaceRegistryService,
) -> None:
    monkeypatch.setattr(config_module, "WORKSPACE_DIR", tmp_path, raising=False)
    for module in (
        files_route,
        files_core_route,
        files_utils_route,
        workspaces_route,
        workspace_files_route,
        workspace_registry_module,
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


@pytest.mark.asyncio
async def test_file_routes_use_workspace_root_for_bound_conversations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    _patch_file_route_workspace(monkeypatch, tmp_path, service)

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-files",
        title="任务 Files",
        initial_conversation_id="conversation-files-001",
        initial_conversation_title="文件对话",
    )
    conversation = workspace.current_conversation
    assert conversation is not None

    upload = UploadFile(
        file=io.BytesIO(b"hello workspace"),
        filename="notes.txt",
    )
    result = await files_route.upload_file(
        "local_default",
        conversation.session_id,
        file=upload,
        current_user=_build_user(),
    )

    workspace_root_file = tmp_path / "local_default" / "task-files" / "uploads" / "notes.txt"
    legacy_session_file = tmp_path / "local_default" / conversation.session_id / "notes.txt"
    assert result["success"] is True
    assert workspace_root_file.exists()
    assert workspace_root_file.read_text(encoding="utf-8") == "hello workspace"
    assert not legacy_session_file.exists()

    listing = await _list_workspace_files(
        workspace.workspace_id,
        recursive=True,
    )
    listed_note = next(
        item
        for item in listing["files"]
        if item["name"] == "notes.txt" or item["name"] == "uploads/notes.txt"
    )
    assert listed_note["size"] == len(b"hello workspace")

    exported = await files_route.export_workspace(
        "local_default",
        conversation.session_id,
        current_user=_build_user(),
    )
    body = b""
    async for chunk in exported.body_iterator:
        body += chunk

    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert "uploads/notes.txt" in archive.namelist()
        assert archive.read("uploads/notes.txt") == b"hello workspace"


@pytest.mark.asyncio
async def test_create_file_writes_nested_text_file_to_workspace_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    _patch_file_route_workspace(monkeypatch, tmp_path, service)

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-create-file",
        title="任务 Create File",
        initial_conversation_id="conversation-create-file-001",
        initial_conversation_title="新建文件对话",
    )
    conversation = workspace.current_conversation
    assert conversation is not None

    response = await files_route.create_file(
        "local_default",
        conversation.session_id,
        files_route.FileCreateRequest(
            path="reports/analysis-note.md",
            content="# 分析记录\n",
        ),
        current_user=_build_user(),
    )

    workspace_file = (
        tmp_path / "local_default" / "task-create-file" / "reports" / "analysis-note.md"
    )
    assert response.success is True
    assert response.filename == "reports/analysis-note.md"
    assert response.path == "/workspace/reports/analysis-note.md"
    assert response.overwritten is False
    assert workspace_file.read_text(encoding="utf-8") == "# 分析记录\n"

    listing = await _list_workspace_files(
        workspace.workspace_id,
        recursive=True,
    )
    assert any(item["name"] == "reports/analysis-note.md" for item in listing["files"])


@pytest.mark.asyncio
async def test_csv_preview_pages_and_updates_visible_slice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    _patch_file_route_workspace(monkeypatch, tmp_path, service)

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-csv-preview",
        title="任务 CSV Preview",
        initial_conversation_id="conversation-csv-preview-001",
        initial_conversation_title="CSV 预览对话",
    )
    conversation = workspace.current_conversation
    assert conversation is not None

    workspace_dir = service._get_workspace_dir("local_default", "task-csv-preview")
    csv_path = workspace_dir / "data" / "large.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(
        "a,b,c\n1,2,3\n4,5,6\n7,8,9\n10,11,12\n",
        encoding="utf-8",
    )

    page = await files_route.get_csv_preview(
        "local_default",
        conversation.session_id,
        "data/large.csv",
        page=2,
        page_size=2,
        column_offset=1,
        column_limit=1,
        current_user=_build_user(),
    )

    assert page.headers == ["b"]
    assert page.rows == [["8"], ["11"]]
    assert page.start_row == 3
    assert page.has_previous is True
    assert page.has_next is False
    assert page.total_columns == 3
    assert page.has_previous_columns is True
    assert page.has_more_columns is True

    update = await files_route.update_csv_preview(
        "local_default",
        conversation.session_id,
        "data/large.csv",
        files_route.CsvPageUpdateRequest(
            rows=[["50"], ["80"]],
            page=2,
            page_size=2,
            column_offset=1,
            column_limit=1,
        ),
        current_user=_build_user(),
    )

    assert update["success"] is True
    assert update["updated_rows"] == 2
    assert csv_path.read_text(encoding="utf-8") == ("a,b,c\n1,2,3\n4,5,6\n7,50,9\n10,80,12\n")


@pytest.mark.asyncio
async def test_list_files_hides_workspace_internal_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    _patch_file_route_workspace(monkeypatch, tmp_path, service)

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-hidden-internal-files",
        title="任务 Internal Files",
        initial_conversation_id="conversation-hidden-internal-files-001",
        initial_conversation_title="内部文件过滤对话",
    )
    conversation = workspace.current_conversation
    assert conversation is not None

    workspace_dir = service._get_workspace_dir(
        "local_default",
        "task-hidden-internal-files",
    )
    workspace_state_file = workspace_dir / ".workspace" / "state.json"
    workspace_state_file.parent.mkdir(parents=True, exist_ok=True)
    workspace_state_file.write_text(
        "{}",
        encoding="utf-8",
    )
    memory_file = workspace_dir / ".aiasys" / "memory" / "workspace_memory.md"
    memory_file.parent.mkdir(parents=True, exist_ok=True)
    memory_file.write_text("internal memory", encoding="utf-8")
    (workspace_dir / ".aiasys" / "memory" / "workspace_memory.md.lock").write_text(
        "",
        encoding="utf-8",
    )
    (workspace_dir / ".env" / "environments.json").parent.mkdir(parents=True, exist_ok=True)
    (workspace_dir / ".env" / "environments.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (workspace_dir / ".env" / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
    (workspace_dir / ".env" / ".venv" / "bin" / "python").write_text(
        "#!/usr/bin/env python\n",
        encoding="utf-8",
    )
    (workspace_dir / "notes.md").write_text("visible", encoding="utf-8")

    listing = await _list_workspace_files(
        workspace.workspace_id,
        recursive=True,
    )

    listed_names = {item["name"] for item in listing["files"]}
    assert "notes.md" in listed_names
    assert not any(name.startswith(".aiasys/") for name in listed_names)
    assert not any(name.startswith(".env/") for name in listed_names)


@pytest.mark.asyncio
async def test_list_files_defaults_to_shallow_root_listing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    _patch_file_route_workspace(monkeypatch, tmp_path, service)

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-shallow-list-files",
        title="任务 Shallow List",
        initial_conversation_id="conversation-shallow-list-files-001",
        initial_conversation_title="浅层文件列表对话",
    )
    conversation = workspace.current_conversation
    assert conversation is not None

    workspace_dir = service._get_workspace_dir("local_default", "task-shallow-list-files")
    (workspace_dir / "root.md").write_text("root", encoding="utf-8")
    nested_file = workspace_dir / "reports" / "summary.md"
    nested_file.parent.mkdir(parents=True, exist_ok=True)
    nested_file.write_text("# summary\n", encoding="utf-8")

    listing = await _list_workspace_files(workspace.workspace_id)
    listed_names = {item["name"] for item in listing["files"]}

    assert listed_names == {"root.md"}
    assert listing["directory"] == ""
    assert listing["recursive"] is False
    assert listing["returned"] == 1
    assert listing["has_more"] is False


@pytest.mark.asyncio
async def test_list_files_supports_directory_recursive_pagination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    _patch_file_route_workspace(monkeypatch, tmp_path, service)

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-paged-list-files",
        title="任务 Paged List",
        initial_conversation_id="conversation-paged-list-files-001",
        initial_conversation_title="分页文件列表对话",
    )
    conversation = workspace.current_conversation
    assert conversation is not None

    workspace_dir = service._get_workspace_dir("local_default", "task-paged-list-files")
    for index in range(5):
        target = workspace_dir / "reports" / f"{index:02d}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(index), encoding="utf-8")
    nested_file = workspace_dir / "reports" / "deep" / "nested.md"
    nested_file.parent.mkdir(parents=True, exist_ok=True)
    nested_file.write_text("nested", encoding="utf-8")
    (workspace_dir / "root.md").write_text("root", encoding="utf-8")

    page = await _list_workspace_files(
        workspace.workspace_id,
        directory="reports",
        recursive=True,
        max_depth=0,
        limit=2,
        offset=1,
        include_total=True,
    )

    assert [item["name"] for item in page["files"]] == [
        "reports/01.md",
        "reports/02.md",
    ]
    assert page["directory"] == "reports"
    assert page["recursive"] is True
    assert page["limit"] == 2
    assert page["offset"] == 1
    assert page["returned"] == 2
    assert page["has_more"] is True
    assert page["next_offset"] == 3
    assert page["total"] == 5


@pytest.mark.asyncio
async def test_create_file_rejects_existing_file_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    _patch_file_route_workspace(monkeypatch, tmp_path, service)

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-create-file-conflict",
        title="任务 Create File Conflict",
        initial_conversation_id="conversation-create-file-conflict-001",
        initial_conversation_title="文件冲突对话",
    )
    conversation = workspace.current_conversation
    assert conversation is not None

    await files_route.create_file(
        "local_default",
        conversation.session_id,
        files_route.FileCreateRequest(path="notes.md", content="v1"),
        current_user=_build_user(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await files_route.create_file(
            "local_default",
            conversation.session_id,
            files_route.FileCreateRequest(path="notes.md", content="v2"),
            current_user=_build_user(),
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_copy_file_copies_nested_file_in_workspace_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    _patch_file_route_workspace(monkeypatch, tmp_path, service)

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-copy-file",
        title="任务 Copy File",
        initial_conversation_id="conversation-copy-file-001",
        initial_conversation_title="复制文件对话",
    )
    conversation = workspace.current_conversation
    assert conversation is not None

    workspace_dir = service._get_workspace_dir("local_default", "task-copy-file")
    source = workspace_dir / "reports" / "source.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# source\n", encoding="utf-8")

    response = await files_route.copy_file(
        "local_default",
        conversation.session_id,
        files_route.FileCopyRequest(
            source="reports/source.md",
            target="reports/source copy.md",
        ),
        current_user=_build_user(),
    )

    target = workspace_dir / "reports" / "source copy.md"
    assert response.success is True
    assert response.target == "reports/source copy.md"
    assert source.read_text(encoding="utf-8") == "# source\n"
    assert target.read_text(encoding="utf-8") == "# source\n"


@pytest.mark.asyncio
async def test_copy_folder_rejects_target_inside_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    _patch_file_route_workspace(monkeypatch, tmp_path, service)

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-copy-folder",
        title="任务 Copy Folder",
        initial_conversation_id="conversation-copy-folder-001",
        initial_conversation_title="复制文件夹对话",
    )
    conversation = workspace.current_conversation
    assert conversation is not None

    workspace_dir = service._get_workspace_dir("local_default", "task-copy-folder")
    source = workspace_dir / "reports"
    source.mkdir(parents=True, exist_ok=True)
    (source / "source.md").write_text("# source\n", encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        await files_route.copy_file(
            "local_default",
            conversation.session_id,
            files_route.FileCopyRequest(
                source="reports",
                target="reports/copy",
            ),
            current_user=_build_user(),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_workspace_mcp_config_file_is_listed_from_config_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    _patch_file_route_workspace(monkeypatch, tmp_path, service)

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-mcp-config-file",
        title="任务 MCP Config",
        initial_conversation_id="conversation-mcp-config-001",
        initial_conversation_title="MCP 配置对话",
    )
    conversation = workspace.current_conversation
    assert conversation is not None

    workspace_dir = service._get_workspace_dir("local_default", "task-mcp-config-file")
    mounted_file = workspace_dir / ".aiasys" / "mcp_config.json"
    mounted_content = '{"version": 1, "servers": {}}'
    mounted_file.parent.mkdir(parents=True, exist_ok=True)
    mounted_file.write_text(mounted_content, encoding="utf-8")

    listing = await _list_workspace_files(
        workspace.workspace_id,
        recursive=True,
    )
    # .aiasys 是内部配置目录，workspace 文件列表不列出其中文件
    assert not any(item["name"] == ".aiasys/mcp_config.json" for item in listing["files"])


@pytest.mark.asyncio
async def test_admin_list_all_files_returns_absolute_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    _patch_file_route_workspace(monkeypatch, tmp_path, service)

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-admin-list-all",
        title="任务 Admin List All",
        initial_conversation_id="conversation-admin-list-all-001",
        initial_conversation_title="管理员文件总览",
    )
    conversation = workspace.current_conversation
    assert conversation is not None

    workspace_dir = service._get_workspace_dir("local_default", "task-admin-list-all")
    listed_file = workspace_dir / "reports" / "summary.md"
    listed_file.parent.mkdir(parents=True, exist_ok=True)
    listed_file.write_text("# summary\n", encoding="utf-8")

    payload = await files_core_route.list_all_files(current_user=_build_user())

    target_file = next(
        item
        for item in payload["files"]
        if item["session_id"] == "task-admin-list-all" and item["name"] == "reports/summary.md"
    )
    assert target_file == {
        "user_id": "local_default",
        "session_id": "task-admin-list-all",
        "name": "reports/summary.md",
        "size": len("# summary\n".encode("utf-8")),
        "modified": listed_file.stat().st_mtime,
        "absolute_path": str(listed_file.absolute()),
    }


@pytest.mark.asyncio
async def test_list_files_returns_sqlite_resource_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    _patch_file_route_workspace(monkeypatch, tmp_path, service)

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-resource-db-file",
        title="资源 DB 文件",
        initial_conversation_id="conversation-resource-db-file-001",
        initial_conversation_title="资源 DB 对话",
    )
    conversation = workspace.current_conversation
    assert conversation is not None

    workspace_dir = service._get_workspace_dir("local_default", "task-resource-db-file")
    db_path = workspace_dir / "knowledge" / "product-docs.knowledge.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE _aiasys_metadata (key TEXT PRIMARY KEY, value TEXT)")
        conn.executemany(
            "INSERT INTO _aiasys_metadata (key, value) VALUES (?, ?)",
            [
                ("resource_type", "knowledge"),
                ("schema_kind", "aiasys.knowledge_base.sqlite.v1"),
                ("preview_kind", "knowledge_base"),
                ("renderer_hint", "knowledge_base_preview"),
                ("id", "kb-product-docs"),
                ("document_count", "12"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    listing = await _list_workspace_files(
        workspace.workspace_id,
        recursive=True,
    )

    db_file = next(
        item for item in listing["files"] if item["name"] == "knowledge/product-docs.knowledge.db"
    )
    assert db_file["resource_type"] == "knowledge"
    assert db_file["schema_kind"] == "aiasys.knowledge_base.sqlite.v1"
    assert db_file["preview_kind"] == "knowledge_base"
    assert db_file["renderer_hint"] == "knowledge_base_preview"
    assert db_file["meta"]["id"] == "kb-product-docs"
    assert db_file["meta"]["document_count"] == 12
    assert db_file["meta"]["db_path"] == "/workspace/knowledge/product-docs.knowledge.db"


@pytest.mark.asyncio
async def test_ipynb_file_is_editable_via_workspace_file_content_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    _patch_file_route_workspace(monkeypatch, tmp_path, service)

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-notebook-edit-file",
        title="任务 Notebook File",
        initial_conversation_id="conversation-notebook-file-001",
        initial_conversation_title="Notebook 文件对话",
    )
    conversation = workspace.current_conversation
    assert conversation is not None

    workspace_dir = service._get_workspace_dir("local_default", "task-notebook-edit-file")
    notebook_path = workspace_dir / "notebooks" / "analysis.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_payload = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": "# Demo",
            }
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    notebook_path.write_text(
        json.dumps(notebook_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    content = await files_route.get_file_content(
        "local_default",
        conversation.session_id,
        "notebooks/analysis.ipynb",
        current_user=_build_user(),
    )
    assert content.editable is True
    assert '"nbformat": 4' in content.content

    updated_payload = {
        **notebook_payload,
        "metadata": {"title": "Notebook Edit"},
    }
    update_response = await files_route.update_file_content(
        "local_default",
        conversation.session_id,
        "notebooks/analysis.ipynb",
        files_route.FileContentRequest(
            content=json.dumps(updated_payload, ensure_ascii=False, indent=2) + "\n"
        ),
        current_user=_build_user(),
    )
    assert update_response["success"] is True
    private_notebook_path = (
        service.get_session_dir("local_default", conversation.session_id)
        / "notebooks"
        / "analysis.ipynb"
    )
    assert private_notebook_path.exists()

    workspace_payload = json.loads(notebook_path.read_text(encoding="utf-8"))
    saved_payload = json.loads(private_notebook_path.read_text(encoding="utf-8"))
    assert workspace_payload["metadata"] == {}
    assert saved_payload["metadata"]["title"] == "Notebook Edit"


@pytest.mark.asyncio
async def test_bound_workspace_listing_prefers_session_private_notebook_over_workspace_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    _patch_file_route_workspace(monkeypatch, tmp_path, service)

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-notebook-listing",
        title="任务 Notebook Listing",
        initial_conversation_id="conversation-notebook-listing-001",
        initial_conversation_title="Notebook Listing 对话",
    )
    conversation = workspace.current_conversation
    assert conversation is not None

    workspace_dir = service._get_workspace_dir("local_default", "task-notebook-listing")
    workspace_notebook_path = workspace_dir / "notebooks" / "analysis.ipynb"
    workspace_notebook_path.parent.mkdir(parents=True, exist_ok=True)
    workspace_notebook_path.write_text("workspace", encoding="utf-8")
    (workspace_dir / "notes.txt").write_text("shared", encoding="utf-8")

    session_dir = service.get_session_dir("local_default", conversation.session_id)
    session_notebook_path = session_dir / "notebooks" / "analysis.ipynb"
    session_notebook_path.parent.mkdir(parents=True, exist_ok=True)
    session_notebook_path.write_text("session", encoding="utf-8")

    listing = await _list_workspace_files(
        workspace.workspace_id,
        recursive=True,
    )

    names = [item["name"] for item in listing["files"]]
    assert names.count("notebooks/analysis.ipynb") == 1
    assert "notes.txt" in names

    content = await files_route.get_file_content(
        "local_default",
        conversation.session_id,
        "notebooks/analysis.ipynb",
        current_user=_build_user(),
    )
    assert content.content == "session"


@pytest.mark.asyncio
async def test_running_session_rejects_manual_notebook_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    _patch_file_route_workspace(monkeypatch, tmp_path, service)
    monkeypatch.setattr(
        files_utils_route,
        "_is_runtime_busy_for_session",
        lambda user_id, session_id: True,
    )

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-notebook-lock",
        title="任务 Notebook Lock",
        initial_conversation_id="conversation-notebook-lock-001",
        initial_conversation_title="Notebook Lock 对话",
    )
    conversation = workspace.current_conversation
    assert conversation is not None

    session_notebook_path = (
        service.get_session_dir("local_default", conversation.session_id)
        / "notebooks"
        / "analysis.ipynb"
    )
    session_notebook_path.parent.mkdir(parents=True, exist_ok=True)
    session_notebook_path.write_text("{}", encoding="utf-8")

    response = await files_route.get_file_content(
        "local_default",
        conversation.session_id,
        "notebooks/analysis.ipynb",
        current_user=_build_user(),
    )
    assert response.editable is False
    assert response.edit_lock_reason is not None

    with pytest.raises(HTTPException) as exc_info:
        await files_route.update_file_content(
            "local_default",
            conversation.session_id,
            "notebooks/analysis.ipynb",
            files_route.FileContentRequest(content="{}"),
            current_user=_build_user(),
        )

    assert exc_info.value.status_code == 409
