import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import require_auth
from app.models.user import UserInfo
from app.models.workspace import (
    ResourceVerificationCheck,
    ResourceVerificationItem,
    WorkspaceResourceVerificationResponse,
)
from app.services.workspace_registry import get_workspace_registry_service

from .workspaces_resources_utils import (
    _read_resource_verification_cache,
    _write_resource_verification_cache,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/{workspace_id}/resource-verification",
    response_model=WorkspaceResourceVerificationResponse,
)
async def get_workspace_resource_verification(
    workspace_id: str,
    refresh: bool = Query(False, description="是否跳过缓存并重新执行资源验活"),
    current_user: UserInfo = Depends(require_auth()),
):
    refresh_value = refresh if isinstance(refresh, bool) else False
    service = get_workspace_registry_service()
    try:
        workspace = service.get_workspace(
            current_user.user_id,
            workspace_id,
            include_conversations=True,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    workspace_dir = service._get_workspace_dir(current_user.user_id, workspace_id)
    if not refresh_value:
        cached = _read_resource_verification_cache(workspace_dir)
        if cached is not None:
            return cached

    current_session_id = (
        workspace.current_conversation.session_id if workspace.current_conversation else None
    )

    resources: list[ResourceVerificationItem] = []

    from app.api.routes.mcp_session import _test_session_server_connection
    from app.core.config import WORKSPACE_DIR
    from app.knowledge import get_sqlite_kb_service
    from app.knowledge.models import QueryRequest as KnowledgeQueryRequest
    from app.services.connector import DatabaseConnectorService
    from app.services.llm import get_mcp_session_service
    from app.services.session.config_projection import (
        build_workspace_capability_summary,
    )

    capability_summary = build_workspace_capability_summary(workspace_dir)

    # MCP
    enabled_mcp_names = capability_summary.get("enabled_mcp_server_names", []) or []
    mcp_servers = (
        get_mcp_session_service().get_session_mcp_servers(
            current_user.user_id,
            current_session_id,
        )
        if current_session_id
        else []
    )
    enabled_mcp_servers = [server for server in mcp_servers if bool(server.enabled)]
    mcp_test_results = []
    for server in enabled_mcp_servers:
        try:
            mcp_test_results.append(await _test_session_server_connection(server))
        except Exception as exc:
            mcp_test_results.append(
                type(
                    "MCPTestFailure",
                    (),
                    {
                        "status": "failed",
                        "model_dump": lambda _self, server=server, exc=exc: {
                            "name": getattr(server, "name", ""),
                            "status": "failed",
                            "message": str(exc),
                        },
                    },
                )()
            )

    if not current_session_id:
        mcp_item = ResourceVerificationItem(
            resource_key="mcp",
            display_name="MCP",
            scope="task",
            session_id=None,
            mounted=False,
            mounted_summary="当前工作区还没有可用于验证的对话上下文。",
            health=ResourceVerificationCheck(
                status="skipped",
                summary="缺少当前对话",
            ),
            smoke=ResourceVerificationCheck(
                status="skipped",
                summary="缺少当前对话，无法执行任务级 MCP 握手验证",
            ),
            metadata={
                "enabled_server_names": enabled_mcp_names,
                "enabled_server_count": len(enabled_mcp_names),
            },
        )
    elif not enabled_mcp_servers:
        mcp_item = ResourceVerificationItem(
            resource_key="mcp",
            display_name="MCP",
            scope="task",
            session_id=current_session_id,
            mounted=False,
            mounted_summary="当前任务还没有启用 MCP 服务。",
            health=ResourceVerificationCheck(
                status="skipped",
                summary="没有已启用的 MCP 服务",
            ),
            smoke=ResourceVerificationCheck(
                status="skipped",
                summary="没有可执行最小握手验证的 MCP 服务",
            ),
            metadata={
                "enabled_server_names": enabled_mcp_names,
                "enabled_server_count": len(enabled_mcp_names),
            },
        )
    else:
        passed_mcp = [result for result in mcp_test_results if result.status == "connected"]
        failed_mcp = [result for result in mcp_test_results if result.status != "connected"]
        mcp_status = "passed" if not failed_mcp else "warning" if passed_mcp else "failed"
        mcp_summary = f"{len(passed_mcp)}/{len(mcp_test_results)} 个 MCP 服务握手成功"
        mcp_item = ResourceVerificationItem(
            resource_key="mcp",
            display_name="MCP",
            scope="task",
            session_id=current_session_id,
            mounted=True,
            mounted_summary=(f"当前任务已启用 {len(enabled_mcp_servers)} 个 MCP 服务。"),
            health=ResourceVerificationCheck(
                status=mcp_status,
                summary=mcp_summary,
                detail=None if not failed_mcp else "部分 MCP 服务连接失败，请展开查看详情。",
            ),
            smoke=ResourceVerificationCheck(
                status=mcp_status,
                summary="最小握手与工具枚举已执行",
                detail=None if not failed_mcp else "至少一个 MCP 服务未通过最小握手验证。",
            ),
            metadata={
                "enabled_server_names": enabled_mcp_names,
                "enabled_server_count": len(enabled_mcp_names),
                "server_results": [result.model_dump() for result in mcp_test_results],
            },
        )
    resources.append(mcp_item)

    # Knowledge base
    kb_service = get_sqlite_kb_service()
    kb_health_error: str | None = None
    try:
        _ = kb_service.list_knowledge_bases(current_user.user_id)
        kb_health = ResourceVerificationCheck(
            status="passed",
            summary="知识库服务健康",
        )
    except Exception as exc:
        kb_health_error = str(exc)
        kb_health = ResourceVerificationCheck(
            status="failed",
            summary="知识库服务不可用",
            detail="Operation failed",
        )

    if kb_health_error:
        knowledge_bases = []
    else:
        try:
            knowledge_bases = kb_service.list_knowledge_bases(current_user.user_id)
        except Exception as exc:
            kb_health_error = str(exc)
            kb_health = ResourceVerificationCheck(
                status="failed",
                summary="知识库列表不可用",
                detail="Operation failed",
                error_code="knowledge_base_list_failed",
            )
            knowledge_bases = []
    # 知识库已取消挂载，验活范围改为用户名下全部知识库
    visible_knowledge_bases_by_id = {
        str(kb.id): kb for kb in knowledge_bases if getattr(kb, "id", None)
    }
    all_knowledge_base_ids = list(visible_knowledge_bases_by_id.keys())
    kb_smoke_results = []
    if kb_health_error:
        kb_smoke = ResourceVerificationCheck(
            status="skipped",
            summary="知识库服务不可用，跳过检索验证",
        )
    elif not all_knowledge_base_ids:
        kb_smoke = ResourceVerificationCheck(
            status="skipped",
            summary="当前用户下还没有知识库",
        )
    else:
        for kb in list(visible_knowledge_bases_by_id.values()):
            try:
                query_result = await kb_service.query(
                    current_user.user_id,
                    kb.id,
                    KnowledgeQueryRequest(query="test", top_k=1),
                )
                kb_smoke_results.append(
                    {
                        "id": kb.id,
                        "name": kb.name,
                        "status": "passed",
                        "result_total": int(query_result.total or 0),
                    }
                )
            except Exception as exc:
                kb_smoke_results.append(
                    {
                        "id": kb.id,
                        "name": kb.name,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
        passed_kb_smoke = [result for result in kb_smoke_results if result["status"] == "passed"]
        failed_kb_smoke = [result for result in kb_smoke_results if result["status"] != "passed"]
        smoke_status = (
            "passed" if not failed_kb_smoke else "warning" if passed_kb_smoke else "failed"
        )
        kb_smoke = ResourceVerificationCheck(
            status=smoke_status,
            summary=(
                f"{len(passed_kb_smoke)}/{len(kb_smoke_results)} 个知识库通过最小检索"
                if kb_smoke_results
                else "没有可验证的知识库"
            ),
            detail=("部分知识库未通过最小检索验证。" if failed_kb_smoke else None),
        )

    resources.append(
        ResourceVerificationItem(
            resource_key="knowledge_base",
            display_name="知识库",
            scope="task",
            session_id=current_session_id,
            mounted=bool(all_knowledge_base_ids),
            mounted_summary=(
                f"当前用户共有 {len(all_knowledge_base_ids)} 个知识库。"
                if all_knowledge_base_ids
                else "当前用户下还没有知识库。"
            ),
            health=kb_health,
            smoke=kb_smoke,
            metadata={
                "visible_count": len(knowledge_bases),
                "available_count": len(all_knowledge_base_ids),
                "smoke_results": kb_smoke_results,
                "knowledge_bases": [
                    {
                        "id": kb.id,
                        "name": kb.name,
                        "document_count": kb.document_count,
                    }
                    for kb in knowledge_bases[:5]
                ],
            },
        )
    )

    # Knowledge graph
    # 知识图谱已取消挂载，验活范围改为全部可用图谱
    from app.api.routes.workspaces_resource_utils import _list_available_knowledge_graphs

    graph_discovery_error: str | None = None
    try:
        available_knowledge_graphs = await _list_available_knowledge_graphs(current_user.user_id)
    except Exception as exc:
        graph_discovery_error = str(exc)
        available_knowledge_graphs = []
    available_graph_ids = {item["id"] for item in available_knowledge_graphs}
    graph_health_results = []
    graph_smoke_results = []
    from app.graphrag import GraphRAGService
    from app.graphrag.core import SQLiteGraphStore

    for graph_id in sorted(available_graph_ids):
        try:
            db_path = SQLiteGraphStore.find_db_path(current_user.user_id, graph_id)
            if db_path is None:
                raise ValueError(f"知识图谱数据库文件不存在: {graph_id}")
            store = SQLiteGraphStore(
                user_id=current_user.user_id,
                kg_id=graph_id,
                db_path=db_path,
            )
            service = GraphRAGService(
                kb_id=graph_id,
                auto_init_llm=True,
                user_id=current_user.user_id,
                graph_store=store,
            )
            health_result = await service.health_check()
        except Exception as exc:
            graph_health_results.append(
                {
                    "id": graph_id,
                    "status": "failed",
                    "llm_status": "unknown",
                    "message": str(exc),
                }
            )
            graph_smoke_results.append(
                {
                    "id": graph_id,
                    "status": "failed",
                    "error": str(exc),
                }
            )
            continue
        graph_health_results.append(
            {
                "id": graph_id,
                "status": health_result.get("status"),
                "llm_status": health_result.get("llm_status"),
                "message": health_result.get("message"),
            }
        )
        try:
            graph_search_result = service.search("test", None)
            graph_smoke_results.append(
                {
                    "id": graph_id,
                    "status": "passed",
                    "result_count": len(graph_search_result),
                }
            )
        except Exception as exc:
            graph_smoke_results.append(
                {
                    "id": graph_id,
                    "status": "failed",
                    "error": str(exc),
                }
            )

    if graph_discovery_error:
        graph_health = ResourceVerificationCheck(
            status="failed",
            summary="知识图谱列表不可用",
            detail=graph_discovery_error,
            error_code="knowledge_graph_list_failed",
        )
        graph_smoke = ResourceVerificationCheck(
            status="skipped",
            summary="知识图谱列表不可用，跳过图谱搜索探针",
            detail=graph_discovery_error,
            error_code="knowledge_graph_list_failed",
        )
        graph_mounted = False
        graph_mounted_summary = "知识图谱列表暂时不可用。"
    elif not available_graph_ids:
        graph_health = ResourceVerificationCheck(
            status="skipped",
            summary="当前存储目录下还没有知识图谱",
        )
        graph_smoke = ResourceVerificationCheck(
            status="skipped",
            summary="当前存储目录下还没有知识图谱",
        )
        graph_mounted = False
        graph_mounted_summary = "当前存储目录下还没有知识图谱。"
    else:
        passed_graph_health = [item for item in graph_health_results if item["status"] == "healthy"]
        failed_graph_health = [item for item in graph_health_results if item["status"] != "healthy"]
        passed_graph_smoke = [item for item in graph_smoke_results if item["status"] == "passed"]
        failed_graph_smoke = [item for item in graph_smoke_results if item["status"] != "passed"]
        graph_health = ResourceVerificationCheck(
            status=(
                "passed"
                if not failed_graph_health
                else "warning" if passed_graph_health else "failed"
            ),
            summary=f"{len(passed_graph_health)}/{len(available_graph_ids)} 个图谱健康检查通过",
            detail=("部分图谱健康检查失败。" if failed_graph_health else None),
        )
        graph_smoke = ResourceVerificationCheck(
            status=(
                "passed"
                if not failed_graph_smoke
                else "warning" if passed_graph_smoke else "failed"
            ),
            summary=f"{len(passed_graph_smoke)}/{len(available_graph_ids)} 个图谱通过最小搜索探针",
            detail=("部分图谱未通过最小搜索探针。" if failed_graph_smoke else None),
        )
        graph_mounted = True
        graph_mounted_summary = f"当前共有 {len(available_graph_ids)} 个知识图谱。"

    resources.append(
        ResourceVerificationItem(
            resource_key="knowledge_graph",
            display_name="知识图谱",
            scope="task",
            session_id=current_session_id,
            mounted=graph_mounted,
            mounted_summary=graph_mounted_summary,
            health=graph_health,
            smoke=graph_smoke,
            metadata={
                "available_count": len(available_knowledge_graphs),
                "verified_count": len(available_graph_ids),
                "available_knowledge_graphs": [available_knowledge_graphs],
                "health_results": graph_health_results,
                "smoke_results": graph_smoke_results,
            },
        )
    )

    # Database
    connector_service = DatabaseConnectorService(WORKSPACE_DIR)
    database_list_error: str | None = None
    if current_session_id:
        try:
            attachments = connector_service.list_session_attachments(
                current_user.user_id,
                current_session_id,
            )
        except Exception as exc:
            database_list_error = str(exc)
            attachments = []
    else:
        attachments = []
    db_test_results = []
    db_smoke_results = []
    for attachment in attachments:
        try:
            test_result = connector_service.test_connector(
                current_user.user_id,
                attachment.connector_id,
            )
            serialized_test_result = test_result.model_dump() if test_result else None
        except Exception as exc:
            test_result = None
            serialized_test_result = {
                "success": False,
                "message": str(exc),
            }
        db_test_results.append(
            {
                "connector_id": attachment.connector_id,
                "name": attachment.name,
                "test": serialized_test_result,
            }
        )
        try:
            table_result = connector_service.list_attached_connector_tables(
                user_id=current_user.user_id,
                session_id=current_session_id,
                connector_id=attachment.connector_id,
            )
            db_smoke_results.append(
                {
                    "connector_id": attachment.connector_id,
                    "name": attachment.name,
                    "table_count": len(table_result.tables),
                    "status": "passed",
                }
            )
        except Exception as exc:
            db_smoke_results.append(
                {
                    "connector_id": attachment.connector_id,
                    "name": attachment.name,
                    "status": "failed",
                    "error": str(exc),
                }
            )

    if database_list_error:
        database_item = ResourceVerificationItem(
            resource_key="database",
            display_name="数据库",
            scope="task",
            session_id=current_session_id,
            mounted=False,
            mounted_summary="当前会话数据库连接列表暂时不可用。",
            health=ResourceVerificationCheck(
                status="failed",
                summary="数据库连接列表不可用",
                detail=database_list_error,
                error_code="database_attachment_list_failed",
            ),
            smoke=ResourceVerificationCheck(
                status="skipped",
                summary="数据库连接列表不可用，跳过表结构探针",
                detail=database_list_error,
                error_code="database_attachment_list_failed",
            ),
        )
    elif not current_session_id:
        database_item = ResourceVerificationItem(
            resource_key="database",
            display_name="数据库",
            scope="task",
            session_id=None,
            mounted=False,
            mounted_summary="当前工作区还没有可用于验证的对话上下文。",
            health=ResourceVerificationCheck(
                status="skipped",
                summary="缺少当前对话",
            ),
            smoke=ResourceVerificationCheck(
                status="skipped",
                summary="缺少当前对话，无法验证数据库挂载",
            ),
        )
    elif not attachments:
        database_item = ResourceVerificationItem(
            resource_key="database",
            display_name="数据库",
            scope="task",
            session_id=current_session_id,
            mounted=False,
            mounted_summary="当前任务还没有挂载数据库连接。",
            health=ResourceVerificationCheck(
                status="skipped",
                summary="没有数据库挂载",
            ),
            smoke=ResourceVerificationCheck(
                status="skipped",
                summary="没有可执行最小表结构探针的数据库连接",
            ),
        )
    else:
        passed_db_health = [
            item for item in db_test_results if item["test"] and item["test"]["success"]
        ]
        failed_db_health = [
            item for item in db_test_results if not item["test"] or not item["test"]["success"]
        ]
        passed_db_smoke = [item for item in db_smoke_results if item["status"] == "passed"]
        failed_db_smoke = [item for item in db_smoke_results if item["status"] != "passed"]
        database_item = ResourceVerificationItem(
            resource_key="database",
            display_name="数据库",
            scope="task",
            session_id=current_session_id,
            mounted=True,
            mounted_summary=f"当前任务已挂载 {len(attachments)} 个数据库连接。",
            health=ResourceVerificationCheck(
                status=(
                    "passed"
                    if not failed_db_health
                    else "warning" if passed_db_health else "failed"
                ),
                summary=f"{len(passed_db_health)}/{len(db_test_results)} 个数据库连接测试通过",
                detail=None if not failed_db_health else "部分数据库连接测试失败。",
            ),
            smoke=ResourceVerificationCheck(
                status=(
                    "passed" if not failed_db_smoke else "warning" if passed_db_smoke else "failed"
                ),
                summary=f"{len(passed_db_smoke)}/{len(db_smoke_results)} 个数据库通过最小表结构探针",
                detail=None if not failed_db_smoke else "部分数据库未通过最小表结构探针。",
            ),
            metadata={
                "attachments": [attachment.model_dump() for attachment in attachments],
                "test_results": db_test_results,
                "smoke_results": db_smoke_results,
            },
        )
    resources.append(database_item)

    # File assets
    workspace_files_dir = workspace_dir / "workspace"
    file_count = 0
    latest_updated_at: str | None = None
    file_health_error: str | None = None
    try:
        if workspace_files_dir.exists():
            for file_path in workspace_files_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                file_count += 1
                updated_at = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                if latest_updated_at is None or updated_at > latest_updated_at:
                    latest_updated_at = updated_at
        file_health = ResourceVerificationCheck(
            status="passed",
            summary=f"工作区文件目录可读，当前有 {file_count} 个文件",
        )
    except Exception as exc:
        file_health_error = str(exc)
        file_health = ResourceVerificationCheck(
            status="failed",
            summary="工作区文件目录不可读",
            detail="Operation failed",
            error_code="workspace_files_unreadable",
        )
    file_item = ResourceVerificationItem(
        resource_key="file",
        display_name="文件资产",
        scope="task",
        session_id=current_session_id,
        mounted=file_count > 0,
        mounted_summary=(
            f"当前工作区有 {file_count} 个可见文件。"
            if file_count > 0
            else "当前工作区还没有可见文件。"
        ),
        health=file_health,
        smoke=ResourceVerificationCheck(
            status="skipped" if file_health_error else "passed",
            summary=(
                "文件资产路径检查已完成"
                if file_health_error is None
                else "文件目录不可读，跳过路径检查"
            ),
            detail=file_health_error,
            error_code="workspace_files_unreadable" if file_health_error else None,
        ),
        metadata={
            "file_count": file_count,
            "latest_updated_at": latest_updated_at,
            "workspace_files_dir": str(workspace_files_dir),
        },
    )
    resources.append(file_item)

    response = WorkspaceResourceVerificationResponse(
        workspace_id=workspace_id,
        checked_at=datetime.now().isoformat(),
        session_id=current_session_id,
        resources=resources,
        verification_source="computed",
        cache_hit=False,
    )
    _write_resource_verification_cache(workspace_dir, response)
    return response
