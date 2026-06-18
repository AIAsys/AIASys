from __future__ import annotations

from pathlib import Path

import pytest

from app.graphrag.core.sqlite_graph_store import SQLiteGraphStore
from app.graphrag.models.entity import Entity
from app.graphrag.models.relation import Relation


@pytest.mark.asyncio
async def test_sqlite_graph_store_serializes_frontend_visualization_shape(
    tmp_path: Path,
) -> None:
    store = SQLiteGraphStore(
        user_id="local_default",
        kg_id="resource-graph",
        db_path=tmp_path / "resource-graph.db",
    )
    await store.add_subgraph(
        doc_id="doc-1",
        entities=[
            Entity(
                entity_id="entity-a",
                name="实体A",
                entity_type="concept",
                description="实体A说明",
                metadata={"source": "test"},
            ),
            Entity(
                entity_id="entity-b",
                name="实体B",
                entity_type="concept",
                description="实体B说明",
            ),
        ],
        relations=[
            Relation(
                relation_id="rel-a-b",
                source_entity="entity-a",
                target_entity="entity-b",
                description="实体A关联实体B",
                strength=2.5,
            )
        ],
    )

    graph, truncated = store.get_visualization_graph(limit=20)
    payload = store.serialize_graph(
        graph,
        source="overview",
        truncated=truncated,
        total_nodes=store.get_graph().number_of_nodes(),
        total_edges=store.get_graph().number_of_edges(),
    )

    assert payload["source"] == "overview"
    assert payload["truncated"] is False
    assert payload["total_nodes"] == 2
    assert payload["total_edges"] == 1

    nodes = {node["id"]: node for node in payload["nodes"]}
    assert nodes["entity-a"]["name"] == "实体A"
    assert nodes["entity-a"]["entity_type"] == "concept"
    assert nodes["entity-a"]["description"] == "实体A说明"
    assert nodes["entity-a"]["degree"] == 1
    assert nodes["entity-a"]["properties"] == {"source": "test"}

    edge = payload["edges"][0]
    assert edge["id"] == "rel-a-b"
    assert edge["source"] == "entity-a"
    assert edge["target"] == "entity-b"
    assert edge["relation_type"] == "实体A关联实体B"
    assert edge["description"] == "实体A关联实体B"
    assert edge["strength"] == 2.5


def test_sqlite_graph_store_persists_graph_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.graphrag.core import sqlite_graph_store as graph_store_module

    monkeypatch.setattr(
        graph_store_module, "get_user_global_resources_dir", lambda user_id: tmp_path
    )
    # list_graphs 自动扫描用的是 WORKSPACE_DIR / user_id，mock 到 tmp_path 避免读到真实项目目录
    monkeypatch.setattr("app.core.config.WORKSPACE_DIR", tmp_path)

    db_path = tmp_path / "graphs" / "named-graph.db"
    store = SQLiteGraphStore(user_id="local_default", kg_id="named-graph", db_path=db_path)
    store.set_metadata("name", "竞赛图谱")
    store.set_metadata("description", "自动研究测试图谱")

    assert store.get_metadata("name") == "竞赛图谱"
    assert store.get_metadata("description") == "自动研究测试图谱"

    graphs = SQLiteGraphStore.list_graphs("local_default")
    assert graphs == [
        {
            "kg_id": "named-graph",
            "name": "竞赛图谱",
            "description": "自动研究测试图谱",
            "entity_count": 0,
            "relation_count": 0,
            "document_count": 0,
        }
    ]


def test_sqlite_graph_store_creates_manual_entity_for_visualization(
    tmp_path: Path,
) -> None:
    store = SQLiteGraphStore(
        user_id="local_default",
        kg_id="manual-graph",
        db_path=tmp_path / "manual-graph.db",
    )

    created = store.create_entity(
        name="手工节点",
        entity_type="idea",
        description="从可视化面板创建",
        properties={"source": "manual"},
    )

    assert created["entity_id"]
    assert created["name"] == "手工节点"
    assert created["entity_type"] == "idea"
    assert created["description"] == "从可视化面板创建"
    assert created["properties"] == {"source": "manual"}

    graph, truncated = store.get_visualization_graph(limit=20)
    payload = store.serialize_graph(graph, source="overview", truncated=truncated)
    assert payload["total_nodes"] == 1
    assert payload["total_edges"] == 0
    assert payload["nodes"] == [
        {
            "id": created["entity_id"],
            "name": "手工节点",
            "entity_type": "idea",
            "description": "从可视化面板创建",
            "degree": 0,
            "community_ids": [],
            "primary_community": None,
            "properties": {"source": "manual"},
        }
    ]


def test_sqlite_graph_store_rejects_duplicate_manual_entity(
    tmp_path: Path,
) -> None:
    store = SQLiteGraphStore(
        user_id="local_default",
        kg_id="manual-graph",
        db_path=tmp_path / "manual-graph.db",
    )

    store.create_entity(name="重复节点")

    with pytest.raises(ValueError, match="实体已存在"):
        store.create_entity(name="重复节点")


