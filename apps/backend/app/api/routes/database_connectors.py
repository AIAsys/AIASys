"""
外部数据库连接器 API
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import require_auth
from app.core.config import WORKSPACE_DIR
from app.models.database_connector import (
    DatabaseConnector,
    DatabaseConnectorCapability,
    DatabaseConnectorDraft,
    DatabaseConnectorTestResult,
    DatabaseDescribeTableRequest,
    DatabaseDescribeTableResponse,
    DatabaseListTablesRequest,
    DatabaseListTablesResponse,
    ReadonlyDatabaseQueryRequest,
    ReadonlyDatabaseQueryResponse,
    SessionDatabaseAttachment,
    SessionDatabaseAttachmentRequest,
    UpdateDatabaseConnectorRequest,
)
from app.models.user import UserInfo
from app.services.connector import DatabaseConnectorService
from app.services.session import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/database-connectors", tags=["database-connectors"])
_CONNECTOR_SERVICE = DatabaseConnectorService(WORKSPACE_DIR)
_SESSION_MANAGER = SessionManager(WORKSPACE_DIR)


def _resolve_user_scope(request_user_id: Optional[str], current_user: UserInfo) -> str:
    """解析本次请求的用户范围。"""
    if request_user_id:
        if not current_user.can_access_user_data(request_user_id):
            raise HTTPException(status_code=403, detail="无权访问该用户的数据库连接器")
        return request_user_id
    return current_user.user_id


def _ensure_session_access(session_id: str, user_id: str) -> None:
    """校验会话存在。"""
    if _SESSION_MANAGER.get_session(session_id, user_id) is None:
        raise HTTPException(status_code=404, detail="目标会话不存在")


@router.get("/capabilities", response_model=list[DatabaseConnectorCapability])
async def list_database_capabilities():
    """返回当前平台支持的数据库连接类型。"""
    return _CONNECTOR_SERVICE.list_capabilities()


@router.get("", response_model=list[DatabaseConnector])
async def list_database_connectors(
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    workspace_id: Optional[str] = Query(
        None, description="工作区 ID，指定后仅返回该工作区可见的连接器"
    ),
    current_user: UserInfo = Depends(require_auth()),
):
    """列出当前用户的数据库连接器。"""
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    return _CONNECTOR_SERVICE.list_connectors(resolved_user_id, workspace_id=workspace_id)


@router.post("", response_model=DatabaseConnector)
async def create_database_connector(
    request: DatabaseConnectorDraft,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    workspace_id: Optional[str] = Query(None, description="工作区 ID，scope=workspace 时生效"),
    current_user: UserInfo = Depends(require_auth()),
):
    """创建数据库连接器。"""
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    return _CONNECTOR_SERVICE.create_connector(resolved_user_id, request, workspace_id=workspace_id)


@router.post("/test", response_model=DatabaseConnectorTestResult)
async def test_database_connector_draft(
    request: DatabaseConnectorDraft,
    current_user: UserInfo = Depends(require_auth()),
):
    """测试未保存的数据库连接器草稿。"""
    logger.info("数据库连接器草稿测试: user=%s type=%s", current_user.user_id, request.db_type)
    return _CONNECTOR_SERVICE.test_connector_draft(request)


@router.get("/sessions/{session_id}/attachments", response_model=list[SessionDatabaseAttachment])
async def list_session_database_attachments(
    session_id: str,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    """列出会话已挂载的数据库连接器。"""
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    _ensure_session_access(session_id, resolved_user_id)
    return _CONNECTOR_SERVICE.list_session_attachments(resolved_user_id, session_id)


@router.post("/sessions/{session_id}/attachments", response_model=SessionDatabaseAttachment)
async def attach_database_connector_to_session(
    session_id: str,
    request: SessionDatabaseAttachmentRequest,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    """向会话挂载数据库连接器。"""
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    _ensure_session_access(session_id, resolved_user_id)
    try:
        return _CONNECTOR_SERVICE.attach_connector(
            resolved_user_id,
            session_id,
            request.connector_id,
            sync_defaults=request.sync_defaults,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Resource not found") from exc


@router.post(
    "/sessions/{session_id}/tools/db_list_tables",
    response_model=DatabaseListTablesResponse,
)
async def db_list_tables(
    session_id: str,
    request: DatabaseListTablesRequest,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    """列出会话已挂载连接器可见表（agent-safe broker）。"""
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    _ensure_session_access(session_id, resolved_user_id)
    try:
        result = _CONNECTOR_SERVICE.list_attached_connector_tables(
            user_id=resolved_user_id,
            session_id=session_id,
            connector_id=request.connector_id,
        )
        logger.info(
            "database_connector_tool action=list_tables user=%s session=%s connector_id=%s audit_id=%s duration_ms=%s",
            resolved_user_id,
            session_id,
            request.connector_id,
            result.audit_id,
            result.duration_ms,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Operation failed") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail="Operation failed") from exc


@router.post(
    "/sessions/{session_id}/tools/db_describe_table",
    response_model=DatabaseDescribeTableResponse,
)
async def db_describe_table(
    session_id: str,
    request: DatabaseDescribeTableRequest,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    """查看会话已挂载连接器单表结构（agent-safe broker）。"""
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    _ensure_session_access(session_id, resolved_user_id)
    try:
        result = _CONNECTOR_SERVICE.describe_attached_connector_table(
            user_id=resolved_user_id,
            session_id=session_id,
            connector_id=request.connector_id,
            table_name=request.table_name,
        )
        logger.info(
            "database_connector_tool action=describe_table user=%s session=%s connector_id=%s audit_id=%s duration_ms=%s",
            resolved_user_id,
            session_id,
            request.connector_id,
            result.audit_id,
            result.duration_ms,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Operation failed") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail="Operation failed") from exc


@router.post(
    "/sessions/{session_id}/query",
    response_model=ReadonlyDatabaseQueryResponse,
)
async def query_attached_database_connector(
    session_id: str,
    request: ReadonlyDatabaseQueryRequest,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    """使用会话已挂载连接器执行只读查询（broker 模式）。"""
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    _ensure_session_access(session_id, resolved_user_id)
    try:
        result = _CONNECTOR_SERVICE.query_attached_connector_readonly(
            user_id=resolved_user_id,
            session_id=session_id,
            connector_id=request.connector_id,
            sql=request.sql,
            params=request.params,
            limit=request.limit,
        )
        logger.info(
            "database_connector_tool action=query user=%s session=%s connector_id=%s audit_id=%s duration_ms=%s",
            resolved_user_id,
            session_id,
            request.connector_id,
            result.audit_id,
            result.duration_ms,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Operation failed") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail="Operation failed") from exc


@router.delete("/sessions/{session_id}/attachments/{connector_id}")
async def detach_database_connector_from_session(
    session_id: str,
    connector_id: str,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    """从会话卸载数据库连接器。"""
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    _ensure_session_access(session_id, resolved_user_id)
    success = _CONNECTOR_SERVICE.detach_connector(
        resolved_user_id,
        session_id,
        connector_id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="会话未挂载该数据库连接器")
    return {"success": True, "message": "数据库连接器已卸载"}


@router.get("/{connector_id}", response_model=DatabaseConnector)
async def get_database_connector(
    connector_id: str,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    workspace_id: Optional[str] = Query(
        None, description="工作区 ID，指定后检查连接器是否对该工作区可见"
    ),
    current_user: UserInfo = Depends(require_auth()),
):
    """读取单个数据库连接器详情。"""
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    connector = _CONNECTOR_SERVICE.get_connector(
        resolved_user_id, connector_id, workspace_id=workspace_id
    )
    if connector is None:
        raise HTTPException(status_code=404, detail="数据库连接器不存在")
    return connector


@router.patch("/{connector_id}", response_model=DatabaseConnector)
async def update_database_connector(
    connector_id: str,
    request: UpdateDatabaseConnectorRequest,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    workspace_id: Optional[str] = Query(
        None, description="工作区 ID，指定后检查连接器是否对该工作区可见"
    ),
    current_user: UserInfo = Depends(require_auth()),
):
    """更新数据库连接器。"""
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    try:
        connector = _CONNECTOR_SERVICE.update_connector(
            resolved_user_id,
            connector_id,
            request,
            workspace_id=workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Operation failed") from exc
    if connector is None:
        raise HTTPException(status_code=404, detail="数据库连接器不存在")
    return connector


@router.delete("/{connector_id}")
async def delete_database_connector(
    connector_id: str,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    workspace_id: Optional[str] = Query(
        None, description="工作区 ID，指定后检查连接器是否对该工作区可见"
    ),
    current_user: UserInfo = Depends(require_auth()),
):
    """删除数据库连接器。"""
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    connector = _CONNECTOR_SERVICE.get_connector(
        resolved_user_id, connector_id, workspace_id=workspace_id
    )
    if connector is None:
        raise HTTPException(status_code=404, detail="数据库连接器不存在")
    success = _CONNECTOR_SERVICE.delete_connector(
        resolved_user_id, connector_id, workspace_id=workspace_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="数据库连接器不存在")
    return {"success": True, "message": "数据库连接器已删除"}


@router.post("/{connector_id}/test", response_model=DatabaseConnectorTestResult)
async def test_saved_database_connector(
    connector_id: str,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    workspace_id: Optional[str] = Query(
        None, description="工作区 ID，指定后检查连接器是否对该工作区可见"
    ),
    current_user: UserInfo = Depends(require_auth()),
):
    """测试已保存的数据库连接器。"""
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    connector = _CONNECTOR_SERVICE.get_connector(
        resolved_user_id, connector_id, workspace_id=workspace_id
    )
    if connector is None:
        raise HTTPException(status_code=404, detail="数据库连接器不存在")
    result = _CONNECTOR_SERVICE.test_connector(resolved_user_id, connector_id)
    if result is None:
        raise HTTPException(status_code=404, detail="数据库连接器不存在")
    return result
