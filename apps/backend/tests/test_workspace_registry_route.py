from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from app.api.routes import workspaces_core as workspace_route
from app.models.database_connector import DatabaseConnectorDraft
from app.models.session import StructuredMessage
from app.models.task_profile import ExecutionPolicyMode, TaskExecutionPolicy
from app.models.user import UserInfo
from app.models.workspace import WorkspaceRuntimeBinding
from app.services.connector import DatabaseConnectorService
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService
from app.services.history.session_execution_journal import SessionExecutionJournal
from app.services.session.config_projection import write_workspace_database_mount_data


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_service(tmp_path: Path) -> WorkspaceRegistryService:
    return WorkspaceRegistryService(tmp_path, session_manager=SessionManager(tmp_path))


def test_workspace_registry_generates_short_workspace_id(tmp_path: Path) -> None:
    service = _build_service(tmp_path)

    created = service.create_workspace(
        user_id="local_default",
        title="短 ID 工作区",
    )

    assert re.fullmatch(r"[0-9a-f]{12}", created.workspace_id)
    assert (
        tmp_path
        / "local_default"
        / created.workspace_id
        / ".aiasys"
        / "workspace"
        / "workspace.json"
    ).exists()


def _create_database_connector(
    tmp_path: Path,
    session_manager: SessionManager,
    *,
    name: str,
    database_name: str,
) -> str:
    connector_service = DatabaseConnectorService(
        tmp_path,
        session_manager=session_manager,
    )
    connector = connector_service.create_connector(
        "local_default",
        DatabaseConnectorDraft(
            name=name,
            db_type="postgres",
            connection_mode="fields",
            host="127.0.0.1",
            database_name=database_name,
            username="demo",
            password="secret",
            readonly=True,
            allowed_schemas=[],
            allowed_tables=[],
            query_timeout_seconds=15,
            row_limit=1000,
            default_grants=["schema_read", "data_read"],
            capability_upper_bound=["schema_read", "data_read"],
            default_approval_policy="none",
        ),
    )
    return connector.connector_id


@pytest.mark.asyncio
async def test_workspace_route_creates_workspace_with_initial_conversation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(workspace_route, "get_workspace_registry_service", lambda: service)

    response = await workspace_route.create_workspace(
        workspace_route.CreateWorkspaceRequest(
            workspace_id="task-alpha",
            title="任务 Alpha",
            description="用于验证工作区描述写入",
            initial_conversation_title="起始对话",
        ),
        current_user=_build_user(),
    )

    assert response.workspace_id == "task-alpha"
    assert response.title == "任务 Alpha"
    assert response.description == "用于验证工作区描述写入"
    assert response.conversation_count == 1
    assert response.current_conversation is not None
    assert response.current_conversation.title == "起始对话"
    assert response.runtime_binding.sandbox_mode is None
    assert response.runtime_binding.env_id is None
    assert (tmp_path / "local_default" / "task-alpha" / ".aiasys" / "workspace" / "workspace.json").exists()
    assert not (tmp_path / "local_default" / "task-alpha" / "env" / "environments.json").exists()

    metadata = service.session_manager.get_session(
        response.current_conversation.session_id,
        "local_default",
    )
    assert metadata is not None
    assert metadata.sandbox_mode is None
    assert metadata.env_id is None
    workspace_root = tmp_path / "local_default" / "task-alpha"
    user_soul = (
        tmp_path
        / "local_default"
        / "global_workspace"
        / ".aiasys"
        / "agent_config"
        / "soul.md"
    )
    project_profile = workspace_root / ".aiasys" / "project_profile.md"
    workspace_memory = workspace_root / ".aiasys" / "memory" / "workspace_memory.md"
    assert user_soul.exists()
    assert project_profile.exists()
    assert workspace_memory.exists()
    assert "Agent Soul" in user_soul.read_text(encoding="utf-8")
    assert "任务 Alpha" in project_profile.read_text(encoding="utf-8")
    assert "用于验证工作区描述写入" in project_profile.read_text(encoding="utf-8")
    assert "长期目标" in workspace_memory.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_workspace_route_accepts_requested_initial_conversation_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(workspace_route, "get_workspace_registry_service", lambda: service)

    response = await workspace_route.create_workspace(
        workspace_route.CreateWorkspaceRequest(
            workspace_id="task-fixed-conversation",
            title="任务 Fixed",
            initial_conversation_id="conversation-fixed-001",
            initial_conversation_title="固定首对话",
        ),
        current_user=_build_user(),
    )

    assert response.current_conversation is not None
    assert response.current_conversation.conversation_id == "conversation-fixed-001"
    assert response.current_conversation.session_id == "conversation-fixed-001"