def test_sqlite_graph_store_creates_manual_relation_for_visualization(
    tmp_path: Path,
) -> None:
    store = SQLiteGraphStore(
        user_id="local_default",
        kg_id="manual-relation-graph",
        db_path=tmp_path / "manual-relation-graph.db",
    )
    source = store.create_entity(name="源节点", entity_type="concept")
    target = store.create_entity(name="目标节点", entity_type="concept")

    relation = store.create_relation(
        source_entity_id=source["entity_id"],
        target_entity_id=target["entity_id"],
        relation_type="supports",
        description="源节点支持目标节点",
        strength=2.0,
        properties={"source": "manual"},
    )

    assert relation["relation_id"]
    assert relation["source"] == source["entity_id"]
    assert relation["target"] == target["entity_id"]
    assert relation["source_name"] == "源节点"
    assert relation["target_name"] == "目标节点"
    assert relation["relation_type"] == "supports"
    assert relation["description"] == "源节点支持目标节点"
    assert relation["strength"] == 2.0
    assert relation["properties"] == {"source": "manual"}

    graph, truncated = store.get_visualization_graph(limit=20)
    payload = store.serialize_graph(graph, source="overview", truncated=truncated)
    assert payload["total_nodes"] == 2
    assert payload["total_edges"] == 1
    nodes = {node["id"]: node for node in payload["nodes"]}
    assert nodes[source["entity_id"]]["degree"] == 1
    assert nodes[target["entity_id"]]["degree"] == 1
    assert payload["edges"] == [
        {
            "id": relation["relation_id"],
            "source": source["entity_id"],
            "target": target["entity_id"],
            "relation_type": "supports",
            "description": "源节点支持目标节点",
            "strength": 2.0,
            "metadata": {},
        }
    ]


def test_sqlite_graph_store_rejects_invalid_manual_relation(
    tmp_path: Path,
) -> None:
    store = SQLiteGraphStore(
        user_id="local_default",
        kg_id="manual-relation-graph",
        db_path=tmp_path / "manual-relation-graph.db",
    )
    source = store.create_entity(name="源节点")
    target = store.create_entity(name="目标节点")

    with pytest.raises(ValueError, match="目标节点不存在"):
        store.create_relation(
            source_entity_id=source["entity_id"],
            target_entity_id="missing",
        )

    with pytest.raises(ValueError, match="不能连接节点自身"):
        store.create_relation(
            source_entity_id=source["entity_id"],
            target_entity_id=source["entity_id"],
        )

    store.create_relation(
        source_entity_id=source["entity_id"],
        target_entity_id=target["entity_id"],
        relation_type="related_to",
    )
    with pytest.raises(ValueError, match="相同关系已存在"):
        store.create_relation(
            source_entity_id=source["entity_id"],
            target_entity_id=target["entity_id"],
            relation_type="related_to",
        )


def test_sqlite_graph_store_deletes_manual_entity_and_relations(
    tmp_path: Path,
) -> None:
    store = SQLiteGraphStore(
        user_id="local_default",
        kg_id="manual-delete-graph",
        db_path=tmp_path / "manual-delete-graph.db",
    )
    source = store.create_entity(name="源节点")
    target = store.create_entity(name="目标节点")
    other = store.create_entity(name="保留节点")
    store.create_relation(
        source_entity_id=source["entity_id"],
        target_entity_id=target["entity_id"],
        relation_type="supports",
    )
    store.create_relation(
        source_entity_id=target["entity_id"],
        target_entity_id=other["entity_id"],
        relation_type="blocks",
    )

    deleted = store.delete_entity(target["entity_id"])

    assert deleted == {
        "entity_id": target["entity_id"],
        "name": "目标节点",
        "deleted_relations": 2,
    }
    assert store.get_entity(target["entity_id"]) is None

    graph, truncated = store.get_visualization_graph(limit=20)
    payload = store.serialize_graph(graph, source="overview", truncated=truncated)
    assert payload["total_nodes"] == 2
    assert payload["total_edges"] == 0
    assert {node["name"] for node in payload["nodes"]} == {"源节点", "保留节点"}
    assert payload["edges"] == []


@pytest.mark.asyncio
async def test_sqlite_graph_store_subgraph_returns_networkx_graph(
    tmp_path: Path,
) -> None:
    store = SQLiteGraphStore(
        user_id="local_default",
        kg_id="subgraph",
        db_path=tmp_path / "subgraph.db",
    )
    await store.add_subgraph(
        doc_id="doc-1",
        entities=[
            Entity(
                entity_id="entity-a",
                name="实体A",
                entity_type="concept",
                description="实体A说明",
            ),
            Entity(
                entity_id="entity-b",
                name="实体B",
                entity_type="concept",
                description="实体B说明",
            ),
        ],
        relations=[
            Relation(
                relation_id="rel-a-b",
                source_entity="实体A",
                target_entity="实体B",
                description="实体A依赖实体B",
                strength=3.5,
            )
        ],
    )

    subgraph = store.get_subgraph(["实体A"], depth=1)

    assert sorted(subgraph.nodes()) == ["实体A", "实体B"]
    assert subgraph.number_of_edges() == 1
    edge = subgraph.get_edge_data("实体A", "实体B")
    assert edge["relation_id"] == "rel-a-b"
    assert edge["relation_type"] == "实体A依赖实体B"
    assert edge["description"] == "实体A依赖实体B"
    assert edge["strength"] == 3.5


