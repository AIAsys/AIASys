"""
知识库 API 路由

提供知识库管理、文档上传、检索等功能
"""

import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.auth import UserInfo, get_current_user
from app.knowledge import SQLiteKBService, get_sqlite_kb_service
from app.knowledge.models import (
    BatchFileUploadResponse,
    DocumentResponse,
    FileUploadResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    QueryRequest,
    QueryResponse,
    SearchMode,
)

router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge"],
)


# ==================== 知识库管理 ====================


@router.post("/bases", response_model=KnowledgeBaseResponse)
async def create_knowledge_base(
    data: KnowledgeBaseCreate,
    user: UserInfo = Depends(get_current_user),
    service: SQLiteKBService = Depends(get_sqlite_kb_service),
):
    """创建知识库"""
    try:
        return service.create_knowledge_base(user.user_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/bases", response_model=List[KnowledgeBaseResponse])
async def list_knowledge_bases(
    skip: int = 0,
    limit: int = 100,
    user: UserInfo = Depends(get_current_user),
    service: SQLiteKBService = Depends(get_sqlite_kb_service),
):
    """列出当前用户的知识库"""
    return service.list_knowledge_bases(user.user_id, skip=skip, limit=limit)


@router.get("/bases/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    kb_id: str,
    user: UserInfo = Depends(get_current_user),
    service: SQLiteKBService = Depends(get_sqlite_kb_service),
):
    """获取知识库详情"""
    kb = service.get_knowledge_base(user.user_id, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return kb


@router.put("/bases/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: str,
    data: KnowledgeBaseUpdate,
    user: UserInfo = Depends(get_current_user),
    service: SQLiteKBService = Depends(get_sqlite_kb_service),
):
    """更新知识库"""
    try:
        kb = service.update_knowledge_base(user.user_id, kb_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return kb


@router.delete("/bases/{kb_id}")
async def delete_knowledge_base(
    kb_id: str,
    user: UserInfo = Depends(get_current_user),
    service: SQLiteKBService = Depends(get_sqlite_kb_service),
):
    """删除知识库"""
    success = service.delete_knowledge_base(user.user_id, kb_id)
    if not success:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return {"success": True, "message": "知识库已删除"}


# ==================== 文档管理 ====================


@router.post("/bases/{kb_id}/docs/upload", response_model=FileUploadResponse)
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    extraction_mode: Optional[str] = Form(default=None),
    embedding_model: Optional[str] = Form(default=None),
    chunk_size: Optional[int] = Form(default=None),
    chunk_overlap: Optional[int] = Form(default=None),
    search_mode: Optional[SearchMode] = Form(default=None),
    user: UserInfo = Depends(get_current_user),
    service: SQLiteKBService = Depends(get_sqlite_kb_service),
):
    """上传文档到知识库"""
    # 读取文件内容
    content = await file.read()

    # 上传并处理
    result = await service.upload_document(
        user_id=user.user_id,
        kb_id=kb_id,
        filename=file.filename,
        file_bytes=content,
        extraction_mode=extraction_mode,
        embedding_model=embedding_model,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        search_mode=search_mode,
    )

    return result


@router.post("/bases/{kb_id}/docs/batch-upload", response_model=BatchFileUploadResponse)
async def upload_documents(
    kb_id: str,
    files: List[UploadFile] = File(...),
    extraction_mode: Optional[str] = Form(default=None),
    embedding_model: Optional[str] = Form(default=None),
    chunk_size: Optional[int] = Form(default=None),
    chunk_overlap: Optional[int] = Form(default=None),
    search_mode: Optional[SearchMode] = Form(default=None),
    user: UserInfo = Depends(get_current_user),
    service: SQLiteKBService = Depends(get_sqlite_kb_service),
):
    """批量上传文档到知识库"""
    if not files:
        raise HTTPException(status_code=400, detail="至少选择一个文件")
    payload: list[tuple[str, bytes]] = []
    for file in files:
        payload.append((file.filename or "untitled", await file.read()))
    return await service.upload_documents(
        user_id=user.user_id,
        kb_id=kb_id,
        files=payload,
        extraction_mode=extraction_mode,
        embedding_model=embedding_model,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        search_mode=search_mode,
    )


@router.get("/bases/{kb_id}/docs", response_model=List[DocumentResponse])
async def list_documents(
    kb_id: str,
    skip: int = 0,
    limit: int = 100,
    user: UserInfo = Depends(get_current_user),
    service: SQLiteKBService = Depends(get_sqlite_kb_service),
):
    """列出知识库中的文档"""
    return service.list_documents(user.user_id, kb_id, skip=skip, limit=limit)


@router.delete("/bases/{kb_id}/docs/{doc_id}")
async def delete_document(
    kb_id: str,
    doc_id: str,
    user: UserInfo = Depends(get_current_user),
    service: SQLiteKBService = Depends(get_sqlite_kb_service),
):
    """删除文档"""
    success = service.delete_document(user.user_id, kb_id, doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"success": True, "message": "文档已删除"}


# ==================== 检索 ====================


@router.post("/bases/{kb_id}/query", response_model=QueryResponse)
async def query_knowledge_base(
    kb_id: str,
    request: QueryRequest,
    user: UserInfo = Depends(get_current_user),
    service: SQLiteKBService = Depends(get_sqlite_kb_service),
):
    """检索知识库"""
    try:
        return await service.query(user.user_id, kb_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ==================== 原始数据探查 ====================


class RawQueryRequest(BaseModel):
    sql: str = Field(
        max_length=4096,
        description="仅允许 SELECT 查询，最大 4096 字符",
    )


class RawQueryResponse(BaseModel):
    columns: List[str]
    rows: List[Dict[str, Any]]
    row_count: int


class TableInfoResponse(BaseModel):
    name: str
    columns: List[Dict[str, Any]]


@router.get("/bases/{kb_id}/tables", response_model=List[TableInfoResponse])
async def list_kb_tables(
    kb_id: str,
    user: UserInfo = Depends(get_current_user),
    service: SQLiteKBService = Depends(get_sqlite_kb_service),
):
    """获取知识库底层 SQLite 数据库的表列表和列信息"""
    kb = service.get_knowledge_base(user.user_id, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    try:
        tables = service.list_tables(user.user_id, kb_id)
        return [TableInfoResponse(**t) for t in tables]
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to list tables") from exc


@router.post("/bases/{kb_id}/raw-query", response_model=RawQueryResponse)
async def execute_kb_raw_query(
    kb_id: str,
    request: RawQueryRequest,
    user: UserInfo = Depends(get_current_user),
    service: SQLiteKBService = Depends(get_sqlite_kb_service),
):
    """对知识库底层 SQLite 数据库执行原始 SELECT 查询"""
    kb = service.get_knowledge_base(user.user_id, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    stripped = request.sql.strip()
    if not re.match(r"^SELECT\b", stripped, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="仅允许 SELECT 查询")
    try:
        result = service.execute_raw_sql(user.user_id, kb_id, request.sql)
        return RawQueryResponse(**result)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid SQL query")
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Query execution failed") from exc


# ==================== 健康检查 ====================


class HealthResponse(BaseModel):
    status: str
    db_path: str
    message: Optional[str] = None


@router.get("/health", response_model=HealthResponse)
async def health_check(
    user: UserInfo = Depends(get_current_user),
    service: SQLiteKBService = Depends(get_sqlite_kb_service),
):
    """知识库服务健康检查"""
    try:
        knowledge_bases = service.list_knowledge_bases(user.user_id, skip=0, limit=1)
        health_path = (
            service._db_path(
                service._resolve_workspace_root_for_kb(user.user_id, knowledge_bases[0].id),
                knowledge_bases[0].id,
            ).parent
            if knowledge_bases
            else "knowledge"
        )
        return HealthResponse(
            status="healthy",
            db_path=str(health_path),
            message="SQLite 知识库服务运行正常",
        )
    except Exception as e:
        return HealthResponse(status="unhealthy", db_path="", message=str(e))
