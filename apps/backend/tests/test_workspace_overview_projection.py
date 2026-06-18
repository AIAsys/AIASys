from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import workspaces_core as workspace_route
from app.models.database_connector import DatabaseConnectorDraft
from app.models.expert import ExpertRoleSummary, WorkspaceExpertCatalogResponse
from app.models.user import UserInfo
from app.services.connector import DatabaseConnectorService
from app.services.history.session_execution_journal import SessionExecutionJournal
from app.services.session import SessionManager
from app.services.session.config_projection import (
    write_workspace_database_mount_data,
)
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_service(tmp_path: Path) -> WorkspaceRegistryService:
    return WorkspaceRegistryService(tmp_path, session_manager=SessionManager(tmp_path))


def _create_database_connector(
    tmp_path: Path,
    session_manager: SessionManager,
) -> str:
    connector_service = DatabaseConnectorService(
        tmp_path,
        session_manager=session_manager,
    )
    connector = connector_service.create_connector(
        "local_default",
        DatabaseConnectorDraft(
            name="Overview Postgres",
            db_type="postgres",
            connection_mode="fields",
            host="127.0.0.1",
            database_name="overview_demo",
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
async def test_workspace_overview_returns_backend_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(workspace_route, "get_workspace_registry_service", lambda: service)

    detail = service.create_workspace(
        user_id="local_default",
        workspace_id="task-overview",
        title="概览任务",
        initial_conversation_title="当前会话",
    )
    conversation = detail.current_conversation
    assert conversation is not None

    workspace_dir = tmp_path / "local_default" / "task-overview"
    (workspace_dir / "workspace").mkdir(parents=True, exist_ok=True)
    (workspace_dir / "workspace" / "report.md").write_text("hello", encoding="utf-8")
    (workspace_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (workspace_dir / "artifacts" / "chart.json").write_text("{}", encoding="utf-8")

    connector_id = _create_database_connector(tmp_path, service.session_manager)
    connector_service = DatabaseConnectorService(
        tmp_path,
        session_manager=service.session_manager,
    )
    connector_service.attach_connector(
        "local_default",
        conversation.session_id,
        connector_id,
    )
    write_workspace_database_mount_data(
        workspace_dir,
        {
            "version": 1,
            "connector_ids": [connector_id],
        },
    )

    graph_dir = tmp_path / "data" / "graphs" / "graph-overview"
    graph_dir.mkdir(parents=True)

    session_dir = tmp_path / "local_default" / conversation.session_id
    journal = SessionExecutionJournal(session_dir, conversation.session_id)
    journal.append_record(
        code="print('overview')",
        started_at="2026-04-24T10:00:00",
        finished_at="2026-04-24T10:00:01",
        status="completed",
        sandbox_mode="local",
        env_id="python-data-analysis",
        stdout="overview",
        stderr="",
        result_preview_text="overview",
    )

    import app.core.config as config_module
    import app.knowledge as knowledge_module
    import app.api.routes.workspaces_overview_utils as overview_utils_module
    import app.services.session.config_projection as config_projection_module

    class FakeKnowledgeService:
        def list_knowledge_bases(self, user_id: str):
            assert user_id == "local_default"
            return [
                SimpleNamespace(
                    id="kb-overview",
                    name="概览知识库",
                    document_count=3,
                )
            ]

    async def fake_runtime_config_projection(**kwargs):
        assert kwargs["session_id"] == conversation.session_id
        return {
            "config_sync_state": "aligned",
            "agent_config_effect": "next_run_only",
            "memory_effect": "next_run_only",
            "can_edit_agent_config_now": True,
            "rebuild_required": False,
            "rebuild_required_reasons": [],
            "current_agent_config_version": "agent-v1",
            "applied_agent_config_version": "agent-v1",
            "pending_agent_config_version": None,
            "current_capability_snapshot_version": "cap-v1",
            "applied_capability_snapshot_version": "cap-v1",
            "pending_capability_snapshot_version": None,
            "current_memory_snapshot_version": "mem-v1",
            "current_memory_snapshot_hash": "hash-v1",
            "pending_memory_snapshot_version": None,
            "memory_snapshot_preview": {
                "version": "mem-v1",
                "snapshot_hash": "hash-v1",
                "rendered_markdown": "## 用户默认层\n\n- 已确认偏好",
            },
        }

    def fake_capability_summary(_workspace_dir: Path):
        return {
            "mcp_server_count": 2,
            "enabled_mcp_server_count": 1,
            "enabled_mcp_server_names": ["demo-mcp"],
            "mcp_config_version": 1,
        }

    def fake_expert_catalog(*, user_id: str, workspace_id: str):
        assert user_id == "local_default"
        assert workspace_id == "task-overview"
        return WorkspaceExpertCatalogResponse(
            workspace_id=workspace_id,
            profile_name="analysis-default",
            roles=[
                ExpertRoleSummary(
                    role_id="researcher",
                    display_name="研究员",
                    description="研究问题",
                    agent_file="researcher.md",
                ),
                ExpertRoleSummary(
                    role_id="coder",
                    display_name="工程师",
                    description="修改代码",
                    agent_file="coder.md",
                ),
            ],
        )

    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(
        knowledge_module,
        "get_sqlite_kb_service",
        lambda: FakeKnowledgeService(),
    )
    monkeypatch.setattr(
        "app.graphrag.core.SQLiteGraphStore.list_graphs",
        classmethod(
            lambda cls, user_id: [
                {
                    "kg_id": "graph-overview",
                    "name": "概览图谱",
                    "entity_count": 3,
                    "relation_count": 2,
                    "document_count": 1,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        config_projection_module,
        "build_runtime_config_projection",
        fake_runtime_config_projection,
    )
    monkeypatch.setattr(
        config_projection_module,
        "build_workspace_capability_summary",
        fake_capability_summary,
    )
    monkeypatch.setattr(
        overview_utils_module,
        "get_workspace_expert_catalog",
        fake_expert_catalog,
    )

    overview = await workspace_route.get_workspace_overview(
        "task-overview",
        current_user=_build_user(),
    )

    assert overview.workspace.workspace_id == "task-overview"
    assert overview.workspace.title == "概览任务"
    assert overview.current_session is not None
    assert overview.current_session.session_id == conversation.session_id
    assert overview.current_session.is_current is True
    assert len(overview.sessions) == 1

    assert overview.config.config_sync_state == "aligned"
    assert overview.config.current_agent_config_version == "agent-v1"
    assert overview.memory.has_memory is True
    assert overview.memory.document_count == 1
    assert overview.memory.version == "mem-v1"

    assert overview.resources.mcp.user_asset_count == 2
    assert overview.resources.mcp.configured is True
    assert overview.resources.mcp.verified is False
    assert overview.resources.mcp.workspace_default_count == 1
    assert overview.resources.knowledge_base.user_asset_count == 1
    assert overview.resources.knowledge_base.workspace_default_count == 1
    assert overview.resources.knowledge_graph.user_asset_count == 1
    assert overview.resources.knowledge_graph.workspace_default_count == 1
    assert overview.resources.knowledge_graph.metadata["available_graphs"] == [
        {"id": "graph-overview", "name": "概览图谱"}
    ]
    assert overview.resources.database.user_asset_count >= 1
    assert overview.resources.database.workspace_default_count == 1
    assert overview.resources.database.session_attached_count == 1
    assert overview.resources.database.runtime_available_count == 1
    assert overview.resources.file.workspace_default_count == 1
    assert overview.resources.verification.status == "not_verified"

    assert overview.experts.profile_name == "analysis-default"
    assert overview.experts.available_role_count == 2
    assert overview.experts.enabled_role_ids == ["researcher", "coder"]
    assert overview.artifacts.workspace_file_count == 1
    assert overview.artifacts.artifact_file_count == 1
    assert overview.artifacts.execution_record_count == 1
    assert overview.artifacts.last_execution_status == "completed"

    resource_layers = await workspace_route.get_workspace_resource_layers(
        "task-overview",
        current_user=_build_user(),
    )
    assert resource_layers.workspace_id == "task-overview"
    assert resource_layers.session_id == conversation.session_id
    assert resource_layers.resources.database.available is True
    assert resource_layers.resources.file.primary_action == "open_workspace_files"


@pytest.mark.asyncio
async def test_workspace_overview_returns_404_for_missing_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(workspace_route, "get_workspace_registry_service", lambda: service)

    with pytest.raises(HTTPException) as exc_info:
        await workspace_route.get_workspace_overview(
            "missing-workspace",
            current_user=_build_user(),
        )

    assert exc_info.value.status_code == 404
