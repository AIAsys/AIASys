"""
GraphRAG API 路由
集成到 FastAPI 应用
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from app.core.auth import require_auth

from ..core import SQLiteGraphStore
from ..service import GraphRAGService

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/graph", tags=["GraphRAG"])


# ============ 请求/响应模型 ============


class AddDocumentRequest(BaseModel):
    content: str
    doc_id: Optional[str] = None
    resolve_entities: bool = True


class AddDocumentResponse(BaseModel):
    doc_id: str
    entity_count: int
    relation_count: int
    token_count: int
    merged_entities: int


class UploadDocumentResponse(AddDocumentResponse):
    filename: str
    file_type: str
    extraction_mode: str
    requested_mode: str
    warnings: List[str] = []
    text_length: int


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    depth: int = 1
    use_communities: bool = False


class QueryResponse(BaseModel):
    question: str
    entities: List[Dict[str, Any]]
    context: str
    subgraph_stats: Dict[str, int]
    subgraph: Dict[str, Any]
    communities: Optional[List[Dict[str, Any]]] = None


class EntityResponse(BaseModel):
    entity_id: Optional[str] = None
    name: str
    entity_type: str
    description: Optional[str] = None
    properties: Dict[str, Any] = {}


class UpdateEntityRequest(BaseModel):
    name: Optional[str] = None
    entity_type: Optional[str] = None
    description: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None


class CreateEntityRequest(BaseModel):
    name: str
    entity_type: str = "concept"
    description: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)


class CreateRelationRequest(BaseModel):
    source_entity_id: str
    target_entity_id: str
    relation_type: str = "related_to"
    description: Optional[str] = None
    strength: float = 1.0
    properties: Dict[str, Any] = Field(default_factory=dict)


class RelationResponse(BaseModel):
    relation_id: str
    source: str
    source_name: str
    target: str
    target_name: str
    relation_type: str
    description: Optional[str] = None
    strength: float = 1.0
    properties: Dict[str, Any] = {}


class DeleteEntityResponse(BaseModel):
    entity_id: str
    name: str
    deleted_relations: int


class StatisticsResponse(BaseModel):
    entity_count: int
    relation_count: int
    entity_types: List[str]
    communities: Optional[Dict[str, int]] = None
    llm_status: str = "unknown"


class CommunitySummary(BaseModel):
    community_id: str
    size: int
    weight: float
    entity_types: Dict[str, int]
    key_entities: List[str]


class VisualizationNode(BaseModel):
    id: str
    name: str
    entity_type: str
    description: str = ""
    degree: int = 0
    community_ids: List[str] = []
    primary_community: Optional[str] = None
    properties: Dict[str, Any] = {}


class VisualizationEdge(BaseModel):
    id: str
    source: str
    target: str
    relation_type: str = ""
    description: str = ""
    strength: float = 1.0
    metadata: Dict[str, Any] = {}


class LayoutPosition(BaseModel):
    x: float
    y: float


class SaveLayoutRequest(BaseModel):
    positions: Dict[str, LayoutPosition]


class VisualizationResponse(BaseModel):
    source: str
    nodes: List[VisualizationNode]
    edges: List[VisualizationEdge]
    truncated: bool = False
    total_nodes: int
    total_edges: int
    layout_positions: Optional[Dict[str, LayoutPosition]] = None


# ============ 依赖注入 ============

# 服务实例缓存（key 为 (user_id, db_path)），限制大小防止无界增长
_workspace_graphrag_services: dict[tuple[str | None, str], GraphRAGService] = {}
_MAX_CACHED_SERVICES = 16


def _resolve_request_user_id(request: Request | None) -> str | None:
    if not request or not hasattr(request.state, "user"):
        return None
    user = request.state.user
    if user is None:
        return None
    if hasattr(user, "user_id"):
        return getattr(user, "user_id")
    if isinstance(user, dict):
        return str(user.get("user_id") or user.get("id") or "").strip() or None
    return None


def _resolve_db_path(
    user_id: str,
    db_path_str: str | None,
    workspace_id: str | None,
) -> Path | None:
    """把逻辑 db_path 解析为物理文件路径。支持 /workspace/ 和 /global/ 前缀。"""
    if not db_path_str:
        return None
    db_path_str = db_path_str.strip()
    if not db_path_str:
        return None

    # /workspace/xxx → 工作区根目录下的相对路径
    if db_path_str.startswith("/workspace/"):
        if not workspace_id:
            return None
        from app.services.workspace_registry import get_workspace_registry_service

        service = get_workspace_registry_service()
        workspace_root = service.get_workspace_root(user_id, workspace_id)
        rel = db_path_str[len("/workspace/") :]
        resolved = (workspace_root / rel).resolve()
        try:
            resolved.relative_to(workspace_root.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="Path traversal detected")
        return resolved

    # /global/xxx → 全局资源目录下的相对路径
    if db_path_str.startswith("/global/"):
        from app.core.config import get_user_global_resources_dir

        global_root = get_user_global_resources_dir(user_id)
        rel = db_path_str[len("/global/") :]
        resolved = (global_root / rel).resolve()
        try:
            resolved.relative_to(global_root.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="Path traversal detected")
        return resolved

    # 无前缀的绝对路径或相对路径（兜底，优先按工作区解析）
    if workspace_id:
        from app.services.workspace_registry import get_workspace_registry_service

        service = get_workspace_registry_service()
        workspace_root = service.get_workspace_root(user_id, workspace_id)
        candidate = (workspace_root / db_path_str).resolve()
        try:
            candidate.relative_to(workspace_root.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="Path traversal detected")
        if candidate.exists():
            return candidate

    return None


def get_graphrag_service(
    _: None = Depends(require_auth),
    request: Request = None,
    workspace_id: Optional[str] = Query(default=None),
    db_path: Optional[str] = Query(
        default=None,
        description="逻辑文件路径，如 /workspace/analysis-note.graph.db 或 /global/graphs/system.db",
    ),
) -> GraphRAGService:
    """
    获取 GraphRAG 服务实例

    通过 db_path 直接定位物理 SQLite 文件。未传 db_path 时默认使用全局 system.db。
    """
    if workspace_id is None and request is not None:
        raw_workspace_id = request.query_params.get("workspace_id")
        workspace_id = raw_workspace_id.strip() if raw_workspace_id else None

    # 处理 db_path：可能是 str、None 或 FastAPI Query 对象
    if isinstance(db_path, str):
        db_path = db_path.strip() or None
    else:
        db_path = None

    if db_path is None and request is not None and hasattr(request, "query_params"):
        raw_db_path = request.query_params.get("db_path")
        db_path = raw_db_path.strip() if raw_db_path else None

    user_id = _resolve_request_user_id(request)
    effective_user_id = user_id or "local_default"

    # 未传 db_path 时，默认使用全局 system.db
    if not db_path:
        db_path = "/global/graphs/system.db"

    resolved_db_path = _resolve_db_path(effective_user_id, db_path, workspace_id)
    if not resolved_db_path or not resolved_db_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"知识图谱数据库不存在: {db_path}",
        )

    cache_key = (effective_user_id, str(resolved_db_path))
    cached = _workspace_graphrag_services.get(cache_key)
    if cached is None:
        if len(_workspace_graphrag_services) >= _MAX_CACHED_SERVICES:
            oldest = next(iter(_workspace_graphrag_services))
            logger.warning(
                "GraphRAG API 服务缓存已满(%d)，淘汰最旧条目: %s",
                _MAX_CACHED_SERVICES,
                oldest,
            )
            _workspace_graphrag_services.pop(oldest, None)

        # 从文件名提取展示名（kg_id / kb_id）
        display_name = resolved_db_path.stem
        if display_name.endswith(".graph"):
            display_name = display_name[:-6]

        graph_store = SQLiteGraphStore(
            user_id=effective_user_id,
            kg_id=display_name,
            db_path=resolved_db_path,
        )
        cached = GraphRAGService(
            kb_id=display_name,
            auto_init_llm=True,
            user_id=effective_user_id,
            graph_store=graph_store,
        )
        _workspace_graphrag_services[cache_key] = cached
    else:
        # LRU：将访问条目移到末尾
        _workspace_graphrag_services.pop(cache_key, None)
        _workspace_graphrag_services[cache_key] = cached
    return cached


# ============ API 端点 ============


@router.post("/documents", response_model=AddDocumentResponse)
async def add_document(
    request: AddDocumentRequest, service: GraphRAGService = Depends(get_graphrag_service)
):
    """
    添加文档到知识图谱

    自动从 llm_config.json 读取 LLM 配置进行实体抽取。
    确保系统中已配置 LLM Provider。
    """
    try:
        result = await service.add_document(
            content=request.content,
            doc_id=request.doc_id,
            resolve_entities=request.resolve_entities,
        )
        return AddDocumentResponse(**result)
    except RuntimeError as e:
        if "LLM" in str(e) or "not configured" in str(e):
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "LLM not configured",
                    "message": str(e),
                    "hint": "Please configure LLM provider in system settings (Settings > LLM Config)",
                },
            ) from e
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}") from e


@router.post("/documents/upload", response_model=UploadDocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    doc_id: Optional[str] = Form(default=None),
    resolve_entities: bool = Form(default=True),
    extraction_mode: Optional[str] = Form(default=None),
    service: GraphRAGService = Depends(get_graphrag_service),
):
    """上传文件并构建知识图谱。"""
    try:
        content = await file.read()
        result = await service.add_document_from_file(
            filename=file.filename or "uploaded.txt",
            file_bytes=content,
            extraction_mode=extraction_mode,
            doc_id=doc_id,
            resolve_entities=resolve_entities,
        )
        return UploadDocumentResponse(**result)
    except RuntimeError as e:
        if "LLM" in str(e) or "not configured" in str(e):
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "LLM not configured",
                    "message": str(e),
                    "hint": "Please configure LLM provider in system settings (Settings > LLM Config)",
                },
            ) from e
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"File upload processing failed: {str(e)}"
        ) from e


@router.post("/query", response_model=QueryResponse)
async def query_graph(
    request: QueryRequest, service: GraphRAGService = Depends(get_graphrag_service)
):
    """查询知识图谱"""
    try:
        result = await service.query(
            question=request.question,
            top_k=request.top_k,
            depth=request.depth,
            use_communities=request.use_communities,
        )
        return QueryResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}") from e


@router.get("/entities", response_model=List[EntityResponse])
async def list_entities(
    entity_type: Optional[str] = None,
    limit: int = 100,
    service: GraphRAGService = Depends(get_graphrag_service),
):
    """获取实体列表"""
    entities = await service.get_all_entities(entity_type=entity_type, limit=limit)
    return [EntityResponse(**e) for e in entities]


@router.post("/entities", response_model=EntityResponse, status_code=201)
async def create_entity(
    request: CreateEntityRequest, service: GraphRAGService = Depends(get_graphrag_service)
):
    """手工创建实体节点"""
    try:
        result = await service.create_entity(
            name=request.name,
            entity_type=request.entity_type,
            description=request.description or "",
            properties=request.properties,
        )
        return EntityResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/relations", response_model=RelationResponse, status_code=201)
async def create_relation(
    request: CreateRelationRequest, service: GraphRAGService = Depends(get_graphrag_service)
):
    """手工创建实体关系"""
    try:
        result = await service.create_relation(
            source_entity_id=request.source_entity_id,
            target_entity_id=request.target_entity_id,
            relation_type=request.relation_type,
            description=request.description or "",
            strength=request.strength,
            properties=request.properties,
        )
        return RelationResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/entities/{name}", response_model=EntityResponse)
async def get_entity(name: str, service: GraphRAGService = Depends(get_graphrag_service)):
    """获取实体详情"""
    entity = await service.get_entity(name)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity '{name}' not found")
    return EntityResponse(**entity)


@router.put("/entities/{entity_id}", response_model=EntityResponse)
async def update_entity(
    entity_id: str,
    request: UpdateEntityRequest,
    service: GraphRAGService = Depends(get_graphrag_service),
):
    """更新实体信息"""
    result = await service.update_entity(
        entity_id=entity_id,
        name=request.name,
        entity_type=request.entity_type,
        description=request.description,
        properties=request.properties,
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
    return EntityResponse(**result)


@router.delete("/entities/{entity_id}", response_model=DeleteEntityResponse)
async def delete_entity(entity_id: str, service: GraphRAGService = Depends(get_graphrag_service)):
    """删除实体节点及其关联关系"""
    result = await service.delete_entity(entity_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
    return DeleteEntityResponse(**result)


@router.get("/search")
async def search_entities(
    query: str,
    entity_type: Optional[str] = None,
    service: GraphRAGService = Depends(get_graphrag_service),
):
    """搜索实体"""
    results = await service.search(query, entity_type)
    return {"results": results, "count": len(results)}


@router.get("/statistics", response_model=StatisticsResponse)
async def get_statistics(service: GraphRAGService = Depends(get_graphrag_service)):
    """获取图谱统计信息"""
    stats = await service.get_statistics()

    # 获取 LLM 状态
    health = await service.health_check()
    stats["llm_status"] = health.get("llm_status", "unknown")
    if "communities" in stats and isinstance(stats["communities"], dict):
        stats["communities"] = {str(level): count for level, count in stats["communities"].items()}

    return StatisticsResponse(**stats)


@router.get("/communities", response_model=List[CommunitySummary])
async def get_communities(level: int = 0, service: GraphRAGService = Depends(get_graphrag_service)):
    """获取社区列表"""
    communities = await service.get_communities(level=level)
    return [CommunitySummary(**c) for c in communities]


@router.get("/visualization", response_model=VisualizationResponse)
async def get_visualization(
    limit: int = 180,
    community_level: int = 0,
    include_communities: bool = False,
    service: GraphRAGService = Depends(get_graphrag_service),
):
    """获取前端知识图谱可视化所需的节点和边。"""
    try:
        result = await service.get_visualization(
            limit=limit,
            community_level=community_level,
            include_communities=include_communities,
        )
        return VisualizationResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Visualization graph export failed: {str(e)}",
        ) from e


@router.post("/communities/reports")
async def generate_community_reports(
    level: int = 0, service: GraphRAGService = Depends(get_graphrag_service)
):
    """
    生成社区报告（需要 LLM）
    """
    try:
        # 确保 LLM 已初始化
        await service._init_llm()
        if not service.community_reporter:
            raise HTTPException(
                status_code=503,
                detail="LLM not configured. Please configure LLM provider in system settings.",
            )

        reports = await service.build_community_reports(level=level)
        return {"level": level, "reports_count": len(reports), "reports": reports}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}") from e


@router.get("/config/llm/status")
async def get_llm_status(service: GraphRAGService = Depends(get_graphrag_service)):
    """获取 LLM 配置状态"""
    await service._init_llm()

    health = await service.health_check()

    return {
        "status": health["llm_status"],
        "initialized": service._llm_initialized,
        "extractor_available": service.extractor is not None,
        "resolver_available": service.resolver is not None,
        "reporter_available": service.community_reporter is not None,
        "config_source": "llm_config.json",  # 说明使用系统配置
    }


@router.post("/layout")
async def save_layout(
    request: SaveLayoutRequest,
    service: GraphRAGService = Depends(get_graphrag_service),
):
    """保存前端图谱布局位置，下次打开直接复用。"""
    try:
        positions = {k: {"x": v.x, "y": v.y} for k, v in request.positions.items()}
        await service.save_layout_positions(positions)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Save layout failed: {str(e)}") from e


@router.get("/layout")
async def get_layout(
    service: GraphRAGService = Depends(get_graphrag_service),
):
    """获取已保存的图谱布局位置。"""
    try:
        positions = await service.get_layout_positions()
        return {"positions": positions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Get layout failed: {str(e)}") from e


@router.get("/health")
async def health_check(service: GraphRAGService = Depends(get_graphrag_service)):
    """GraphRAG 服务健康检查"""
    try:
        health = await service.health_check()
        return health
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}") from e


class RawQueryRequest(BaseModel):
    sql: str


class RawQueryResponse(BaseModel):
    columns: List[str]
    rows: List[Dict[str, Any]]
    row_count: int


class TableInfoResponse(BaseModel):
    name: str
    columns: List[Dict[str, Any]]


@router.get("/tables", response_model=List[TableInfoResponse])
async def list_graph_tables(service: GraphRAGService = Depends(get_graphrag_service)):
    """获取知识图谱底层 SQLite 数据库的表列表和列信息"""
    try:
        tables = await service.graph_store.list_tables()
        return [TableInfoResponse(**t) for t in tables]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取表列表失败: {str(e)}") from e


@router.post("/raw-query", response_model=RawQueryResponse)
async def execute_graph_raw_query(
    request: RawQueryRequest, service: GraphRAGService = Depends(get_graphrag_service)
):
    """对知识图谱底层 SQLite 数据库执行原始 SELECT 查询"""
    try:
        result = await service.graph_store.execute_raw_sql(request.sql)
        return RawQueryResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}") from e