@pytest.mark.asyncio
async def test_workspace_route_lists_workspaces_and_conversations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(workspace_route, "get_workspace_registry_service", lambda: service)

    created = service.create_workspace(
        user_id="local_default",
        workspace_id="task-beta",
        title="任务 Beta",
        description="列表描述",
        initial_conversation_title="默认对话",
    )
    service.create_conversation(
        user_id="local_default",
        workspace_id="task-beta",
        title="第二个对话",
    )

    workspaces = await workspace_route.list_workspaces(current_user=_build_user())
    workspace_detail = await workspace_route.get_workspace(
        "task-beta",
        current_user=_build_user(),
    )
    conversations = await workspace_route.list_workspace_conversations(
        "task-beta",
        current_user=_build_user(),
    )

    assert workspaces.total == 1
    assert workspaces.workspaces[0].workspace_id == "task-beta"
    assert workspaces.workspaces[0].description == "列表描述"
    assert workspaces.workspaces[0].conversation_count == 2
    assert workspaces.workspaces[0].current_conversation is not None
    assert workspaces.workspaces[0].conversations == []
    assert len(workspace_detail.conversations) == 2
    assert {item.title for item in workspace_detail.conversations} == {
        "默认对话",
        "第二个对话",
    }
    assert conversations.total == 2
    assert {item.title for item in conversations.conversations} == {"默认对话", "第二个对话"}
    assert created.current_conversation is not None


@pytest.mark.asyncio
async def test_workspace_route_lists_conversation_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(workspace_route, "get_workspace_registry_service", lambda: service)

    detail = service.create_workspace(
        user_id="local_default",
        workspace_id="task-runs",
        title="任务 Runs",
        initial_conversation_title="运行对话",
    )
    conversation = detail.current_conversation
    assert conversation is not None

    session_dir = tmp_path / "local_default" / conversation.session_id
    journal = SessionExecutionJournal(session_dir, conversation.session_id)
    journal.append_record(
        code="print('hello')",
        started_at="2026-04-05T02:00:00",
        finished_at="2026-04-05T02:00:01",
        status="completed",
        sandbox_mode="local",
        env_id="env-local",
        stdout="hello",
        stderr="",
        result_preview_text="hello",
    )

    runs = await workspace_route.list_conversation_runs(
        "task-runs",
        conversation.conversation_id,
        limit=50,
        current_user=_build_user(),
    )

    assert runs.total == 1
    assert runs.runs[0].code == "print('hello')"
    assert runs.runs[0].status == "completed"


@pytest.mark.asyncio
async def test_workspace_route_cleans_up_orphan_conversation_dirs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(workspace_route, "get_workspace_registry_service", lambda: service)

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-cleanup",
        title="任务 Cleanup",
        initial_conversation_title="绑定对话",
    )

    orphan_session_dir = tmp_path / "local_default" / "orphan-session"
    orphan_session_dir.mkdir(parents=True, exist_ok=True)
    (orphan_session_dir / ".aiasys" / "session").mkdir(parents=True, exist_ok=True)
    (orphan_session_dir / "workspace").mkdir(exist_ok=True)

    preview = await workspace_route.cleanup_orphan_conversations(
        dry_run=True,
        current_user=_build_user(),
    )
    assert preview.deleted_count == 0
    assert [item.session_id for item in preview.candidates] == ["orphan-session"]
    assert orphan_session_dir.exists()

    result = await workspace_route.cleanup_orphan_conversations(
        dry_run=False,
        current_user=_build_user(),
    )
    assert result.deleted_count == 1
    assert result.deleted_session_ids == ["orphan-session"]
    assert not orphan_session_dir.exists()


