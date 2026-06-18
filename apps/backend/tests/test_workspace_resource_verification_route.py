from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest

from app.api.routes import workspaces_resource_utils
from app.api.routes import workspaces_resources_verification as workspace_route
from app.models.mcp import MCPServerConfig
from app.models.user import UserInfo

from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_service(tmp_path: Path) -> WorkspaceRegistryService:
    return WorkspaceRegistryService(tmp_path, session_manager=SessionManager(tmp_path))


@pytest.mark.asyncio
async def test_workspace_resource_verification_route_returns_unified_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspace_route,
        "get_workspace_registry_service",
        lambda: service,
    )

    detail = service.create_workspace(
        user_id="local_default",
        workspace_id="task-verify",
        title="任务验证",
        initial_conversation_title="当前对话",
    )
    conversation = detail.current_conversation
    assert conversation is not None

    import app.services.llm as llm_module
    import app.api.routes.mcp_session as mcp_session_route
    import app.knowledge as knowledge_module
    import app.graphrag as graphrag_module
    import app.services.connector as connector_module
    import app.services.session.config_projection as config_projection_module

    class FakeMCPSessionService:
        def get_session_mcp_servers(self, user_id: str, session_id: str):
            assert user_id == "local_default"
            assert session_id == conversation.session_id
            return [
                MCPServerConfig(
                    name="demo-mcp",
                    type="streamable-http",
                    url="http://localhost:9999/mcp",
                    enabled=True,
                )
            ]

    async def fake_test_session_server_connection(server: MCPServerConfig):
        assert server.name == "demo-mcp"
        return mcp_session_route.TestConnectionResponse(
            status="connected",
            tools_count=2,
            message="连接成功",
        )

    class FakeKnowledgeClient:
        def list_collections(self):
            return ["demo"]

    class FakeKnowledgeService:
        client = FakeKnowledgeClient()

        def list_knowledge_bases(self, user_id: str):
            assert user_id == "local_default"
            return [
                SimpleNamespace(
                    id="kb-demo",
                    name="演示知识库",
                    document_count=3,
                )
            ]

        async def query(self, user_id: str, kb_id: str, request):
            assert user_id == "local_default"
            assert kb_id == "kb-demo"
            assert request.query == "test"
            return SimpleNamespace(total=1)

    class FakeGraphService:
        def __init__(
            self, kb_id: str, auto_init_llm: bool, user_id: str | None = None, graph_store=None
        ):
            assert kb_id == "system"

        async def health_check(self):
            return {
                "status": "healthy",
                "llm_status": "ready",
                "message": "Graph ready",
            }

        def search(self, query: str, entity_type):
            assert query == "test"
            assert entity_type is None
            return [{"name": "Test Entity"}]

        def get_statistics(self):
            return {"entity_count": 5, "relation_count": 3, "entity_types": ["concept"]}

    class FakeDatabaseConnectorService:
        def __init__(self, base_dir: Path):
            self.base_dir = base_dir

        def list_session_attachments(self, user_id: str, session_id: str):
            assert user_id == "local_default"
            assert session_id == conversation.session_id
            return [
                SimpleNamespace(
                    connector_id="conn-1",
                    name="Postgres Demo",
                    handle="db.postgres_demo",
                    grants=["schema_read", "data_read"],
                    model_dump=lambda: {
                        "connector_id": "conn-1",
                        "name": "Postgres Demo",
                        "handle": "db.postgres_demo",
                        "grants": ["schema_read", "data_read"],
                    },
                )
            ]

        def test_connector(self, user_id: str, connector_id: str):
            assert user_id == "local_default"
            assert connector_id == "conn-1"
            return SimpleNamespace(
                success=True,
                message="连接成功",
                model_dump=lambda: {
                    "success": True,
                    "message": "连接成功",
                },
            )

        def list_attached_connector_tables(
            self, *, user_id: str, session_id: str, connector_id: str
        ):
            assert user_id == "local_default"
            assert session_id == conversation.session_id
            assert connector_id == "conn-1"
            return SimpleNamespace(
                tables=[
                    SimpleNamespace(full_name="public.demo_table"),
                ]
            )

    monkeypatch.setattr(llm_module, "get_mcp_session_service", lambda: FakeMCPSessionService())
    monkeypatch.setattr(
        mcp_session_route,
        "_test_session_server_connection",
        fake_test_session_server_connection,
    )
    monkeypatch.setattr(
        config_projection_module,
        "build_workspace_capability_summary",
        lambda _workspace_dir: {
            "enabled_mcp_server_names": ["demo-mcp"],
            "enabled_mcp_server_count": 1,
        },
    )
    monkeypatch.setattr(
        knowledge_module,
        "get_sqlite_kb_service",
        lambda: FakeKnowledgeService(),
    )

    async def fake_list_available_knowledge_graphs(user_id: str = "local_default"):
        return [
            {
                "id": "system",
                "name": "system",
                "entity_count": 5,
                "relation_count": 3,
                "llm_status": "ready",
            }
        ]

    monkeypatch.setattr(
        workspaces_resource_utils,
        "_list_available_knowledge_graphs",
        fake_list_available_knowledge_graphs,
    )
    monkeypatch.setattr(
        graphrag_module,
        "GraphRAGService",
        FakeGraphService,
    )
    # Mock find_db_path to return a valid path so GraphRAGService gets created
    from app.graphrag.core import SQLiteGraphStore

    db_file = tmp_path / "test-system.db"
    db_file.touch()
    monkeypatch.setattr(
        SQLiteGraphStore,
        "find_db_path",
        classmethod(lambda cls, user_id, kg_id, **kwargs: db_file),
    )
    monkeypatch.setattr(
        connector_module,
        "DatabaseConnectorService",
        FakeDatabaseConnectorService,
    )

    response = await workspace_route.get_workspace_resource_verification(
        "task-verify",
        current_user=_build_user(),
    )

    assert response.workspace_id == "task-verify"
    assert response.session_id == conversation.session_id
    assert [item.resource_key for item in response.resources] == [
        "mcp",
        "knowledge_base",
        "knowledge_graph",
        "database",
        "file",
    ]

    mcp_item = response.resources[0]
    assert mcp_item.mounted is True
    assert mcp_item.health.status == "passed"
    assert mcp_item.smoke.status == "passed"

    kb_item = response.resources[1]
    assert kb_item.scope == "task"
    assert kb_item.mounted is True
    assert kb_item.health.status == "passed"
    assert kb_item.smoke.status == "passed"

    graph_item = response.resources[2]
    assert graph_item.scope == "task"
    assert graph_item.mounted is True
    assert graph_item.health.status == "passed"
    assert graph_item.smoke.status == "passed"

    db_item = response.resources[3]
    assert db_item.mounted is True
    assert db_item.health.status == "passed"
    assert db_item.smoke.status == "passed"

    file_item = response.resources[4]
    assert file_item.resource_key == "file"
    assert file_item.health.status == "passed"

    cached = await workspace_route.get_workspace_resource_verification(
        "task-verify",
        current_user=_build_user(),
    )
    assert cached.cache_hit is True
    assert cached.verification_source == "cache"
    assert [item.resource_key for item in cached.resources] == [
        "mcp",
        "knowledge_base",
        "knowledge_graph",
        "database",
        "file",
    ]


