from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import networkx as nx
import pytest
from fastapi import HTTPException

from app.graphrag.api import routes as graph_routes
from app.core import config as config_module
from app.graphrag.models.entity import Entity
from app.graphrag.models.relation import Relation
from app.graphrag.service import GraphRAGService
from app.models.user import UserInfo
from app.services.session import SessionManager

from app.services.workspace_registry import WorkspaceRegistryService


def _build_service(tmp_path: Path) -> WorkspaceRegistryService:
    return WorkspaceRegistryService(tmp_path, session_manager=SessionManager(tmp_path))


def _graph_dir(tmp_path: Path, user_id: str = "local_default") -> Path:
    return tmp_path / user_id / "global_workspace" / "resources" / "graphs"


def _write_example_graph(graph_file: Path, nodes: list[str], edges: list[tuple[str, str]]) -> None:
    graph = nx.Graph()
    for node in nodes:
        graph.add_node(
            node,
            entity_id=node,
            entity_type="concept",
            description=f"{node} description",
            source_id="test",
            metadata_json="{}",
        )
    for index, (source, target) in enumerate(edges, start=1):
        graph.add_edge(
            source,
            target,
            relation_id=f"rel-{index}",
            description=f"{source}->{target}",
            strength=1.0,
            source_id="test",
            metadata_json="{}",
        )
    graph_file.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(graph, graph_file)