@pytest.mark.asyncio
async def test_workspace_route_forks_conversation_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(workspace_route, "get_workspace_registry_service", lambda: service)

    detail = service.create_workspace(
        user_id="local_default",
        workspace_id="task-fork",
        title="任务 Fork",
        initial_conversation_title="原始对话",
    )
    source = detail.current_conversation
    assert source is not None
    connector_id = _create_database_connector(
        tmp_path,
        service.session_manager,
        name="Fork Postgres",
        database_name="fork_demo",
    )
    connector_service = DatabaseConnectorService(
        tmp_path,
        session_manager=service.session_manager,
    )
    connector_service.attach_connector(
        "local_default",
        source.session_id,
        connector_id,
    )

    service.session_manager.add_message(
        source.session_id,
        "local_default",
        StructuredMessage(role="user", content="请继续分析这个问题"),
    )
    service.session_manager.add_message(
        source.session_id,
        "local_default",
        StructuredMessage(role="assistant", content="这是上一轮的分析结论"),
    )
    service.session_manager.add_message(
        source.session_id,
        "local_default",
        StructuredMessage(role="user", content="再给我一个后续行动建议"),
    )

    forked = await workspace_route.create_workspace_conversation(
        "task-fork",
        workspace_route.CreateConversationRequest(
          conversation_id="fork-conversation-001",
          title="Fork 对话",
          branched_from_conversation_id=source.conversation_id,
        ),
        current_user=_build_user(),
    )

    fork_history = service.session_manager.get_history(
        forked.session_id,
        "local_default",
    )
    forked_detail = await workspace_route.get_workspace(
        "task-fork",
        current_user=_build_user(),
    )
    forked_summary = next(
        item
        for item in forked_detail.conversations
        if item.conversation_id == forked.conversation_id
    )

    assert forked.branched_from_conversation_id == source.conversation_id
    assert len(fork_history) == 3
    assert [item["content"] for item in fork_history] == [
        "请继续分析这个问题",
        "这是上一轮的分析结论",
        "再给我一个后续行动建议",
    ]
    assert forked_summary.message_count == 3
    assert forked_summary.branched_from_conversation_id == source.conversation_id
    # 数据库连接器已改为全局资源，fork 时不再克隆 session_attachments


@pytest.mark.asyncio
async def test_workspace_route_new_conversation_inherits_workspace_default_database_mounts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(workspace_route, "get_workspace_registry_service", lambda: service)

    detail = service.create_workspace(
        user_id="local_default",
        workspace_id="task-db-defaults",
        title="任务数据库默认挂载",
        initial_conversation_title="原始对话",
    )
    assert detail.current_conversation is not None

    connector_id = _create_database_connector(
        tmp_path,
        service.session_manager,
        name="Workspace Default Postgres",
        database_name="workspace_default_demo",
    )
    write_workspace_database_mount_data(
        tmp_path / "local_default" / "task-db-defaults",
        {
            "version": 1,
            "connector_ids": [connector_id],
        },
    )

    created = await workspace_route.create_workspace_conversation(
        "task-db-defaults",
        workspace_route.CreateConversationRequest(
            conversation_id="conversation-db-default-001",
            title="带数据库默认挂载的新对话",
        ),
        current_user=_build_user(),
    )

    # 数据库连接器已改为全局资源，新建对话时不再按工作区挂载配置 attach
    connector_service = DatabaseConnectorService(
        tmp_path,
        session_manager=service.session_manager,
    )
    attachments = connector_service.list_session_attachments(
        "local_default",
        created.session_id,
    )
    assert attachments == []


@pytest.mark.asyncio
async def test_workspace_route_updates_workspace_policy_without_rewriting_existing_conversations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(workspace_route, "get_workspace_registry_service", lambda: service)

    detail = service.create_workspace(
        user_id="local_default",
        workspace_id="task-policy-sync",
        title="任务 Policy Sync",
        initial_conversation_title="原始会话",
    )
    source = detail.current_conversation
    assert source is not None

    sibling = service.create_conversation(
        user_id="local_default",
        workspace_id="task-policy-sync",
        title="第二会话",
    )

    updated = await workspace_route.update_workspace(
        "task-policy-sync",
        workspace_route.UpdateWorkspaceRequest(
            execution_policy=TaskExecutionPolicy(
                mode=ExecutionPolicyMode.AUTO_EXPLORE,
            ),
            runtime_binding=WorkspaceRuntimeBinding(
                sandbox_mode="local",
                env_id="python-research",
            ),
        ),
        current_user=_build_user(),
    )
    conversations = await workspace_route.list_workspace_conversations(
        "task-policy-sync",
        current_user=_build_user(),
    )

    assert updated.execution_policy.mode == ExecutionPolicyMode.AUTO_EXPLORE
    assert updated.runtime_binding.sandbox_mode == "local"
    assert updated.runtime_binding.env_id == "python-research"
    assert {
        item.execution_policy.mode for item in conversations.conversations
    } == {ExecutionPolicyMode.CHAT_ASSIST}

    source_meta = service.session_manager.get_session(source.session_id, "local_default")
    sibling_meta = service.session_manager.get_session(sibling.session_id, "local_default")
    assert source_meta is not None
    assert sibling_meta is not None
    assert source_meta.execution_policy.mode == ExecutionPolicyMode.CHAT_ASSIST
    assert sibling_meta.execution_policy.mode == ExecutionPolicyMode.CHAT_ASSIST
    assert source_meta.sandbox_mode is None
    assert sibling_meta.sandbox_mode is None
    assert source_meta.env_id is None
    assert sibling_meta.env_id is None

    created_after_update = await workspace_route.create_workspace_conversation(
        "task-policy-sync",
        workspace_route.CreateConversationRequest(
            conversation_id="conversation-after-mode-update",
            title="切换后的新会话",
        ),
        current_user=_build_user(),
    )
    assert created_after_update.execution_policy.mode == ExecutionPolicyMode.AUTO_EXPLORE
    created_after_update_meta = service.session_manager.get_session(
        created_after_update.session_id,
        "local_default",
    )
    assert created_after_update_meta is not None
    assert created_after_update_meta.sandbox_mode == "local"
    assert created_after_update_meta.env_id == "python-research"


