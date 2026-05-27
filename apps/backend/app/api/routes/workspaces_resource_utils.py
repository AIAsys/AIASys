"""
任务工作区与对话主接口
"""

from __future__ import annotations

import logging

from app.models.workspace import (
    WorkspaceDatabaseMountResponse,
    WorkspaceKnowledgeBaseMountResponse,
    WorkspaceMountedDatabaseConnectorSummary,
    WorkspaceMountedKnowledgeBaseSummary,
)

logger = logging.getLogger(__name__)


def _build_workspace_knowledge_base_mount_response(
    *,
    workspace_id: str,
    mounted_ids: list[str],
    visible_knowledge_bases: list[object],
) -> WorkspaceKnowledgeBaseMountResponse:
    visible_by_id = {str(kb.id): kb for kb in visible_knowledge_bases if getattr(kb, "id", None)}
    mounted_knowledge_bases = [
        WorkspaceMountedKnowledgeBaseSummary(
            id=kb_id,
            name=str(visible_by_id[kb_id].name),
            document_count=int(getattr(visible_by_id[kb_id], "document_count", 0) or 0),
            mounted=True,
        )
        for kb_id in mounted_ids
        if kb_id in visible_by_id
    ]
    available_knowledge_bases = [
        WorkspaceMountedKnowledgeBaseSummary(
            id=str(kb.id),
            name=str(kb.name),
            document_count=int(getattr(kb, "document_count", 0) or 0),
            mounted=str(kb.id) in mounted_ids,
        )
        for kb in visible_knowledge_bases
    ]
    missing_ids = [kb_id for kb_id in mounted_ids if kb_id not in visible_by_id]
    return WorkspaceKnowledgeBaseMountResponse(
        workspace_id=workspace_id,
        knowledge_base_ids=mounted_ids,
        mounted_knowledge_bases=mounted_knowledge_bases,
        available_knowledge_bases=available_knowledge_bases,
        missing_knowledge_base_ids=missing_ids,
    )


async def _list_available_knowledge_graphs(
    user_id: str = "local_default",
) -> list[dict[str, object]]:
    from app.graphrag.core import SQLiteGraphStore

    available_graphs: list[dict[str, object]] = []
    for graph in SQLiteGraphStore.list_graphs(user_id):
        graph_id = str(graph.get("kg_id") or "").strip()
        if not graph_id:
            continue
        available_graphs.append(
            {
                "id": graph_id,
                "name": str(graph.get("name") or graph_id),
                "entity_count": int(graph.get("entity_count", 0) or 0),
                "relation_count": int(graph.get("relation_count", 0) or 0),
                "llm_status": str(graph.get("llm_status") or "available"),
            }
        )
    return available_graphs


def _describe_workspace_database_connector(connector: object) -> str | None:
    connection_url_masked = getattr(connector, "connection_url_masked", None)
    if isinstance(connection_url_masked, str) and connection_url_masked.strip():
        return connection_url_masked.strip()

    parts = [
        str(getattr(connector, "host", "") or "").strip() or None,
        (
            str(getattr(connector, "port", "") or "").strip()
            if getattr(connector, "port", None) is not None
            else None
        ),
        str(getattr(connector, "database_name", "") or "").strip() or None,
    ]
    normalized_parts = [part for part in parts if part]
    return " / ".join(normalized_parts) if normalized_parts else None


def _build_workspace_database_mount_response(
    *,
    workspace_id: str,
    mounted_ids: list[str],
    available_connectors: list[object],
) -> WorkspaceDatabaseMountResponse:
    visible_by_id = {
        str(getattr(connector, "connector_id")): connector
        for connector in available_connectors
        if getattr(connector, "connector_id", None)
    }
    mounted_connectors = [
        WorkspaceMountedDatabaseConnectorSummary(
            connector_id=connector_id,
            name=str(getattr(visible_by_id[connector_id], "name") or connector_id),
            db_type=str(getattr(visible_by_id[connector_id], "db_type") or "unknown"),
            readonly=bool(getattr(visible_by_id[connector_id], "readonly", True)),
            mounted=True,
            last_test_status=str(
                getattr(visible_by_id[connector_id], "last_test_status") or "untested"
            ),
            connection_summary=_describe_workspace_database_connector(visible_by_id[connector_id]),
        )
        for connector_id in mounted_ids
        if connector_id in visible_by_id
    ]
    available_connector_items = [
        WorkspaceMountedDatabaseConnectorSummary(
            connector_id=str(getattr(connector, "connector_id")),
            name=str(getattr(connector, "name") or getattr(connector, "connector_id")),
            db_type=str(getattr(connector, "db_type") or "unknown"),
            readonly=bool(getattr(connector, "readonly", True)),
            mounted=str(getattr(connector, "connector_id")) in mounted_ids,
            last_test_status=str(getattr(connector, "last_test_status") or "untested"),
            connection_summary=_describe_workspace_database_connector(connector),
        )
        for connector in available_connectors
        if getattr(connector, "connector_id", None)
    ]
    missing_ids = [
        connector_id for connector_id in mounted_ids if connector_id not in visible_by_id
    ]
    return WorkspaceDatabaseMountResponse(
        workspace_id=workspace_id,
        connector_ids=mounted_ids,
        mounted_database_connectors=mounted_connectors,
        available_database_connectors=available_connector_items,
        missing_connector_ids=missing_ids,
    )
