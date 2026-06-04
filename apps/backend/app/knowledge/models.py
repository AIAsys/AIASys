"""
知识库数据模型 (Pydantic)

元数据与向量均存储在自包含的 SQLite（每个知识库独立的 {kb_id}.db），
不再通过 app.core.database 维护。
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ==================== Pydantic Models (API) ====================


class FileType(str, Enum):
    """支持的文件类型"""

    DOC = "doc"
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MD = "md"
    MARKDOWN = "markdown"
    XLSX = "xlsx"
    XLSM = "xlsm"


class DocumentStatus(str, Enum):
    """文档处理状态"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ----- Knowledge Base -----


class KnowledgeBaseKind(str, Enum):
    """知识库类型"""

    DOCUMENT = "document"
    STRUCTURED = "structured"
    WEB = "web"
    CODE = "code"


class SearchMode(str, Enum):
    """检索模式"""

    VECTOR = "vector"  # 仅向量检索
    FULLTEXT = "fulltext"  # 仅全文检索
    HYBRID = "hybrid"  # 向量 + 全文混合


class KnowledgeBaseInitStatus(str, Enum):
    """知识库初始化状态"""

    DRAFT = "draft"
    READY = "ready"
    INDEXING = "indexing"
    NEEDS_REINDEX = "needs_reindex"
    ERROR = "error"


class KnowledgeBaseCreate(BaseModel):
    """创建知识库请求"""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    kind: KnowledgeBaseKind = KnowledgeBaseKind.DOCUMENT
    embedding_model: Optional[str] = None
    chunk_size: Optional[int] = Field(512, ge=64, le=8192)
    chunk_overlap: Optional[int] = Field(50, ge=0, le=4096)
    default_search_mode: SearchMode = SearchMode.FULLTEXT
    default_extraction_mode: Optional[str] = None
    extraction_mode_mapping: Optional[Dict[str, str]] = None

    @model_validator(mode="after")
    def validate_chunk_overlap(self) -> "KnowledgeBaseCreate":
        if self.chunk_size is not None and self.chunk_overlap is not None:
            if self.chunk_overlap >= self.chunk_size:
                raise ValueError("chunk_overlap 必须小于 chunk_size")
        return self


class KnowledgeBaseUpdate(BaseModel):
    """更新知识库请求"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    embedding_model: Optional[str] = None
    chunk_size: Optional[int] = Field(None, ge=64, le=8192)
    chunk_overlap: Optional[int] = Field(None, ge=0, le=4096)
    default_search_mode: Optional[SearchMode] = None
    default_extraction_mode: Optional[str] = None
    extraction_mode_mapping: Optional[Dict[str, str]] = None

    @model_validator(mode="after")
    def validate_chunk_overlap(self) -> "KnowledgeBaseUpdate":
        if self.chunk_size is not None and self.chunk_overlap is not None:
            if self.chunk_overlap >= self.chunk_size:
                raise ValueError("chunk_overlap 必须小于 chunk_size")
        return self


class KnowledgeBaseResponse(BaseModel):
    """知识库响应"""

    id: str
    name: str
    description: Optional[str]
    user_id: str
    kind: str
    embedding_model: Optional[str]
    chunk_size: int
    chunk_overlap: int
    default_search_mode: str = SearchMode.FULLTEXT.value
    default_extraction_mode: Optional[str] = None
    extraction_mode_mapping: Optional[Dict[str, str]] = None
    document_count: int = 0
    init_status: str = KnowledgeBaseInitStatus.READY.value
    config_complete: bool = True
    config_issue: Optional[str] = None
    config_version: int = 1
    last_indexed_config_version: int = 0
    can_edit_index_config: bool = True
    requires_reindex: bool = False
    scope: str = "workspace"
    workspace_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ----- Document -----


class DocumentResponse(BaseModel):
    """文档响应"""

    id: str
    knowledge_base_id: str
    filename: str
    file_type: str
    file_size: int
    status: str
    chunk_count: int
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentChunkResponse(BaseModel):
    """文档分块响应"""

    id: str
    document_id: str
    chunk_index: int
    content: str
    meta_info: Dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ----- Query -----


class QueryRequest(BaseModel):
    """查询请求"""

    query: str = Field(..., min_length=1, max_length=2000)
    top_k: Optional[int] = Field(5, ge=1, le=20)
    filter: Optional[Dict[str, Any]] = None  # 元数据过滤
    search_mode: Optional[SearchMode] = None  # 为空时使用知识库默认检索模式


class QueryResult(BaseModel):
    """查询结果"""

    content: str
    score: float
    document_id: str
    document_name: str
    chunk_index: int
    metadata: Dict[str, Any]


class QueryResponse(BaseModel):
    """查询响应"""

    query: str
    knowledge_base_id: str
    results: List[QueryResult]
    total: int


# ----- File Upload -----


class FileUploadResponse(BaseModel):
    """文件上传响应"""

    success: bool
    document_id: Optional[str] = None
    filename: str
    message: str
    chunk_count: Optional[int] = None
    extraction_mode: Optional[str] = None
    requested_extraction_mode: Optional[str] = None
    search_mode: Optional[str] = None
    embedding_model: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None


class BatchFileUploadResponse(BaseModel):
    """批量上传响应"""

    success: bool
    batch_id: str
    knowledge_base_id: str
    total: int
    successful_count: int
    failed_count: int
    results: List[FileUploadResponse]
    message: str
    extraction_mode: Optional[str] = None
    search_mode: Optional[str] = None
    embedding_model: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
