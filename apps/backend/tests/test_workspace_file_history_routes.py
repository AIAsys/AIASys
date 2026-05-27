from __future__ import annotations

from pathlib import Path

import pytest

from app.api.routes import workspaces_resources_files as files_route
from app.api.routes.files_utils import FileContentRequest, FileCreateRequest, FileMoveRequest
from app.core import config as config_module
from app.models.user import UserInfo
from app.services import workspace_registry as workspace_registry_module
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _patch_roots(
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
        files_route,
        "get_workspace_registry_service",
        lambda: service,
    )


@pytest.mark.asyncio
async def test_workspace_file_history_update_diff_and_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    service.create_workspace(
        user_id="local_default",
        workspace_id="history-workspace",
        title="文件历史工作区",
    )
    _patch_roots(monkeypatch, tmp_path, service)
    user = _build_user()

    created = await files_route.create_workspace_file(
        "history-workspace",
        FileCreateRequest(path="docs/notes.md", content="old\n"),
        current_user=user,
    )
    assert created.overwritten is False

    updated = await files_route.update_workspace_file_content(
        "history-workspace",
        "docs/notes.md",
        FileContentRequest(content="new\n"),
        current_user=user,
    )
    assert updated["success"] is True

    history = await files_route.list_workspace_file_history(
        "history-workspace",
        "docs/notes.md",
        current_user=user,
    )
    assert history.scope == "workspace"
    assert history.filename == "docs/notes.md"
    assert len(history.entries) == 1
    entry = history.entries[0]
    assert entry.operation == "before_update"

    content = await files_route.get_workspace_file_history_content(
        "history-workspace",
        entry.id,
        current_user=user,
    )
    assert content.content == "old\n"

    diff = await files_route.get_workspace_file_history_diff(
        "history-workspace",
        entry.id,
        current_user=user,
    )
    assert diff.current_exists is True
    assert "-old\n" in diff.diff
    assert "+new\n" in diff.diff
    assert diff.status == "modified"
    assert diff.left_label == "history/docs/notes.md"
    assert diff.right_label == "current/docs/notes.md"
    assert diff.left_text == "old\n"
    assert diff.right_text == "new\n"
    assert diff.additions == 1
    assert diff.deletions == 1

    restored = await files_route.restore_workspace_file_history_entry(
        "history-workspace",
        entry.id,
        current_user=user,
    )
    workspace_file = tmp_path / "local_default" / "history-workspace" / "docs" / "notes.md"
    assert restored.success is True
    assert restored.filename == "docs/notes.md"
    assert workspace_file.read_text(encoding="utf-8") == "old\n"

    after_restore = await files_route.list_workspace_file_history(
        "history-workspace",
        "docs/notes.md",
        current_user=user,
    )
    assert any(entry.operation == "before_restore" for entry in after_restore.entries)


@pytest.mark.asyncio
async def test_global_file_history_follows_move_and_records_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    service.create_workspace(
        user_id="local_default",
        workspace_id="global-history-workspace",
        title="全局文件历史工作区",
    )
    _patch_roots(monkeypatch, tmp_path, service)
    user = _build_user()

    await files_route.create_global_workspace_file(
        "global-history-workspace",
        FileCreateRequest(path="shared.md", content="one\n"),
        current_user=user,
    )
    await files_route.update_global_workspace_file_content(
        "global-history-workspace",
        "shared.md",
        FileContentRequest(content="two\n"),
        current_user=user,
    )
    moved = await files_route.move_global_workspace_file(
        "global-history-workspace",
        FileMoveRequest(source="shared.md", target="docs/shared.md"),
        current_user=user,
    )
    assert moved.success is True

    old_path_history = await files_route.list_global_workspace_file_history(
        "global-history-workspace",
        "shared.md",
        current_user=user,
    )
    new_path_history = await files_route.list_global_workspace_file_history(
        "global-history-workspace",
        "docs/shared.md",
        current_user=user,
    )
    assert old_path_history.entries == []
    assert {entry.operation for entry in new_path_history.entries} >= {
        "before_update",
        "before_move",
    }

    deleted = await files_route.delete_global_workspace_file(
        "global-history-workspace",
        "docs/shared.md",
        current_user=user,
    )
    assert deleted["success"] is True

    after_delete = await files_route.list_global_workspace_file_history(
        "global-history-workspace",
        "docs/shared.md",
        current_user=user,
    )
    assert any(entry.operation == "before_delete" for entry in after_delete.entries)