@pytest.mark.asyncio
async def test_workspace_route_merges_runtime_binding_partial_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(workspace_route, "get_workspace_registry_service", lambda: service)

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-runtime-binding-merge",
        title="运行配置合并",
        runtime_binding=WorkspaceRuntimeBinding(
            sandbox_mode="local",
            env_id="workspace-default",
            env_vars={"OLD": "kept"},
        ),
    )

    updated = await workspace_route.update_workspace(
        "task-runtime-binding-merge",
        workspace_route.UpdateWorkspaceRequest(
            runtime_binding=WorkspaceRuntimeBinding(
                env_vars={"TOKEN": "workspace-value"},
            ),
        ),
        current_user=_build_user(),
    )

    assert updated.runtime_binding.sandbox_mode == "local"
    assert updated.runtime_binding.env_id == "workspace-default"
    assert updated.runtime_binding.env_vars == {"TOKEN": "workspace-value"}


@pytest.mark.asyncio
async def test_workspace_route_creates_conversation_with_explicit_execution_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(workspace_route, "get_workspace_registry_service", lambda: service)

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-explicit-policy",
        title="任务 Explicit Policy",
        initial_conversation_title="默认会话",
    )

    created = await workspace_route.create_workspace_conversation(
        "task-explicit-policy",
        workspace_route.CreateConversationRequest(
            conversation_id="analysis-branch-001",
            title="分析会话",
            execution_policy=TaskExecutionPolicy(
                mode=ExecutionPolicyMode.AUTO_EXPLORE,
            ),
        ),
        current_user=_build_user(),
    )

    metadata = service.session_manager.get_session(created.session_id, "local_default")
    assert metadata is not None
    assert created.execution_policy.mode == ExecutionPolicyMode.AUTO_EXPLORE
    assert metadata.execution_policy.mode == ExecutionPolicyMode.AUTO_EXPLORE


@pytest.mark.asyncio
async def test_workspace_route_creates_workspace_with_explicit_execution_policy_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(workspace_route, "get_workspace_registry_service", lambda: service)

    created = await workspace_route.create_workspace(
        workspace_route.CreateWorkspaceRequest(
            workspace_id="task-auto-explore",
            title="任务 Auto Explore",
            execution_policy=TaskExecutionPolicy(
                mode=ExecutionPolicyMode.AUTO_EXPLORE,
            ),
            runtime_binding=WorkspaceRuntimeBinding(
                sandbox_mode="local",
                env_id="workspace-default",
            ),
            initial_conversation_id="auto-explore-branch-001",
            initial_conversation_title="自动探索会话",
        ),
        current_user=_build_user(),
    )

    assert created.execution_policy.mode == ExecutionPolicyMode.AUTO_EXPLORE
    assert created.runtime_binding.sandbox_mode == "local"
    assert created.runtime_binding.env_id == "workspace-default"
    registry_path = (
        tmp_path
        / "local_default"
        / "task-auto-explore"
        / ".env"
        / "environments.json"
    )
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry["active_env_id"] == "workspace-default"
    assert registry["envs"][0]["active"] is True
    assert created.current_conversation is not None
    assert (
        created.current_conversation.execution_policy.mode
        == ExecutionPolicyMode.AUTO_EXPLORE
    )

    metadata = service.session_manager.get_session(
        "auto-explore-branch-001",
        "local_default",
    )
    assert metadata is not None
    assert metadata.execution_policy.mode == ExecutionPolicyMode.AUTO_EXPLORE
    assert metadata.sandbox_mode == "local"
    assert metadata.env_id == "workspace-default"