@pytest.mark.asyncio
async def test_sqlite_graph_store_relation_queries_handle_ids_and_names(
    tmp_path: Path,
) -> None:
    store = SQLiteGraphStore(
        user_id="local_default",
        kg_id="relations",
        db_path=tmp_path / "relations.db",
    )
    await store.add_subgraph(
        doc_id="doc-1",
        entities=[
            Entity(entity_id="entity-a", name="实体A", entity_type="concept", description="A"),
            Entity(entity_id="entity-b", name="实体B", entity_type="concept", description="B"),
        ],
        relations=[
            Relation(
                relation_id="rel-a-b",
                source_entity="实体A",
                target_entity="实体B",
                description="实体A依赖实体B",
                strength=8,
            )
        ],
    )
    await store.add_relation(
        Relation(
            relation_id="rel-b-a",
            source_entity="entity-b",
            target_entity="entity-a",
            description="实体B反向引用实体A",
            strength=4,
        )
    )

    entity, outgoing = store.get_entity_relations("entity-a", direction="outgoing")
    assert entity and entity["name"] == "实体A"
    assert [relation["relation_id"] for relation in outgoing] == ["rel-a-b"]
    assert outgoing[0]["source"] == "实体A"
    assert outgoing[0]["target"] == "实体B"
    assert outgoing[0]["direction"] == "outgoing"

    entity, incoming = store.get_entity_relations(
        "实体A",
        relation_type="反向引用",
        direction="incoming",
    )
    assert entity and entity["entity_id"] == "entity-a"
    assert [relation["relation_id"] for relation in incoming] == ["rel-b-a"]
    assert incoming[0]["source"] == "实体B"
    assert incoming[0]["target"] == "实体A"
    assert incoming[0]["direction"] == "incoming"


@pytest.mark.asyncio
async def test_sqlite_graph_store_invalidates_cached_graph_on_writes(
    tmp_path: Path,
) -> None:
    store = SQLiteGraphStore(
        user_id="local_default",
        kg_id="cache",
        db_path=tmp_path / "cache.db",
    )
    store.create_entity(name="实体A")
    assert store.get_graph().number_of_nodes() == 1

    await store.add_entity(
        Entity(
            entity_id="entity-b",
            name="实体B",
            entity_type="concept",
            description="B",
        )
    )

    assert store.get_graph().number_of_nodes() == 2


def test_sqlite_graph_store_load_graph_without_n_plus_one(
    tmp_path: Path,
) -> None:
    store = SQLiteGraphStore(
        user_id="local_default",
        kg_id="nplusone",
        db_path=tmp_path / "nplusone.db",
    )
    store.create_entity(name="实体A", entity_type="concept")
    store.create_entity(name="实体B", entity_type="concept")
    store.create_relation(
        source_entity_id="实体A",
        target_entity_id="实体B",
        relation_type="related_to",
    )
    graph = store.get_graph()
    assert graph.number_of_nodes() == 2
    assert graph.number_of_edges() == 1
    edge = graph.get_edge_data("实体A", "实体B")
    assert edge is not None
    assert edge["relation_type"] == "related_to"


def test_sqlite_graph_store_search_entities_does_not_scan_properties(
    tmp_path: Path,
) -> None:
    store = SQLiteGraphStore(
        user_id="local_default",
        kg_id="search",
        db_path=tmp_path / "search.db",
    )
    store.create_entity(
        name="关键词匹配",
        entity_type="concept",
        properties={"hidden": "内部JSON值含有特殊关键词不应被搜到"},
    )
    results = store.search_entities("内部JSON")
    assert len(results) == 0
    results = store.search_entities("关键词匹配")
    assert len(results) == 1


def test_sqlite_graph_store_cached_counts_and_layout_positions(
    tmp_path: Path,
) -> None:
    store = SQLiteGraphStore(
        user_id="local_default",
        kg_id="counts",
        db_path=tmp_path / "counts.db",
    )
    stats = store.get_statistics()
    assert stats["entity_count"] == 0
    assert stats["relation_count"] == 0

    store.create_entity(name="A")
    store.create_entity(name="B")
    store.create_relation(source_entity_id="A", target_entity_id="B")

    stats = store.get_statistics()
    assert stats["entity_count"] == 2
    assert stats["relation_count"] == 1

    # 布局位置持久化
    positions = {"A": {"x": 10.5, "y": 20.0}, "B": {"x": 30.0, "y": 40.0}}
    store.save_layout_positions(positions)
    loaded = store.get_layout_positions()
    assert loaded == positions

    # 更新布局
    positions["A"]["x"] = 99.0
    store.save_layout_positions(positions)
    loaded = store.get_layout_positions()
    assert loaded["A"]["x"] == 99.0
