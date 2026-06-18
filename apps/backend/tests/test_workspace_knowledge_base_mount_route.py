from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.routes import workspaces_resources_mounts as workspace_route
from app.models.user import UserInfo
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_service(tmp_path: Path) -> WorkspaceRegistryService:
    return WorkspaceRegistryService(tmp_path, session_manager=SessionManager(tmp_path))


class FakeKnowledgeService:
    def list_knowledge_bases(self, user_id: str):
        assert user_id == "local_default"
        return [
            SimpleNamespace(id="kb-a", name="知识库 A", document_count=2),
            SimpleNamespace(id="kb-b", name="知识库 B", document_count=5),
        ]


@pytest.mark.asyncio
async def test_workspace_knowledge_base_mount_routes_returns_all_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """知识库已取消挂载，GET/PUT 都返回全部可用知识库。"""
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspace_route,
        "get_workspace_registry_service",
        lambda: service,
    )

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-kb",
        title="任务知识库",
        initial_conversation_title="当前对话",
    )

    import app.knowledge as knowledge_module

    monkeypatch.setattr(
        knowledge_module,
        "get_sqlite_kb_service",
        lambda: FakeKnowledgeService(),
    )

    result = await workspace_route.get_workspace_knowledge_base_mounts(
        "task-kb",
        current_user=_build_user(),
    )
    # 取消挂载后，返回全部可用知识库
    assert result.knowledge_base_ids == ["kb-a", "kb-b"]
    assert [item.id for item in result.available_knowledge_bases] == ["kb-a", "kb-b"]
    assert all(item.mounted for item in result.available_knowledge_bases)

    # PUT 变为空操作，同样返回全部可用知识库
    updated = await workspace_route.update_workspace_knowledge_base_mounts(
        "task-kb",
        workspace_route.WorkspaceKnowledgeBaseMountRequest(
            knowledge_base_ids=["kb-b", "kb-a", "kb-b"]
        ),
        current_user=_build_user(),
    )
    assert updated.knowledge_base_ids == ["kb-a", "kb-b"]
    assert [item.id for item in updated.mounted_knowledge_bases] == ["kb-a", "kb-b"]


@pytest.mark.asyncio
async def test_workspace_knowledge_base_mount_routes_put_no_longer_rejects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """知识库已取消挂载，PUT 不再校验 ID，直接返回全部可用知识库。"""
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspace_route,
        "get_workspace_registry_service",
        lambda: service,
    )

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-kb-invalid",
        title="任务知识库",
        initial_conversation_title="当前对话",
    )

    import app.knowledge as knowledge_module

    monkeypatch.setattr(
        knowledge_module,
        "get_sqlite_kb_service",
        lambda: FakeKnowledgeService(),
    )

    # PUT 不再 reject unknown IDs，而是返回全部可用知识库
    updated = await workspace_route.update_workspace_knowledge_base_mounts(
        "task-kb-invalid",
        workspace_route.WorkspaceKnowledgeBaseMountRequest(knowledge_base_ids=["kb-missing"]),
        current_user=_build_user(),
    )
    assert updated.knowledge_base_ids == ["kb-a", "kb-b"]