@pytest.mark.asyncio
async def test_workspace_resource_verification_degrades_per_resource(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspace_route,
        "get_workspace_registry_service",
        lambda: service,
    )

    detail = service.create_workspace(
        user_id="local_default",
        workspace_id="task-verify-failure",
        title="任务验证失败降级",
        initial_conversation_title="当前对话",
    )
    conversation = detail.current_conversation
    assert conversation is not None

    import app.services.llm as llm_module
    import app.knowledge as knowledge_module
    import app.services.connector as connector_module
    import app.services.session.config_projection as config_projection_module

    class FakeMCPSessionService:
        def get_session_mcp_servers(self, user_id: str, session_id: str):
            return []

    class FailingKnowledgeService:
        def list_knowledge_bases(self, user_id: str):
            raise RuntimeError("kb unavailable")

    class FailingDatabaseConnectorService:
        def __init__(self, base_dir: Path):
            self.base_dir = base_dir

        def list_session_attachments(self, user_id: str, session_id: str):
            raise RuntimeError("database attachments unavailable")

    async def failing_list_available_knowledge_graphs():
        raise RuntimeError("graph unavailable")

    monkeypatch.setattr(llm_module, "get_mcp_session_service", lambda: FakeMCPSessionService())
    monkeypatch.setattr(
        config_projection_module,
        "build_workspace_capability_summary",
        lambda _workspace_dir: {
            "enabled_mcp_server_names": [],
            "enabled_mcp_server_count": 0,
        },
    )
    monkeypatch.setattr(
        knowledge_module,
        "get_sqlite_kb_service",
        lambda: FailingKnowledgeService(),
    )
    monkeypatch.setattr(
        workspaces_resource_utils,
        "_list_available_knowledge_graphs",
        failing_list_available_knowledge_graphs,
    )
    monkeypatch.setattr(
        connector_module,
        "DatabaseConnectorService",
        FailingDatabaseConnectorService,
    )

    response = await workspace_route.get_workspace_resource_verification(
        "task-verify-failure",
        current_user=_build_user(),
    )

    resources = {item.resource_key: item for item in response.resources}
    assert resources["knowledge_base"].health.status == "failed"
    assert resources["knowledge_base"].smoke.status == "skipped"
    assert resources["knowledge_graph"].health.status == "failed"
    assert resources["knowledge_graph"].smoke.status == "skipped"
    assert resources["database"].health.status == "failed"
    assert resources["database"].smoke.status == "skipped"