def test_get_graphrag_service_uses_db_path_directly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证通过 db_path 直接定位知识图谱文件。"""
    service = _build_service(tmp_path)
    service.create_workspace(
        user_id="local_default",
        workspace_id="task-graph-bind",
        title="图谱绑定",
        initial_conversation_title="当前对话",
    )

    # 在工作区根目录创建 .graph.db 文件
    workspace_root = service.get_workspace_root("local_default", "task-graph-bind")
    (workspace_root / "analysis-note.graph.db").touch()

    request = SimpleNamespace(state=SimpleNamespace(user=UserInfo(
        user_id="local_default",
        role="admin",
        auth_provider="local",
    )))

    created = []

    class FakeGraphRAGService:
        def __init__(self, kb_id: str, auto_init_llm: bool, user_id: str | None = None, graph_store=None):
            created.append(
                {
                    "kb_id": kb_id,
                    "auto_init_llm": auto_init_llm,
                    "user_id": user_id,
                }
            )

    monkeypatch.setattr(
        graph_routes,
        "_workspace_graphrag_services",
        {},
    )
    monkeypatch.setattr(
        "app.services.workspace_registry.get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        "app.graphrag.api.routes.GraphRAGService",
        FakeGraphRAGService,
    )
    monkeypatch.setattr(config_module, "WORKSPACE_DIR", tmp_path)

    result = graph_routes.get_graphrag_service(
        request=request,
        workspace_id="task-graph-bind",
        db_path="/workspace/analysis-note.graph.db",
    )

    assert result is not None
    assert created == [
        {
            "kb_id": "analysis-note",
            "auto_init_llm": True,
            "user_id": "local_default",
        }
    ]


def test_get_graphrag_service_defaults_to_system_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证未传 db_path 时默认使用全局 system.db。"""
    service = _build_service(tmp_path)
    service.create_workspace(
        user_id="local_default",
        workspace_id="task-graph-empty",
        title="空图谱绑定",
        initial_conversation_title="当前对话",
    )

    # 创建全局 system.db
    graph_dir = _graph_dir(tmp_path)
    graph_dir.mkdir(parents=True, exist_ok=True)
    (graph_dir / "system.db").touch()

    request = SimpleNamespace(state=SimpleNamespace(user=UserInfo(
        user_id="local_default",
        role="admin",
        auth_provider="local",
    )))

    monkeypatch.setattr(
        "app.services.workspace_registry.get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(config_module, "WORKSPACE_DIR", tmp_path)

    result = graph_routes.get_graphrag_service(
        request=request,
        workspace_id="task-graph-empty",
    )
    assert result is not None


def test_get_graphrag_service_rejects_missing_db_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证传不存在的 db_path 时返回 404。"""
    service = _build_service(tmp_path)
    service.create_workspace(
        user_id="local_default",
        workspace_id="task-graph-invalid",
        title="图谱切换校验",
        initial_conversation_title="当前对话",
    )

    request = SimpleNamespace(state=SimpleNamespace(user=UserInfo(
        user_id="local_default",
        role="admin",
        auth_provider="local",
    )))

    monkeypatch.setattr(
        "app.services.workspace_registry.get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(config_module, "WORKSPACE_DIR", tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        graph_routes.get_graphrag_service(
            request=request,
            workspace_id="task-graph-invalid",
            db_path="/workspace/nonexistent.graph.db",
        )

    assert exc_info.value.status_code == 404
    assert "知识图谱数据库不存在" in str(exc_info.value.detail)


def test_get_graphrag_service_uses_global_db_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证通过 /global/ 前缀定位全局图谱。"""
    service = _build_service(tmp_path)

    graph_dir = _graph_dir(tmp_path)
    graph_dir.mkdir(parents=True, exist_ok=True)
    (graph_dir / "project-b.db").touch()

    request = SimpleNamespace(state=SimpleNamespace(user=UserInfo(
        user_id="local_default",
        role="admin",
        auth_provider="local",
    )))

    created = []

    class FakeGraphRAGService:
        def __init__(self, kb_id: str, auto_init_llm: bool, user_id: str | None = None, graph_store=None):
            created.append(kb_id)

    monkeypatch.setattr(graph_routes, "_workspace_graphrag_services", {})
    monkeypatch.setattr(
        "app.services.workspace_registry.get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        "app.graphrag.api.routes.GraphRAGService",
        FakeGraphRAGService,
    )
    monkeypatch.setattr(config_module, "WORKSPACE_DIR", tmp_path)

    graph_routes.get_graphrag_service(
        request=request,
        db_path="/global/graphs/project-b.db",
    )

    assert created == ["project-b"]


@pytest.mark.asyncio
async def test_graphrag_service_refreshes_cached_graph_when_data_changes(
    tmp_path: Path,
) -> None:
    """验证 SQLite 存储模式下，add_subgraph 后 health_check 和 visualization 能正确反映新数据。"""
    from app.graphrag.core import SQLiteGraphStore

    graph_store = SQLiteGraphStore(
        user_id="test",
        kg_id="graph-preview-delivery-demo",
        db_path=tmp_path / "test-graph.db",
    )
    service = GraphRAGService(
        kb_id="graph-preview-delivery-demo",
        auto_init_llm=False,
        enable_communities=False,
        graph_store=graph_store,
    )

    await service.graph_store.add_subgraph(
        doc_id="doc-1",
        entities=[
            Entity(entity_id="e-a", name="初始节点A", entity_type="concept", description="A"),
            Entity(entity_id="e-b", name="初始节点B", entity_type="concept", description="B"),
        ],
        relations=[
            Relation(relation_id="r-ab", source_entity="初始节点A", target_entity="初始节点B", description="A->B"),
        ],
    )

    initial_health = await service.health_check()
    assert initial_health["entities"] == 2
    assert initial_health["relations"] == 1
    assert initial_health["kb_id"] == "graph-preview-delivery-demo"

    await service.graph_store.add_subgraph(
        doc_id="doc-2",
        entities=[
            Entity(entity_id="e-a", name="更新节点A", entity_type="concept", description="A2"),
            Entity(entity_id="e-b", name="更新节点B", entity_type="concept", description="B2"),
            Entity(entity_id="e-c", name="更新节点C", entity_type="concept", description="C2"),
        ],
        relations=[
            Relation(relation_id="r-ab", source_entity="更新节点A", target_entity="更新节点B", description="A2->B2"),
            Relation(relation_id="r-bc", source_entity="更新节点B", target_entity="更新节点C", description="B2->C2"),
        ],
    )

    refreshed_health = await service.health_check()
    visualization = service.get_visualization()

    assert refreshed_health["entities"] == 3
    assert refreshed_health["relations"] == 2
    assert {item["name"] for item in visualization["nodes"]} == {
        "更新节点A",
        "更新节点B",
        "更新节点C",
    }
