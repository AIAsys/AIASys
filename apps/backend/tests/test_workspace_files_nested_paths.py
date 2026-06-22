from __future__ import annotations

import asyncio
import importlib.util
import io
import shutil
import uuid
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.routes import workspaces as workspaces_route
from app.api.routes import workspaces_resources_files as workspace_files_route
from app.core.config import WORKSPACE_DIR
from app.models.user import UserInfo
from app.services.memory.resolver import (
    get_workspace_memory_file_path,
)
from app.services.memory.store import MemoryStore
from app.services.workspace_registry import WorkspaceRegistryService

TEST_USER_ID = "nested_paths_test_user"
FILES_ROUTE_PATH = Path(__file__).resolve().parent.parent / "app/api/routes/files.py"
FILES_ROUTE_SPEC = importlib.util.spec_from_file_location(
    "workspace_files_route_test",
    FILES_ROUTE_PATH,
)
assert FILES_ROUTE_SPEC and FILES_ROUTE_SPEC.loader
files_module = importlib.util.module_from_spec(FILES_ROUTE_SPEC)
FILES_ROUTE_SPEC.loader.exec_module(files_module)
CURRENT_USER = UserInfo(
    user_id=TEST_USER_ID,
    role="admin",
    auth_provider="none",
)


async def _list_workspace_files(
    workspace_id: str,
    **kwargs: object,
) -> dict[str, object]:
    response = await workspace_files_route.list_workspace_files(
        workspace_id,
        current_user=CURRENT_USER,
        **kwargs,
    )
    payload = response.model_dump(exclude_none=True)
    payload["files"] = [
        {key: value for key, value in item.items() if not (key == "meta" and value == {})}
        for item in payload["files"]
    ]
    return payload


@pytest.fixture
def workspace_case():
    workspace_id = f"nested-workspace-{uuid.uuid4().hex[:8]}"
    session_id = f"nested-paths-{uuid.uuid4().hex[:8]}"
    service = WorkspaceRegistryService(WORKSPACE_DIR)
    service.create_workspace(
        user_id=TEST_USER_ID,
        title="Nested Path Files",
        workspace_id=workspace_id,
        initial_conversation_id=session_id,
    )
    workspace_dir = service.get_workspace_root(TEST_USER_ID, workspace_id)

    nested_markdown = workspace_dir / "kb_documents" / "001_report.md"
    nested_markdown.parent.mkdir(parents=True, exist_ok=True)
    nested_markdown.write_text("# nested report\n", encoding="utf-8")

    nested_csv = workspace_dir / "kb_documents" / "metrics" / "fault_features.csv"
    nested_csv.parent.mkdir(parents=True, exist_ok=True)
    nested_csv.write_text("feature,value\namp,1\n", encoding="utf-8")

    dot_dir_file = workspace_dir / ".secret" / "token.txt"
    dot_dir_file.parent.mkdir(parents=True, exist_ok=True)
    dot_dir_file.write_text("shown like a normal workspace file", encoding="utf-8")

    internal_file = workspace_dir / ".aiasys" / "session" / "trace.jsonl"
    internal_file.parent.mkdir(parents=True, exist_ok=True)
    internal_file.write_text("internal", encoding="utf-8")

    try:
        yield {
            "workspace_id": workspace_id,
            "session_id": session_id,
            "workspace_dir": workspace_dir,
            "nested_markdown": nested_markdown,
            "nested_csv": nested_csv,
        }
    finally:
        shutil.rmtree(WORKSPACE_DIR / TEST_USER_ID / workspace_id, ignore_errors=True)
        shutil.rmtree(WORKSPACE_DIR / TEST_USER_ID / session_id, ignore_errors=True)


def test_list_files_returns_nested_relative_paths(workspace_case) -> None:
    payload = asyncio.run(
        _list_workspace_files(
            workspace_case["workspace_id"],
            recursive=True,
        )
    )

    names = sorted(item["name"] for item in payload["files"])

    assert names == [
        ".secret/token.txt",
        "kb_documents/001_report.md",
        "kb_documents/metrics/fault_features.csv",
    ]


def test_nested_file_endpoints_support_read_update_delete_and_export(workspace_case) -> None:
    session_id = workspace_case["session_id"]
    nested_path = "kb_documents/001_report.md"

    download_response = asyncio.run(
        files_module.download_file(
            TEST_USER_ID,
            session_id,
            nested_path,
            current_user=CURRENT_USER,
        )
    )
    assert Path(download_response.path) == workspace_case["nested_markdown"]

    content_response = asyncio.run(
        files_module.get_file_content(
            TEST_USER_ID,
            session_id,
            nested_path,
            CURRENT_USER,
        )
    )
    assert content_response.filename == nested_path
    assert content_response.content == "# nested report\n"

    update_response = asyncio.run(
        files_module.update_file_content(
            TEST_USER_ID,
            session_id,
            nested_path,
            files_module.FileContentRequest(content="# updated\n"),
            CURRENT_USER,
        )
    )
    assert update_response["success"] is True
    assert workspace_case["nested_markdown"].read_text(encoding="utf-8") == "# updated\n"

    delete_response = asyncio.run(
        files_module.delete_file(
            TEST_USER_ID,
            session_id,
            nested_path,
            current_user=CURRENT_USER,
        )
    )
    assert delete_response["success"] is True
    assert not workspace_case["nested_markdown"].exists()