@pytest.mark.asyncio
async def test_workspace_route_new_conversation_inherits_workspace_execution_policy_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(workspace_route, "get_workspace_registry_service", lambda: service)

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-explicit-auto-explore",
        title="任务 Explicit Auto Explore",
        initial_conversation_title="默认会话",
        execution_policy=TaskExecutionPolicy(
            mode=ExecutionPolicyMode.AUTO_EXPLORE,
        ),
    )

    created = await workspace_route.create_workspace_conversation(
        "task-explicit-auto-explore",
        workspace_route.CreateConversationRequest(
            conversation_id="auto-explore-branch-001",
            title="自动探索会话",
        ),
        current_user=_build_user(),
    )

    metadata = service.session_manager.get_session(created.session_id, "local_default")
    assert metadata is not None
    assert created.execution_policy.mode == ExecutionPolicyMode.AUTO_EXPLORE
    assert metadata.execution_policy.mode == ExecutionPolicyMode.AUTO_EXPLORE


def test_create_workspace_with_template_applies_memory_and_env(tmp_path: Path) -> None:
    """测试模板创建时：memory 被复制，env_kind 推断默认 runtime_binding，template_id 被记录。"""
    service = _build_service(tmp_path)

    # 使用 data-analysis 模板，不传 runtime_binding
    created = service.create_workspace(
        user_id="local_default",
        title="数据分析任务",
        template_id="data-analysis",
    )

    # 1. template_id 被记录到 meta
    meta_path = (
        tmp_path
        / "local_default"
        / created.workspace_id
        / ".aiasys"
        / "workspace"
        / "workspace.json"
    )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta.get("template_id") == "data-analysis"

    # 2. workspace_memory.md 被复制
    memory_path = (
        tmp_path
        / "local_default"
        / created.workspace_id
        / ".aiasys"
        / "memory"
        / "workspace_memory.md"
    )
    assert memory_path.exists()
    content = memory_path.read_text(encoding="utf-8")
    assert "EDA" in content
    assert "pandas" in content

    # 3. 不传 runtime_binding 时不自动绑定环境（模板 env_kind 只作推荐提示）
    assert created.runtime_binding.sandbox_mode is None
    assert created.runtime_binding.env_id is None


def test_create_workspace_with_blank_template_no_memory_and_no_env(tmp_path: Path) -> None:
    """测试空白模板：不预置 memory，不绑定环境。"""
    service = _build_service(tmp_path)

    created = service.create_workspace(
        user_id="local_default",
        title="空白任务",
        template_id="blank-workspace",
    )

    # 1. template_id 被记录
    meta_path = (
        tmp_path
        / "local_default"
        / created.workspace_id
        / ".aiasys"
        / "workspace"
        / "workspace.json"
    )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta.get("template_id") == "blank-workspace"

    # 2. 不绑定环境
    assert created.runtime_binding.sandbox_mode is None
    assert created.runtime_binding.env_id is None

    # 3. memory 为默认内容（blank 模板没有 workspace_memory.md）
    memory_path = (
        tmp_path
        / "local_default"
        / created.workspace_id
        / ".aiasys"
        / "memory"
        / "workspace_memory.md"
    )
    assert memory_path.exists()
    content = memory_path.read_text(encoding="utf-8")
    assert "长期目标" in content


def test_create_workspace_explicit_runtime_binding_overrides_template_env_kind(
    tmp_path: Path,
) -> None:
    """测试显式传 runtime_binding 覆盖模板的 env_kind 推荐，但模板文件仍被应用。"""
    service = _build_service(tmp_path)

    # 选 data-analysis 模板（env_kind=uv），但显式指定不绑定环境
    created = service.create_workspace(
        user_id="local_default",
        title="数据分析但不绑定环境",
        template_id="data-analysis",
        runtime_binding=WorkspaceRuntimeBinding(
            sandbox_mode=None,
            env_id=None,
        ),
    )

    # 应以显式值为准，不绑定环境
    assert created.runtime_binding.sandbox_mode is None
    assert created.runtime_binding.env_id is None

    # memory 仍然被复制（模板文件应用不受 runtime_binding 影响）
    memory_path = (
        tmp_path
        / "local_default"
        / created.workspace_id
        / ".aiasys"
        / "memory"
        / "workspace_memory.md"
    )
    assert memory_path.exists()
    content = memory_path.read_text(encoding="utf-8")
    assert "EDA" in content
