from __future__ import annotations

from pathlib import Path

import pytest

from app.api.routes import diff as diff_route
from app.models.user import UserInfo
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


@pytest.mark.asyncio
async def test_text_diff_route_returns_unified_response() -> None:
    response = await diff_route.compare_text_diff(
        diff_route.TextDiffRequest(
            left=diff_route.TextDiffSide(content="old\n", label="old.md"),
            right=diff_route.TextDiffSide(content="new\n", label="new.md"),
        ),
        current_user=_build_user(),
    )

    assert response.status == "modified"
    assert response.left_label == "old.md"
    assert response.right_label == "new.md"
    assert "-old\n" in response.unified_diff
    assert "+new\n" in response.unified_diff


@pytest.mark.asyncio
async def test_file_diff_route_resolves_workspace_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    service.create_workspace(
        user_id="local_default",
        workspace_id="diff-workspace",
        title="差异工作区",
    )
    monkeypatch.setattr(
        diff_route,
        "get_workspace_registry_service",
        lambda: service,
    )

    workspace_root = service.get_workspace_root("local_default", "diff-workspace")
    (workspace_root / "left.md").write_text("old\n", encoding="utf-8")
    (workspace_root / "right.md").write_text("new\n", encoding="utf-8")

    response = await diff_route.compare_file_diff(
        diff_route.FileDiffRequest(
            left=diff_route.DiffPathRef(
                scope="workspace",
                workspace_id="diff-workspace",
                path="left.md",
            ),
            right=diff_route.DiffPathRef(
                scope="workspace",
                workspace_id="diff-workspace",
                path="right.md",
            ),
        ),
        current_user=_build_user(),
    )

    assert response.status == "modified"
    assert response.left_exists is True
    assert response.right_exists is True
    assert "-old\n" in response.unified_diff
    assert "+new\n" in response.unified_diff