def test_dot_dir_file_can_be_read_but_internal_dir_is_blocked(
    workspace_case,
) -> None:
    session_id = workspace_case["session_id"]

    content_response = asyncio.run(
        files_module.get_file_content(
            TEST_USER_ID,
            session_id,
            ".secret/token.txt",
            CURRENT_USER,
        )
    )
    assert content_response.filename == ".secret/token.txt"
    assert content_response.content == "shown like a normal workspace file"

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            files_module.get_file_content(
                TEST_USER_ID,
                session_id,
                ".aiasys/session/trace.jsonl",
                CURRENT_USER,
            )
        )

    assert exc_info.value.status_code == 403


def test_export_workspace_zip_includes_nested_paths(workspace_case) -> None:
    response = asyncio.run(
        files_module.export_workspace(
            TEST_USER_ID,
            workspace_case["session_id"],
            CURRENT_USER,
        )
    )

    body = b""

    async def _read_body() -> bytes:
        nonlocal body
        async for chunk in response.body_iterator:
            body += chunk
        return body

    archive_bytes = asyncio.run(_read_body())
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        names = sorted(archive.namelist())

    assert names == [
        ".secret/token.txt",
        "kb_documents/001_report.md",
        "kb_documents/metrics/fault_features.csv",
    ]


def test_export_markdown_document_supports_md_docx_pdf(monkeypatch, workspace_case) -> None:
    session_id = workspace_case["session_id"]
    nested_path = "kb_documents/001_report.md"

    md_response = asyncio.run(
        files_module.export_markdown_document(
            TEST_USER_ID,
            session_id,
            nested_path,
            "md",
            CURRENT_USER,
        )
    )
    assert Path(md_response.path) == workspace_case["nested_markdown"]

    def fake_export_markdown_file_to_path(source_path: Path, output_format: str):
        output_path = source_path.with_suffix(f".{output_format}")
        output_path.write_bytes(f"{output_format}-binary".encode("utf-8"))
        return (
            output_path,
            f"{source_path.stem}.{output_format}",
            "application/octet-stream",
        )

    import app.api.routes.files_core as files_core_module

    monkeypatch.setattr(
        files_core_module,
        "export_markdown_file_to_path",
        fake_export_markdown_file_to_path,
    )

    for export_format in ("docx", "pdf"):
        response = asyncio.run(
            files_module.export_markdown_document(
                TEST_USER_ID,
                session_id,
                nested_path,
                export_format,
                CURRENT_USER,
            )
        )

        payload = Path(response.path).read_bytes()
        assert payload == f"{export_format}-binary".encode("utf-8")
        assert response.headers["content-disposition"].endswith(f'"001_report.{export_format}"')


def test_export_markdown_document_rejects_non_markdown(workspace_case) -> None:
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            files_module.export_markdown_document(
                TEST_USER_ID,
                workspace_case["session_id"],
                "kb_documents/metrics/fault_features.csv",
                "pdf",
                CURRENT_USER,
            )
        )

    assert exc_info.value.status_code == 400


def test_nested_file_endpoints_reject_path_traversal(workspace_case) -> None:
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            files_module.download_file(
                TEST_USER_ID,
                workspace_case["session_id"],
                "../config.json",
                current_user=CURRENT_USER,
            )
        )

    assert exc_info.value.status_code == 400


@pytest.fixture
def workspace_memory_case():
    workspace_id = f"workspace-memory-{uuid.uuid4().hex[:8]}"
    session_id = f"workspace-memory-session-{uuid.uuid4().hex[:8]}"
    service = WorkspaceRegistryService(WORKSPACE_DIR)
    original_get_workspace_registry_service = workspaces_route.get_workspace_registry_service
    workspaces_route.get_workspace_registry_service = lambda: service
    service.create_workspace(
        user_id=TEST_USER_ID,
        title="Workspace Memory Files",
        workspace_id=workspace_id,
        initial_conversation_id=session_id,
    )
    workspace_root = service.get_workspace_root(TEST_USER_ID, workspace_id)
    session_root = WORKSPACE_DIR / TEST_USER_ID / session_id

    try:
        yield {
            "workspace_id": workspace_id,
            "session_id": session_id,
            "workspace_root": workspace_root,
            "session_root": session_root,
        }
    finally:
        workspaces_route.get_workspace_registry_service = original_get_workspace_registry_service
        shutil.rmtree(WORKSPACE_DIR / TEST_USER_ID / workspace_id, ignore_errors=True)
        shutil.rmtree(WORKSPACE_DIR / TEST_USER_ID / session_id, ignore_errors=True)


def test_workspace_memory_mirror_writes_workspace_root(
    workspace_memory_case,
) -> None:
    session_id = workspace_memory_case["session_id"]

    asyncio.run(
        files_module.update_file_content(
            TEST_USER_ID,
            session_id,
            "记忆/工作区记忆.md",
            files_module.FileContentRequest(
                content="## 长期目标\n- 统一工作区术语\n",
            ),
            CURRENT_USER,
        )
    )

    workspace_mirror = workspace_memory_case["workspace_root"] / "记忆" / "工作区记忆.md"
    assert workspace_mirror.read_text(encoding="utf-8").startswith("## 长期目标")

    workspace_store = MemoryStore(
        get_workspace_memory_file_path(workspace_memory_case["workspace_root"])
    )
    assert workspace_store.read_text().startswith("## 长期目标")

    listed_files = asyncio.run(
        _list_workspace_files(
            workspace_memory_case["workspace_id"],
            recursive=True,
        )
    )
    listed_names = sorted(item["name"] for item in listed_files["files"])
    assert "记忆/工作区记忆.md" in listed_names
