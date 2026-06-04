"""
Overview 构建
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from app.api.routes.workspaces_runtime_utils import (
    _is_runtime_busy,
    _resolve_runtime_control_capability,
)
from app.models.workspace import (
    WorkspaceConversationSummary,
    WorkspaceDetailResponse,
    WorkspaceOverviewArtifacts,
    WorkspaceOverviewConfig,
    WorkspaceOverviewExperts,
    WorkspaceOverviewMemory,
    WorkspaceOverviewResourceBucket,
    WorkspaceOverviewResources,
    WorkspaceOverviewResponse,
    WorkspaceOverviewRuntime,
    WorkspaceOverviewSession,
    WorkspaceOverviewVerificationSummary,
    WorkspaceOverviewWorkspace,
    WorkspaceResourceLayerSummaryResponse,
)
from app.services.expert_roles import get_workspace_expert_catalog
from app.services.runtime.session_runtime_state import build_session_runtime_summary

logger = logging.getLogger(__name__)


def _normalize_overview_ids(value) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _count_files_under(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.rglob("*") if item.is_file())


def _overview_resource_status(
    *,
    user_asset_count: int = 0,
    workspace_default_count: int = 0,
    session_attached_count: int = 0,
    runtime_available_count: int = 0,
    unavailable: bool = False,
) -> str:
    if unavailable:
        return "unavailable"
    if runtime_available_count > 0:
        return "ready"
    if session_attached_count > 0 or workspace_default_count > 0:
        return "not_verified"
    if user_asset_count > 0:
        return "empty"
    return "empty"


def _build_workspace_overview_workspace(
    workspace: WorkspaceDetailResponse,
) -> WorkspaceOverviewWorkspace:
    return WorkspaceOverviewWorkspace(
        workspace_id=workspace.workspace_id,
        title=workspace.title,
        description=workspace.description,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
        status=workspace.status,
        workspace_kind=workspace.workspace_kind,
        execution_policy=workspace.execution_policy,
        runtime_binding=workspace.runtime_binding,
        current_conversation_id=workspace.current_conversation_id,
        conversation_count=workspace.conversation_count,
    )


def _build_workspace_overview_session(
    conversation: WorkspaceConversationSummary,
    *,
    current_conversation_id: str | None,
) -> WorkspaceOverviewSession:
    return WorkspaceOverviewSession(
        workspace_id=conversation.workspace_id,
        conversation_id=conversation.conversation_id,
        session_id=conversation.session_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        status=conversation.status,
        execution_policy=conversation.execution_policy,
        message_count=conversation.message_count,
        execution_record_count=conversation.execution_record_count,
        last_execution_status=conversation.last_execution_status,
        last_execution_record_id=conversation.last_execution_record_id,
        source=conversation.source,
        conversation_type=conversation.conversation_type,
        bound_host_session_id=conversation.bound_host_session_id,
        is_current=conversation.conversation_id == current_conversation_id,
    )


def _build_empty_overview_resources() -> WorkspaceOverviewResources:
    return WorkspaceOverviewResources(
        mcp=WorkspaceOverviewResourceBucket(resource_key="mcp", display_name="MCP"),
        knowledge_base=WorkspaceOverviewResourceBucket(
            resource_key="knowledge_base",
            display_name="知识库",
        ),
        knowledge_graph=WorkspaceOverviewResourceBucket(
            resource_key="knowledge_graph",
            display_name="知识图谱",
        ),
        database=WorkspaceOverviewResourceBucket(
            resource_key="database",
            display_name="数据库",
        ),
        file=WorkspaceOverviewResourceBucket(resource_key="file", display_name="文件"),
        verification=WorkspaceOverviewVerificationSummary(),
    )


async def _build_workspace_overview(
    *,
    service,
    user_id: str,
    workspace_id: str,
) -> WorkspaceOverviewResponse:
    from app.knowledge import get_sqlite_kb_service
    from app.services.connector import DatabaseConnectorService
    from app.services.session.config_projection import (
        build_runtime_config_projection,
        build_workspace_capability_summary,
        read_workspace_database_mount_data,
    )

    workspace = service.get_workspace(
        user_id,
        workspace_id,
        include_conversations=True,
    )
    workspace_dir = service._get_workspace_dir(user_id, workspace_id)
    current_session = workspace.current_conversation
    current_session_id = current_session.session_id if current_session else None

    execution_summary: dict = {}
    metadata = None
    session_dir: Path | None = None
    runtime_busy = False
    runtime_summary: dict = {}
    runtime = WorkspaceOverviewRuntime()
    config_projection: dict = {}

    if current_session_id:
        metadata = service.session_manager.get_session(current_session_id, user_id)
        execution_summary = service.session_manager.get_execution_summary(
            current_session_id,
            user_id,
        )
        session_dir = service.session_manager._get_session_dir(
            current_session_id,
            user_id,
        )
        runtime_busy = _is_runtime_busy(user_id, current_session_id)
        sandbox_mode = (
            getattr(metadata, "sandbox_mode", None) or workspace.runtime_binding.sandbox_mode
        )
        env_id = getattr(metadata, "env_id", None) or workspace.runtime_binding.env_id
        runtime_summary = build_session_runtime_summary(
            session_dir=session_dir,
            session_id=current_session_id,
            user_id=user_id,
            sandbox_mode=sandbox_mode,
            env_id=env_id,
            last_runtime_state=execution_summary.get("last_runtime_state"),
            runtime_busy=runtime_busy,
        )
        can_start_runtime, can_stop_runtime, runtime_control_reason = (
            _resolve_runtime_control_capability(runtime_summary)
        )
        runtime = WorkspaceOverviewRuntime(
            session_id=current_session_id,
            env_id=env_id,
            sandbox_mode=sandbox_mode,
            last_runtime_state=execution_summary.get("last_runtime_state"),
            runtime_busy=runtime_busy,
            can_start_runtime=can_start_runtime,
            can_stop_runtime=can_stop_runtime,
            runtime_control_reason=runtime_control_reason,
            runtime_summary=runtime_summary,
        )
        try:
            config_projection = await build_runtime_config_projection(
                session_dir=session_dir,
                user_id=user_id,
                session_id=current_session_id,
                sandbox_mode=sandbox_mode,
                runtime_busy=runtime_busy,
            )
        except Exception as exc:
            logger.warning(
                "构建工作区概览配置投影失败: workspace=%s session=%s error=%s",
                workspace_id,
                current_session_id,
                exc,
            )
            config_projection = {
                "config_sync_state": "unknown",
                "projection_error": str(exc),
            }

    try:
        capability_summary = build_workspace_capability_summary(workspace_dir)
    except Exception as exc:
        logger.warning("构建工作区能力摘要失败: workspace=%s error=%s", workspace_id, exc)
        capability_summary = {"summary_error": str(exc)}

    database_mounts = read_workspace_database_mount_data(workspace_dir)

    database_connector_count = 0
    database_attachment_ids: list[str] = []
    database_error: str | None = None
    try:
        connector_service = DatabaseConnectorService(
            service.base_dir,
            session_manager=service.session_manager,
        )
        database_connector_count = len(
            connector_service.list_connectors(user_id, workspace_id=workspace_id)
        )
        if current_session_id:
            database_attachment_ids = [
                item.connector_id
                for item in connector_service.list_session_attachments(
                    user_id,
                    current_session_id,
                )
            ]
    except Exception as exc:
        database_error = str(exc)

    knowledge_base_count = 0
    knowledge_base_error: str | None = None
    knowledge_base_ids: list[str] = []
    try:
        knowledge_base_ids = _normalize_overview_ids(
            [
                str(kb.id)
                for kb in get_sqlite_kb_service().list_knowledge_bases(user_id)
                if getattr(kb, "id", None)
            ]
        )
        knowledge_base_count = len(knowledge_base_ids)
    except Exception as exc:
        knowledge_base_error = str(exc)

    knowledge_graphs: list[dict[str, Any]] = []
    try:
        from app.graphrag.core import SQLiteGraphStore

        knowledge_graphs = SQLiteGraphStore.list_graphs(user_id)
        knowledge_graph_ids = [g["kg_id"] for g in knowledge_graphs]
    except Exception:
        knowledge_graph_ids = []

    mcp_enabled_names = _normalize_overview_ids(capability_summary.get("enabled_mcp_server_names"))
    database_default_ids = _normalize_overview_ids(database_mounts.get("connector_ids"))
    knowledge_graph_default_ids = _normalize_overview_ids(knowledge_graph_ids)
    workspace_file_count = _count_files_under(workspace_dir / "workspace")
    artifact_file_count = _count_files_under(workspace_dir / "artifacts")

    resources = WorkspaceOverviewResources(
        mcp=WorkspaceOverviewResourceBucket(
            resource_key="mcp",
            display_name="MCP",
            status=_overview_resource_status(
                user_asset_count=int(capability_summary.get("mcp_server_count") or 0),
                workspace_default_count=len(mcp_enabled_names),
                session_attached_count=len(mcp_enabled_names),
            ),
            user_asset_count=int(capability_summary.get("mcp_server_count") or 0),
            workspace_default_count=len(mcp_enabled_names),
            session_attached_count=len(mcp_enabled_names),
            runtime_available_count=0,
            configured=bool(mcp_enabled_names),
            mounted=bool(mcp_enabled_names),
            verified=False,
            available=False,
            stale=True if mcp_enabled_names else False,
            primary_action=("verify_resource" if mcp_enabled_names else "configure_mcp"),
            next_check_hint=(
                "打开资源验活或传 refresh=true 重新握手。"
                if mcp_enabled_names
                else "当前工作区还没有启用 MCP 服务。"
            ),
            ids=mcp_enabled_names,
            detail="概览接口不执行 MCP 握手，真实可用性以后端验活接口为准。",
            metadata={
                "enabled_server_names": mcp_enabled_names,
                "mcp_config_version": capability_summary.get("mcp_config_version"),
            },
        ),
        knowledge_base=WorkspaceOverviewResourceBucket(
            resource_key="knowledge_base",
            display_name="知识库",
            status=_overview_resource_status(
                user_asset_count=knowledge_base_count,
                workspace_default_count=len(knowledge_base_ids),
                session_attached_count=len(knowledge_base_ids),
                unavailable=knowledge_base_error is not None,
            ),
            user_asset_count=knowledge_base_count,
            workspace_default_count=len(knowledge_base_ids),
            session_attached_count=len(knowledge_base_ids),
            runtime_available_count=0,
            configured=bool(knowledge_base_ids),
            mounted=bool(knowledge_base_ids),
            verified=False,
            available=False,
            stale=True if knowledge_base_ids else False,
            primary_action=("verify_resource" if knowledge_base_ids else "mount_knowledge_base"),
            disabled_reason=("知识库服务当前不可用" if knowledge_base_error is not None else None),
            next_check_hint=(
                "资源验活会执行一次最小检索。"
                if knowledge_base_ids
                else "可先在工作区设置中挂载知识库。"
            ),
            ids=knowledge_base_ids,
            detail=knowledge_base_error,
        ),
        knowledge_graph=WorkspaceOverviewResourceBucket(
            resource_key="knowledge_graph",
            display_name="知识图谱",
            status=_overview_resource_status(
                user_asset_count=len(knowledge_graph_ids),
                workspace_default_count=len(knowledge_graph_default_ids),
                session_attached_count=len(knowledge_graph_default_ids),
            ),
            user_asset_count=len(knowledge_graph_ids),
            workspace_default_count=len(knowledge_graph_default_ids),
            session_attached_count=len(knowledge_graph_default_ids),
            runtime_available_count=0,
            configured=bool(knowledge_graph_default_ids),
            mounted=bool(knowledge_graph_default_ids),
            verified=False,
            available=False,
            stale=True if knowledge_graph_default_ids else False,
            primary_action=(
                "verify_resource" if knowledge_graph_default_ids else "mount_knowledge_graph"
            ),
            next_check_hint=(
                "资源验活会检查图谱健康状态。"
                if knowledge_graph_default_ids
                else "可先在工作区设置中挂载知识图谱。"
            ),
            ids=knowledge_graph_default_ids,
            metadata={
                "primary_knowledge_graph_id": None,
                "available_graph_ids": knowledge_graph_ids,
                "available_graphs": [
                    {
                        "id": graph["kg_id"],
                        "name": graph.get("name") or graph["kg_id"],
                    }
                    for graph in knowledge_graphs
                    if graph.get("kg_id")
                ],
            },
        ),
        database=WorkspaceOverviewResourceBucket(
            resource_key="database",
            display_name="数据库",
            status=_overview_resource_status(
                user_asset_count=database_connector_count,
                workspace_default_count=len(database_default_ids),
                session_attached_count=len(database_attachment_ids),
                runtime_available_count=len(database_attachment_ids),
                unavailable=database_error is not None,
            ),
            user_asset_count=database_connector_count,
            workspace_default_count=len(database_default_ids),
            session_attached_count=len(database_attachment_ids),
            runtime_available_count=len(database_attachment_ids),
            configured=bool(database_default_ids),
            mounted=bool(database_attachment_ids),
            verified=False,
            available=bool(database_attachment_ids),
            stale=True if database_default_ids or database_attachment_ids else False,
            primary_action=(
                "verify_resource"
                if database_default_ids or database_attachment_ids
                else "mount_database_connector"
            ),
            disabled_reason=("数据库连接器服务当前不可用" if database_error is not None else None),
            next_check_hint=(
                "资源验活会执行连接测试和最小表结构探针。"
                if database_default_ids or database_attachment_ids
                else "可先在资源管理中创建数据库连接器。"
            ),
            ids=database_attachment_ids or database_default_ids,
            detail=database_error,
            metadata={"workspace_default_connector_ids": database_default_ids},
        ),
        file=WorkspaceOverviewResourceBucket(
            resource_key="file",
            display_name="文件",
            status="ready" if workspace_file_count > 0 else "empty",
            workspace_default_count=workspace_file_count,
            session_attached_count=workspace_file_count,
            runtime_available_count=workspace_file_count,
            configured=workspace_file_count > 0,
            mounted=workspace_file_count > 0,
            verified=True,
            available=workspace_file_count > 0,
            primary_action=("open_workspace_files" if workspace_file_count > 0 else "upload_file"),
            next_check_hint="文件资产按工作区文件目录实时读取。",
            metadata={"workspace_file_count": workspace_file_count},
        ),
        verification=WorkspaceOverviewVerificationSummary(
            status="not_verified",
            resource_count=5,
        ),
    )

    expert_status = WorkspaceOverviewExperts()
    try:
        expert_catalog = get_workspace_expert_catalog(
            user_id=user_id,
            workspace_id=workspace_id,
        )
        role_ids = [role.role_id for role in expert_catalog.roles]
        configured_role_ids = getattr(metadata, "enabled_expert_role_ids", None)
        enabled_role_ids = (
            [role_id for role_id in configured_role_ids if role_id in role_ids]
            if isinstance(configured_role_ids, list)
            else role_ids
        )
        expert_status = WorkspaceOverviewExperts(
            profile_name=expert_catalog.profile_name,
            available_role_count=len(role_ids),
            enabled_role_count=len(enabled_role_ids),
            enabled_role_ids=enabled_role_ids,
            status="ready" if role_ids else "empty",
        )
    except Exception:
        expert_status = WorkspaceOverviewExperts(
            status="unavailable",
            detail="Operation failed",
        )

    memory_preview = config_projection.get("memory_snapshot_preview")
    if not isinstance(memory_preview, dict):
        memory_preview = {}
    rendered_memory = str(memory_preview.get("rendered_markdown") or "").strip()
    has_memory = bool(rendered_memory)
    memory = WorkspaceOverviewMemory(
        effect=config_projection.get("memory_effect") or "next_run_only",
        has_memory=has_memory,
        document_count=1 if has_memory else 0,
        version=config_projection.get("current_memory_snapshot_version"),
        snapshot_hash=config_projection.get("current_memory_snapshot_hash"),
        pending_snapshot_version=config_projection.get("pending_memory_snapshot_version"),
        preview=memory_preview,
    )

    sessions = [
        _build_workspace_overview_session(
            conversation,
            current_conversation_id=workspace.current_conversation_id,
        )
        for conversation in workspace.conversations
    ]
    current_session_overview = next(
        (session for session in sessions if session.is_current),
        None,
    )

    return WorkspaceOverviewResponse(
        generated_at=datetime.now().isoformat(),
        workspace=_build_workspace_overview_workspace(workspace),
        current_session=current_session_overview,
        sessions=sessions,
        runtime=runtime,
        config=WorkspaceOverviewConfig(
            config_sync_state=config_projection.get("config_sync_state") or "unknown",
            agent_config_effect=config_projection.get("agent_config_effect") or "next_run_only",
            task_profile_effect="next_run_only",
            memory_effect=config_projection.get("memory_effect") or "next_run_only",
            can_edit_agent_config_now=bool(
                config_projection.get("can_edit_agent_config_now", False)
            ),
            can_edit_task_profile_now=not runtime_busy,
            rebuild_required=bool(config_projection.get("rebuild_required", False)),
            rebuild_required_reasons=list(config_projection.get("rebuild_required_reasons") or []),
            current_agent_config_version=config_projection.get("current_agent_config_version"),
            applied_agent_config_version=config_projection.get("applied_agent_config_version"),
            pending_agent_config_version=config_projection.get("pending_agent_config_version"),
            current_capability_snapshot_version=config_projection.get(
                "current_capability_snapshot_version"
            ),
            applied_capability_snapshot_version=config_projection.get(
                "applied_capability_snapshot_version"
            ),
            pending_capability_snapshot_version=config_projection.get(
                "pending_capability_snapshot_version"
            ),
            config_state_updated_at=config_projection.get("config_state_updated_at"),
            projection=config_projection,
        ),
        resources=resources,
        experts=expert_status,
        artifacts=WorkspaceOverviewArtifacts(
            workspace_file_count=workspace_file_count,
            artifact_file_count=artifact_file_count,
            execution_record_count=int(execution_summary.get("execution_record_count") or 0),
            last_execution_status=execution_summary.get("last_execution_status"),
            last_execution_record_id=execution_summary.get("last_execution_record_id"),
        ),
        memory=memory,
    )


async def _build_workspace_resource_layer_summary(
    *,
    service,
    user_id: str,
    workspace_id: str,
) -> WorkspaceResourceLayerSummaryResponse:
    overview = await _build_workspace_overview(
        service=service,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    return WorkspaceResourceLayerSummaryResponse(
        workspace_id=workspace_id,
        session_id=overview.runtime.session_id,
        generated_at=overview.generated_at,
        resources=overview.resources,
    )
