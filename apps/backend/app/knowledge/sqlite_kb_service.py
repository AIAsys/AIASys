"""
SQLite + sqlite-vec 知识库服务

每个知识库对应一个 SQLite 数据库文件，使用 sqlite-vec 的 vec0 虚拟表存储向量。
元数据层继续使用 SQLAlchemy + SQLite（app/core/database.py）。
"""

import json
import logging
import re
import sqlite3
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

import jieba
from sqlalchemy.orm import Session

from app.core.database import Document as DocumentORM
from app.core.database import DocumentChunk as DocumentChunkORM
from app.core.database import KnowledgeBase as KnowledgeBaseORM
from app.core.database import (
    db_session,
)
from app.core.sqlite_vec import ensure_vec_extension
from app.core.time import utc_now_naive
from app.document_extraction import get_document_extraction_service
from app.knowledge.models import DocumentStatus
from app.services.llm import get_llm_config_service

from .embedder import BaseEmbedder, OpenAIEmbedder
from .models import (
    BatchFileUploadResponse,
    DocumentResponse,
    FileUploadResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseInitStatus,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    QueryRequest,
    QueryResponse,
    QueryResult,
    SearchMode,
)
from .parser import TextChunker

logger = logging.getLogger(__name__)

# 合法的 SQL 表名/列名：字母或下划线开头，后跟字母数字下划线
_VALID_SQL_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

MIN_CHUNK_SIZE = 64
MAX_CHUNK_SIZE = 8192
MIN_CHUNK_OVERLAP = 0
MAX_CHUNK_OVERLAP = 4096
DEFAULT_CONFIG_VERSION = 1


class SQLiteKBService:
    """SQLite + sqlite-vec 知识库服务。"""

    _EMBEDDER_CACHE_MAX_SIZE = 50

    def __init__(self):
        self._embedder_cache: OrderedDict[str, BaseEmbedder] = OrderedDict()

    # ==================== Embedder ====================

    def _get_embedder(self, user_id: str, embedding_model: str) -> BaseEmbedder:
        cache_key = f"{user_id}:{embedding_model}"
        cached = self._embedder_cache.get(cache_key)
        if cached is not None:
            self._embedder_cache.move_to_end(cache_key)
            return cached
        resolved = get_llm_config_service().resolve_embedding_model_config(user_id, embedding_model)
        if resolved:
            embedder = OpenAIEmbedder(
                api_key=str(resolved.get("api_key") or ""),
                base_url=str(resolved.get("base_url") or ""),
                model=str(resolved.get("model_name") or embedding_model),
                dimension=resolved.get("dimension"),
            )
        else:
            raise ValueError(
                f"未找到 embedding 模型配置: {embedding_model}。"
                "请在 LLM 设置中配置 embedding 模型，或在 config.json 中设置 embedding 段作为系统默认。"
            )
        self._embedder_cache[cache_key] = embedder
        if len(self._embedder_cache) > self._EMBEDDER_CACHE_MAX_SIZE:
            self._embedder_cache.popitem(last=False)
        return embedder

    @staticmethod
    def _get_embedding_dimension(user_id: str, embedding_model: str) -> int:
        resolved = get_llm_config_service().resolve_embedding_model_config(user_id, embedding_model)
        if resolved and resolved.get("dimension"):
            return int(resolved["dimension"])
        if not resolved:
            raise ValueError(
                f"未找到 embedding 模型配置: {embedding_model}。"
                "请在 LLM 设置中配置 embedding 模型，或在 config.json 中设置 embedding 段作为系统默认。"
            )
        # resolved 存在但没有 dimension 字段，根据模型名推断
        model_name = str(resolved.get("model_name") or embedding_model).lower()
        if "bge-m3" in model_name:
            return 1024
        if "text-embedding-3-small" in model_name or "text-embedding-v4" in model_name:
            return 1536
        if "text-embedding-3-large" in model_name:
            return 3072
        return 1536

    # ==================== 数据库路径 ====================

    @staticmethod
    def _db_path(workspace_root: Path, kb_id: str) -> Path:
        kb_dir = workspace_root / ".aiasys" / "knowledge"
        kb_dir.mkdir(parents=True, exist_ok=True)
        return kb_dir / f"{kb_id}.db"

    @staticmethod
    def _legacy_db_path(user_id: str, kb_id: str) -> Path:
        """旧版全局资源路径，用于兼容旧数据。"""
        from app.core.config import get_user_global_resources_dir
        return get_user_global_resources_dir(user_id) / "knowledge" / f"{kb_id}.db"

    @staticmethod
    def _find_db_path(workspace_root: Path, user_id: str, kb_id: str) -> Path | None:
        """按优先级查找 .db 文件：新路径 > 旧全局路径。"""
        new_path = SQLiteKBService._db_path(workspace_root, kb_id)
        if new_path.exists():
            return new_path
        legacy = SQLiteKBService._legacy_db_path(user_id, kb_id)
        if legacy.exists():
            return legacy
        return None

    def _resolve_workspace_root_for_kb(self, user_id: str, kb_id: str) -> Path:
        """根据 ORM 记录中的 scope/workspace_id 解析 .db 文件所在工作区根目录。

        优先级：
        1. 从 ORM 查 scope 和 workspace_id，计算新路径
        2. 如果新路径不存在，fallback 到旧全局路径（兼容旧数据）
        3. 如果 ORM 没有 scope 字段（旧记录），fallback 到旧全局路径
        """
        from app.core.config import WORKSPACE_DIR, get_user_global_workspace_dir
        from app.core.database import db_session as _db_session

        with _db_session() as db:
            kb = db.query(KnowledgeBaseORM).filter(
                KnowledgeBaseORM.id == kb_id,
                KnowledgeBaseORM.user_id == user_id,
            ).first()

        if kb is not None:
            scope = getattr(kb, "scope", None)
            if scope == "workspace":
                ws_id = getattr(kb, "workspace_id", None)
                if ws_id:
                    ws_root = WORKSPACE_DIR / user_id / ws_id
                    return ws_root
            elif scope == "global":
                return get_user_global_workspace_dir(user_id)

        # Fallback: 旧全局路径
        legacy = self._legacy_db_path(user_id, kb_id)
        if legacy.exists():
            return get_user_global_workspace_dir(user_id)

        # 最后 fallback 到全局工作区（旧记录没有 scope 字段时）
        return get_user_global_workspace_dir(user_id)

    def _get_conn(self, user_id: str, kb_id: str) -> sqlite3.Connection:
        workspace_root = self._resolve_workspace_root_for_kb(user_id, kb_id)
        db_path = self._db_path(workspace_root, kb_id)
        if not db_path.exists():
            legacy = self._legacy_db_path(user_id, kb_id)
            if legacy.exists():
                db_path = legacy
        return ensure_vec_extension(db_path)

    # ==================== 知识库管理 ====================

    def create_knowledge_base(
        self,
        user_id: str,
        data: KnowledgeBaseCreate,
        *,
        workspace_root: Path | None = None,
        scope: str = "workspace",
        workspace_id: str | None = None,
    ) -> KnowledgeBaseResponse:
        with db_session() as db:
            kb_id = str(uuid.uuid4())
            chunk_size = data.chunk_size or 512
            chunk_overlap = data.chunk_overlap or 50
            chunk_error = self._validate_chunk_config(chunk_size, chunk_overlap)
            if chunk_error:
                raise ValueError(chunk_error)
            # 尝试获取默认 embedding 模型，没有也不报错
            try:
                embedding_model = (
                    data.embedding_model
                    or get_llm_config_service().resolve_default_embedding_model_id(user_id)
                )
            except ValueError:
                embedding_model = None

            # 解析 workspace_root：未传时 fallback 到旧全局路径（API 直接调用场景）
            if workspace_root is None:
                from app.core.config import get_user_global_workspace_dir
                workspace_root = get_user_global_workspace_dir(user_id)
                scope = "global"

            kb = KnowledgeBaseORM(
                id=kb_id,
                name=data.name,
                description=data.description,
                user_id=user_id,
                kind=data.kind.value if data.kind else "document",
                embedding_model=embedding_model,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                default_search_mode=data.default_search_mode.value,
                default_extraction_mode=data.default_extraction_mode,
                extraction_mode_mapping=data.extraction_mode_mapping,
                scope=scope,
                workspace_id=workspace_id if scope == "workspace" else None,
            )
            db.add(kb)
            db.commit()
            db.refresh(kb)

            self._ensure_kb_schema(user_id, kb_id, embedding_model)
            self._sync_kb_runtime_metadata(user_id, kb)

            return self._kb_to_response(kb, db)

    @staticmethod
    def _tokenize_for_fts(text: str) -> str:
        """用 jieba 分词后空格拼接，供 FTS5 索引/查询使用。"""
        return " ".join(jieba.cut(text.strip()))

    @staticmethod
    def _is_fts_search_term(term: str) -> bool:
        return any(char.isalnum() or char == "_" for char in term)

    @staticmethod
    def _quote_fts_phrase(term: str) -> str:
        escaped = term.replace('"', '""')
        return f'"{escaped}"'

    @classmethod
    def _build_fts_match_query(cls, query: str) -> str:
        terms = [
            term
            for term in (part.strip() for part in jieba.cut(query.strip()))
            if term and cls._is_fts_search_term(term)
        ]
        return " AND ".join(cls._quote_fts_phrase(term) for term in terms)

    def _ensure_kb_schema(self, user_id: str, kb_id: str, embedding_model: Optional[str]) -> None:
        conn = self._get_conn(user_id, kb_id)
        try:
            self._ensure_metadata_table(conn)
            # vec0 向量表（embedding 可用时才创建）
            if embedding_model:
                try:
                    dim = self._get_embedding_dimension(user_id, embedding_model)
                    conn.execute(f"""
                        CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING vec0(
                            chunk_id TEXT,
                            document_id TEXT,
                            chunk_index INTEGER,
                            meta_json TEXT,
                            embedding float[{dim}]
                        )
                    """)
                except ValueError as exc:
                    logger.warning(
                        "知识库 %s embedding 模型不可用，跳过向量表创建: %s",
                        kb_id,
                        exc,
                    )
            # FTS5 全文表（始终创建，作为保底检索能力）
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    document_id UNINDEXED,
                    content
                )
            """)
        finally:
            conn.close()

    @staticmethod
    def _ensure_metadata_table(conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kb_metadata(
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT NOT NULL
            )
        """)

    @staticmethod
    def _serialize_metadata_value(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _metadata_from_kb(
        kb: KnowledgeBaseORM,
        *,
        init_status: KnowledgeBaseInitStatus | str | None = None,
        config_version: int = DEFAULT_CONFIG_VERSION,
        last_indexed_config_version: int = 0,
        config_issue: str | None = None,
    ) -> dict[str, Any]:
        resolved_status = (
            init_status.value if isinstance(init_status, KnowledgeBaseInitStatus) else init_status
        )
        if resolved_status is None:
            resolved_status, config_issue = SQLiteKBService._derive_init_state(kb)
        config_complete = resolved_status == KnowledgeBaseInitStatus.READY.value
        return {
            "schema_version": "1",
            "knowledge_base_id": kb.id,
            "kind": kb.kind or "document",
            "embedding_model": kb.embedding_model,
            "chunk_size": kb.chunk_size,
            "chunk_overlap": kb.chunk_overlap,
            "default_search_mode": kb.default_search_mode or SearchMode.FULLTEXT.value,
            "init_status": resolved_status,
            "config_complete": "true" if config_complete else "false",
            "config_issue": config_issue or "",
            "config_version": config_version,
            "last_indexed_config_version": last_indexed_config_version,
            "requires_reindex": (
                "true"
                if resolved_status == KnowledgeBaseInitStatus.NEEDS_REINDEX.value
                else "false"
            ),
        }

    def _sync_kb_metadata(self, user_id: str, kb_id: str, metadata: dict[str, Any]) -> None:
        conn = self._get_conn(user_id, kb_id)
        try:
            self._ensure_metadata_table(conn)
            updated_at = utc_now_naive().isoformat()
            for key, value in metadata.items():
                conn.execute(
                    """
                    INSERT INTO kb_metadata(key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (key, self._serialize_metadata_value(value), updated_at),
                )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _validate_chunk_config(chunk_size: int, chunk_overlap: int) -> Optional[str]:
        if chunk_size < MIN_CHUNK_SIZE or chunk_size > MAX_CHUNK_SIZE:
            return f"chunk_size 必须在 {MIN_CHUNK_SIZE}-{MAX_CHUNK_SIZE} 之间"
        if chunk_overlap < MIN_CHUNK_OVERLAP or chunk_overlap > MAX_CHUNK_OVERLAP:
            return f"chunk_overlap 必须在 {MIN_CHUNK_OVERLAP}-{MAX_CHUNK_OVERLAP} 之间"
        if chunk_overlap >= chunk_size:
            return "chunk_overlap 必须小于 chunk_size"
        return None

    @staticmethod
    def _derive_init_state(kb: KnowledgeBaseORM) -> tuple[str, str | None]:
        if not kb.embedding_model:
            return (
                KnowledgeBaseInitStatus.DRAFT.value,
                "需要先配置 embedding 模型",
            )
        return KnowledgeBaseInitStatus.READY.value, None

    @staticmethod
    def _parse_int_metadata(value: str | None, fallback: int) -> int:
        if value is None or value == "":
            return fallback
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _parse_bool_metadata(value: str | None, fallback: bool = False) -> bool:
        if value is None or value == "":
            return fallback
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def _read_kb_metadata(self, user_id: str, kb_id: str) -> dict[str, str]:
        workspace_root = self._resolve_workspace_root_for_kb(user_id, kb_id)
        db_path = self._db_path(workspace_root, kb_id)
        if not db_path.exists():
            legacy = self._legacy_db_path(user_id, kb_id)
            if not legacy.exists():
                return {}
        conn = self._get_conn(user_id, kb_id)
        try:
            self._ensure_metadata_table(conn)
            rows = conn.execute("SELECT key, value FROM kb_metadata").fetchall()
            return {str(key): "" if value is None else str(value) for key, value in rows}
        finally:
            conn.close()

    def _get_config_version(self, user_id: str, kb_id: str) -> int:
        metadata = self._read_kb_metadata(user_id, kb_id)
        return self._parse_int_metadata(metadata.get("config_version"), DEFAULT_CONFIG_VERSION)

    def _next_config_version(self, user_id: str, kb_id: str) -> int:
        return self._get_config_version(user_id, kb_id) + 1

    def _sync_kb_runtime_metadata(
        self,
        user_id: str,
        kb: KnowledgeBaseORM,
        *,
        config_version: int | None = None,
        last_indexed_config_version: int | None = None,
        init_status: KnowledgeBaseInitStatus | str | None = None,
        config_issue: str | None = None,
    ) -> dict[str, Any]:
        existing = self._read_kb_metadata(user_id, kb.id)
        resolved_config_version = (
            config_version
            if config_version is not None
            else self._parse_int_metadata(existing.get("config_version"), DEFAULT_CONFIG_VERSION)
        )
        resolved_last_indexed = (
            last_indexed_config_version
            if last_indexed_config_version is not None
            else self._parse_int_metadata(existing.get("last_indexed_config_version"), 0)
        )
        metadata = self._metadata_from_kb(
            kb,
            init_status=init_status,
            config_version=resolved_config_version,
            last_indexed_config_version=resolved_last_indexed,
            config_issue=config_issue,
        )
        self._sync_kb_metadata(user_id, kb.id, metadata)
        return metadata

    def _assert_kb_ready(self, user_id: str, kb: KnowledgeBaseORM) -> None:
        metadata = self._read_kb_metadata(user_id, kb.id)
        derived_status, derived_issue = self._derive_init_state(kb)
        status = metadata.get("init_status") or derived_status
        issue = metadata.get("config_issue") or derived_issue
        config_complete = self._parse_bool_metadata(
            metadata.get("config_complete"),
            status == KnowledgeBaseInitStatus.READY.value,
        )
        if not config_complete or status == KnowledgeBaseInitStatus.DRAFT.value:
            raise ValueError(issue or "知识库需要先完成模型配置")
        if status == KnowledgeBaseInitStatus.NEEDS_REINDEX.value:
            raise ValueError("知识库配置已变更，需要重建索引后再使用")
        if status == KnowledgeBaseInitStatus.ERROR.value:
            raise ValueError(issue or "知识库状态异常")

    def list_knowledge_bases(
        self, user_id: str, skip: int = 0, limit: int = 100
    ) -> List[KnowledgeBaseResponse]:
        with db_session() as db:
            kbs = (
                db.query(KnowledgeBaseORM)
                .filter(KnowledgeBaseORM.user_id == user_id)
                .offset(skip)
                .limit(limit)
                .all()
            )
            return [self._kb_to_response(kb, db) for kb in kbs]

    def get_knowledge_base(self, user_id: str, kb_id: str) -> Optional[KnowledgeBaseResponse]:
        with db_session() as db:
            kb = (
                db.query(KnowledgeBaseORM)
                .filter(KnowledgeBaseORM.id == kb_id, KnowledgeBaseORM.user_id == user_id)
                .first()
            )
            return self._kb_to_response(kb, db) if kb else None

    def update_knowledge_base(
        self, user_id: str, kb_id: str, data: KnowledgeBaseUpdate
    ) -> Optional[KnowledgeBaseResponse]:
        with db_session() as db:
            kb = (
                db.query(KnowledgeBaseORM)
                .filter(KnowledgeBaseORM.id == kb_id, KnowledgeBaseORM.user_id == user_id)
                .first()
            )
            if not kb:
                return None
            document_count = (
                db.query(DocumentORM).filter(DocumentORM.knowledge_base_id == kb_id).count()
            )
            index_config_changed = False
            runtime_config_changed = False
            if data.name is not None:
                kb.name = data.name
            if data.description is not None:
                kb.description = data.description
            if data.embedding_model is not None:
                next_embedding_model = data.embedding_model.strip() or None
                if document_count > 0 and next_embedding_model != kb.embedding_model:
                    raise ValueError("已有文档的知识库不能直接切换 embedding 模型，请先重建索引")
                if next_embedding_model != kb.embedding_model:
                    kb.embedding_model = next_embedding_model
                    self._ensure_kb_schema(user_id, kb_id, kb.embedding_model)
                    index_config_changed = True
            next_chunk_size = data.chunk_size if data.chunk_size is not None else kb.chunk_size
            next_chunk_overlap = (
                data.chunk_overlap if data.chunk_overlap is not None else kb.chunk_overlap
            )
            chunk_error = self._validate_chunk_config(next_chunk_size, next_chunk_overlap)
            if chunk_error:
                raise ValueError(chunk_error)
            if document_count > 0 and (
                (data.chunk_size is not None and data.chunk_size != kb.chunk_size)
                or (data.chunk_overlap is not None and data.chunk_overlap != kb.chunk_overlap)
            ):
                raise ValueError("已有文档的知识库不能直接修改分块配置，请先重建索引")
            if data.chunk_size is not None:
                if data.chunk_size != kb.chunk_size:
                    kb.chunk_size = data.chunk_size
                    index_config_changed = True
            if data.chunk_overlap is not None:
                if data.chunk_overlap != kb.chunk_overlap:
                    kb.chunk_overlap = data.chunk_overlap
                    index_config_changed = True
            if data.default_search_mode is not None:
                if data.default_search_mode.value != kb.default_search_mode:
                    kb.default_search_mode = data.default_search_mode.value
                    runtime_config_changed = True
            if data.default_extraction_mode is not None:
                next_extraction = data.default_extraction_mode.strip() or None
                if next_extraction != kb.default_extraction_mode:
                    kb.default_extraction_mode = next_extraction
                    runtime_config_changed = True
            if data.extraction_mode_mapping is not None:
                kb.extraction_mode_mapping = data.extraction_mode_mapping
                runtime_config_changed = True
            kb.updated_at = utc_now_naive()
            db.commit()
            db.refresh(kb)
            config_changed = index_config_changed or runtime_config_changed
            next_config_version = (
                self._next_config_version(user_id, kb_id)
                if config_changed
                else self._get_config_version(user_id, kb_id)
            )
            last_indexed = None
            if runtime_config_changed and not index_config_changed and document_count > 0:
                last_indexed = next_config_version
            self._sync_kb_runtime_metadata(
                user_id,
                kb,
                config_version=next_config_version,
                last_indexed_config_version=last_indexed,
            )
            return self._kb_to_response(kb, db)

    def delete_knowledge_base(self, user_id: str, kb_id: str) -> bool:
        with db_session() as db:
            kb = (
                db.query(KnowledgeBaseORM)
                .filter(KnowledgeBaseORM.id == kb_id, KnowledgeBaseORM.user_id == user_id)
                .first()
            )
            if not kb:
                return False

            workspace_root = self._resolve_workspace_root_for_kb(user_id, kb_id)
            db_path = self._db_path(workspace_root, kb_id)
            if not db_path.exists():
                legacy = self._legacy_db_path(user_id, kb_id)
                if legacy.exists():
                    db_path = legacy
            if db_path.exists():
                try:
                    db_path.unlink()
                except Exception as e:
                    logger.warning(f"删除知识库 SQLite 文件失败: {e}")

            db.delete(kb)
            db.commit()
            return True

    # ==================== 文档管理 ====================

    async def upload_document(
        self,
        user_id: str,
        kb_id: str,
        filename: str,
        file_bytes: bytes,
        extraction_mode: Optional[str] = None,
        embedding_model: Optional[str] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        search_mode: Optional[SearchMode | str] = None,
    ) -> FileUploadResponse:
        with db_session() as db:
            kb = (
                db.query(KnowledgeBaseORM)
                .filter(KnowledgeBaseORM.id == kb_id, KnowledgeBaseORM.user_id == user_id)
                .first()
            )
            if not kb:
                return FileUploadResponse(
                    success=False,
                    filename=filename,
                    message="知识库不存在",
                    extraction_mode=extraction_mode,
                )
            try:
                self._assert_kb_ready(user_id, kb)
            except ValueError as exc:
                return FileUploadResponse(
                    success=False,
                    filename=filename,
                    message=str(exc),
                    extraction_mode=extraction_mode,
                )

            if extraction_mode is None and kb.default_extraction_mode:
                extraction_mode = kb.default_extraction_mode

            document_count = (
                db.query(DocumentORM).filter(DocumentORM.knowledge_base_id == kb_id).count()
            )
            index_config_changed = False
            runtime_config_changed = False
            next_chunk_size = chunk_size if chunk_size is not None else kb.chunk_size
            next_chunk_overlap = chunk_overlap if chunk_overlap is not None else kb.chunk_overlap
            chunk_error = self._validate_chunk_config(next_chunk_size, next_chunk_overlap)
            if chunk_error:
                return FileUploadResponse(
                    success=False,
                    filename=filename,
                    message=chunk_error,
                    extraction_mode=extraction_mode,
                    requested_extraction_mode=extraction_mode,
                    search_mode=kb.default_search_mode,
                    embedding_model=kb.embedding_model,
                    chunk_size=kb.chunk_size,
                    chunk_overlap=kb.chunk_overlap,
                )
            if document_count > 0 and (
                (chunk_size is not None and chunk_size != kb.chunk_size)
                or (chunk_overlap is not None and chunk_overlap != kb.chunk_overlap)
            ):
                return FileUploadResponse(
                    success=False,
                    filename=filename,
                    message="已有文档的知识库不能在导入时修改分块配置，请先重建索引",
                    extraction_mode=extraction_mode,
                    requested_extraction_mode=extraction_mode,
                    search_mode=kb.default_search_mode,
                    embedding_model=kb.embedding_model,
                    chunk_size=kb.chunk_size,
                    chunk_overlap=kb.chunk_overlap,
                )

            if embedding_model is not None:
                next_embedding_model = embedding_model.strip() or None
                if document_count > 0 and next_embedding_model != kb.embedding_model:
                    return FileUploadResponse(
                        success=False,
                        filename=filename,
                        message="已有文档的知识库不能在导入时切换 embedding 模型，请先重建索引",
                        extraction_mode=extraction_mode,
                        requested_extraction_mode=extraction_mode,
                        search_mode=kb.default_search_mode,
                        embedding_model=kb.embedding_model,
                        chunk_size=kb.chunk_size,
                        chunk_overlap=kb.chunk_overlap,
                    )
                if next_embedding_model != kb.embedding_model:
                    kb.embedding_model = next_embedding_model
                    self._ensure_kb_schema(user_id, kb_id, kb.embedding_model)
                    index_config_changed = True

            if chunk_size is not None:
                if chunk_size != kb.chunk_size:
                    kb.chunk_size = chunk_size
                    index_config_changed = True
            if chunk_overlap is not None:
                if chunk_overlap != kb.chunk_overlap:
                    kb.chunk_overlap = chunk_overlap
                    index_config_changed = True
            if search_mode is not None:
                resolved_search_mode = (
                    search_mode.value if isinstance(search_mode, SearchMode) else str(search_mode)
                )
                try:
                    next_search_mode = SearchMode(resolved_search_mode).value
                    if next_search_mode != kb.default_search_mode:
                        kb.default_search_mode = next_search_mode
                        runtime_config_changed = True
                except ValueError:
                    db.rollback()
                    return FileUploadResponse(
                        success=False,
                        filename=filename,
                        message=f"不支持的检索策略: {resolved_search_mode}",
                        extraction_mode=extraction_mode,
                        requested_extraction_mode=extraction_mode,
                        search_mode=kb.default_search_mode,
                        embedding_model=kb.embedding_model,
                        chunk_size=kb.chunk_size,
                        chunk_overlap=kb.chunk_overlap,
                    )
            db.commit()
            db.refresh(kb)
            config_changed = index_config_changed or runtime_config_changed
            next_config_version = (
                self._next_config_version(user_id, kb_id)
                if config_changed
                else self._get_config_version(user_id, kb_id)
            )
            self._sync_kb_runtime_metadata(
                user_id,
                kb,
                config_version=next_config_version,
            )
            try:
                self._assert_kb_ready(user_id, kb)
            except ValueError as exc:
                return FileUploadResponse(
                    success=False,
                    filename=filename,
                    message=str(exc),
                    extraction_mode=extraction_mode,
                    requested_extraction_mode=extraction_mode,
                    search_mode=kb.default_search_mode,
                    embedding_model=kb.embedding_model,
                    chunk_size=kb.chunk_size,
                    chunk_overlap=kb.chunk_overlap,
                )

            doc_id = str(uuid.uuid4())
            suffix = Path(filename).suffix.lower()
            file_type = suffix.lstrip(".") if suffix else "txt"

            # 拒绝表格文件进知识库
            if suffix in {".xlsx", ".xlsm"}:
                return FileUploadResponse(
                    success=False,
                    filename=filename,
                    message="表格文件建议放到工作区处理，知识库对表格数据的检索效果有限",
                    extraction_mode=extraction_mode,
                    requested_extraction_mode=extraction_mode,
                    search_mode=kb.default_search_mode,
                    embedding_model=kb.embedding_model,
                    chunk_size=kb.chunk_size,
                    chunk_overlap=kb.chunk_overlap,
                )

            # 按文件类型映射表选择解析引擎
            if extraction_mode is None and kb.extraction_mode_mapping:
                mapped_mode = kb.extraction_mode_mapping.get(suffix)
                if mapped_mode:
                    extraction_mode = mapped_mode

            doc = DocumentORM(
                id=doc_id,
                knowledge_base_id=kb_id,
                filename=filename,
                file_type=file_type,
                file_size=len(file_bytes),
                status=DocumentStatus.PROCESSING.value,
            )
            db.add(doc)
            db.commit()

            try:
                extraction = get_document_extraction_service().extract(
                    Path(filename), file_bytes, mode=extraction_mode
                )
                content = extraction.text
                if not content.strip():
                    raise ValueError("文档内容为空")

                chunker = TextChunker(chunk_size=kb.chunk_size, chunk_overlap=kb.chunk_overlap)
                chunks = chunker.split_with_metadata(
                    content, doc_metadata={"doc_id": doc_id, "filename": filename}
                )

                chunk_ids = [str(uuid.uuid4()) for _ in chunks]

                # embedding 可用时生成向量，否则仅做全文索引
                embeddings: Optional[List[List[float]]] = None
                if kb.embedding_model:
                    try:
                        embedder = self._get_embedder(user_id, kb.embedding_model)
                        texts = [c["content"] for c in chunks]
                        embeddings = await embedder.embed(texts)
                    except ValueError as exc:
                        logger.warning(
                            "知识库 %s embedding 模型不可用，文档仅以全文索引存储: %s",
                            kb_id,
                            exc,
                        )

                self._insert_chunks(user_id, kb_id, doc_id, chunk_ids, chunks, embeddings)

                chunk_records = []
                for i, chunk in enumerate(chunks):
                    chunk_records.append(
                        DocumentChunkORM(
                            id=str(uuid.uuid4()),
                            document_id=doc_id,
                            chunk_index=chunk["index"],
                            content=chunk["content"],
                            meta_info=chunk["metadata"],
                            chunk_id=chunk_ids[i],
                        )
                    )
                db.add_all(chunk_records)

                doc.status = DocumentStatus.COMPLETED.value
                doc.chunk_count = len(chunks)
                db.commit()
                self._sync_kb_runtime_metadata(
                    user_id,
                    kb,
                    config_version=next_config_version,
                    last_indexed_config_version=next_config_version,
                    init_status=KnowledgeBaseInitStatus.READY,
                )

                return FileUploadResponse(
                    success=True,
                    document_id=doc_id,
                    filename=filename,
                    message="上传成功",
                    chunk_count=len(chunks),
                    extraction_mode=extraction.mode_used.value,
                    requested_extraction_mode=extraction.requested_mode.value,
                    search_mode=kb.default_search_mode,
                    embedding_model=kb.embedding_model,
                    chunk_size=kb.chunk_size,
                    chunk_overlap=kb.chunk_overlap,
                )
            except Exception as e:
                logger.error(f"文档处理失败: {e}")
                doc.status = DocumentStatus.FAILED.value
                doc.error_message = str(e)
                db.commit()
                return FileUploadResponse(
                    success=False,
                    document_id=doc_id,
                    filename=filename,
                    message=f"处理失败: {e}",
                    extraction_mode=extraction_mode,
                    requested_extraction_mode=extraction_mode,
                    search_mode=kb.default_search_mode,
                    embedding_model=kb.embedding_model,
                    chunk_size=kb.chunk_size,
                    chunk_overlap=kb.chunk_overlap,
                )

    async def upload_documents(
        self,
        user_id: str,
        kb_id: str,
        files: list[tuple[str, bytes]],
        extraction_mode: Optional[str] = None,
        embedding_model: Optional[str] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        search_mode: Optional[SearchMode | str] = None,
    ) -> BatchFileUploadResponse:
        batch_id = str(uuid.uuid4())
        results: list[FileUploadResponse] = []
        for filename, file_bytes in files:
            result = await self.upload_document(
                user_id=user_id,
                kb_id=kb_id,
                filename=filename,
                file_bytes=file_bytes,
                extraction_mode=extraction_mode,
                embedding_model=embedding_model,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                search_mode=search_mode,
            )
            results.append(result)

        successful_count = sum(1 for item in results if item.success)
        failed_count = len(results) - successful_count
        return BatchFileUploadResponse(
            success=failed_count == 0,
            batch_id=batch_id,
            knowledge_base_id=kb_id,
            total=len(results),
            successful_count=successful_count,
            failed_count=failed_count,
            results=results,
            message=(
                f"成功导入 {successful_count} 个文件"
                if failed_count == 0
                else f"成功导入 {successful_count} 个文件，失败 {failed_count} 个文件"
            ),
            extraction_mode=extraction_mode,
            search_mode=(
                search_mode.value
                if isinstance(search_mode, SearchMode)
                else str(search_mode) if search_mode is not None else None
            ),
            embedding_model=embedding_model,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def _insert_chunks(
        self,
        user_id: str,
        kb_id: str,
        doc_id: str,
        chunk_ids: List[str],
        chunks: List[Dict[str, Any]],
        embeddings: Optional[List[List[float]]] = None,
    ) -> None:
        conn = self._get_conn(user_id, kb_id)
        try:
            for i, chunk in enumerate(chunks):
                # vec0 向量表（embedding 可用时）
                if embeddings is not None:
                    try:
                        conn.execute(
                            "INSERT INTO chunks(chunk_id, document_id, chunk_index, meta_json, embedding) VALUES (?, ?, ?, ?, ?)",
                            [
                                chunk_ids[i],
                                doc_id,
                                chunk["index"],
                                json.dumps(chunk["metadata"]),
                                json.dumps(embeddings[i]),
                            ],
                        )
                    except sqlite3.OperationalError:
                        # chunks 表不存在（无 embedding 配置时），忽略
                        pass
                # FTS5 全文表（始终插入）
                tokenized = self._tokenize_for_fts(chunk["content"])
                conn.execute(
                    "INSERT INTO chunks_fts(chunk_id, document_id, content) VALUES (?, ?, ?)",
                    [chunk_ids[i], doc_id, tokenized],
                )
            conn.commit()
        finally:
            conn.close()

    def list_documents(
        self, user_id: str, kb_id: str, skip: int = 0, limit: int = 100
    ) -> List[DocumentResponse]:
        with db_session() as db:
            kb = (
                db.query(KnowledgeBaseORM)
                .filter(KnowledgeBaseORM.id == kb_id, KnowledgeBaseORM.user_id == user_id)
                .first()
            )
            if not kb:
                return []
            docs = (
                db.query(DocumentORM)
                .filter(DocumentORM.knowledge_base_id == kb_id)
                .offset(skip)
                .limit(limit)
                .all()
            )
            return [DocumentResponse.model_validate(doc) for doc in docs]

    def delete_document(self, user_id: str, kb_id: str, doc_id: str) -> bool:
        with db_session() as db:
            kb = (
                db.query(KnowledgeBaseORM)
                .filter(KnowledgeBaseORM.id == kb_id, KnowledgeBaseORM.user_id == user_id)
                .first()
            )
            if not kb:
                return False

            doc = (
                db.query(DocumentORM)
                .filter(DocumentORM.id == doc_id, DocumentORM.knowledge_base_id == kb_id)
                .first()
            )
            if not doc:
                return False

            conn = self._get_conn(user_id, kb_id)
            try:
                conn.execute("DELETE FROM chunks WHERE document_id = ?", [doc_id])
                conn.execute("DELETE FROM chunks_fts WHERE document_id = ?", [doc_id])
            except Exception as e:
                logger.warning(f"从 SQLite 删除分块失败: {e}")
            finally:
                conn.close()

            db.delete(doc)
            db.commit()
            return True

    # ==================== 检索 ====================

    async def query(self, user_id: str, kb_id: str, request: QueryRequest) -> QueryResponse:
        with db_session() as db:
            kb = (
                db.query(KnowledgeBaseORM)
                .filter(KnowledgeBaseORM.id == kb_id, KnowledgeBaseORM.user_id == user_id)
                .first()
            )
            if not kb:
                raise ValueError("知识库不存在")
            self._assert_kb_ready(user_id, kb)

            top_k = request.top_k or 10
            search_mode = request.search_mode or SearchMode(
                kb.default_search_mode or SearchMode.FULLTEXT.value
            )

            # 收集候选 chunk_id → 检索信息
            candidates: Dict[str, Dict[str, Any]] = {}

            # 无 embedding 配置时，VECTOR/HYBRID 自动降级为 FULLTEXT
            effective_mode = search_mode
            if search_mode in (SearchMode.VECTOR, SearchMode.HYBRID):
                try:
                    embedder = self._get_embedder(user_id, kb.embedding_model)
                    query_embedding = (await embedder.embed([request.query]))[0]
                    vec_results = self._search_vectors(
                        user_id,
                        kb_id,
                        query_embedding,
                        top_k,
                    )
                    for rank, (chunk_id, doc_id, score) in enumerate(vec_results):
                        candidates[chunk_id] = {
                            "chunk_id": chunk_id,
                            "doc_id": doc_id,
                            "vec_rank": rank,
                            "vec_score": score,
                            "text_rank": None,
                            "text_score": 0.0,
                        }
                except ValueError:
                    effective_mode = SearchMode.FULLTEXT

            if effective_mode in (SearchMode.FULLTEXT, SearchMode.HYBRID):
                text_results = self._search_fulltext(
                    user_id,
                    kb_id,
                    request.query,
                    top_k,
                )
                for rank, (chunk_id, doc_id, score) in enumerate(text_results):
                    if chunk_id in candidates:
                        candidates[chunk_id]["text_rank"] = rank
                        candidates[chunk_id]["text_score"] = score
                    else:
                        candidates[chunk_id] = {
                            "chunk_id": chunk_id,
                            "doc_id": doc_id,
                            "vec_rank": None,
                            "vec_score": 0.0,
                            "text_rank": rank,
                            "text_score": score,
                        }

            # 排序
            if effective_mode == SearchMode.HYBRID and len(candidates) > 0:
                fused = self._fuse_hybrid_results(candidates, top_k=top_k)
            else:
                # vector 或 fulltext 单一路径，按已有 score 排序
                fused = sorted(
                    candidates.values(),
                    key=lambda x: x["vec_score"] + x["text_score"],
                    reverse=True,
                )[:top_k]

            # maxSpread 多样性过滤：保留 top 分 65% 以上的结果
            if fused:
                if effective_mode == SearchMode.HYBRID:
                    fused = self._apply_max_spread_filter(fused, score_key="fused_score")
                elif effective_mode == SearchMode.VECTOR:
                    fused = self._apply_max_spread_filter(fused, score_key="vec_score")
                # FULLTEXT: 不应用，BM25 分数尺度与向量距离不可比

            # 批量查询：先收集所有 chunk_id，一次性 IN 查询
            chunk_ids = [item["chunk_id"] for item in fused]
            chunk_map: dict[str, DocumentChunkORM] = {}
            if chunk_ids:
                for chunk in (
                    db.query(DocumentChunkORM)
                    .filter(DocumentChunkORM.chunk_id.in_(chunk_ids))
                    .all()
                ):
                    chunk_map[str(chunk.chunk_id)] = chunk

            doc_ids = [str(chunk.document_id) for chunk in chunk_map.values()]
            doc_map: dict[str, DocumentORM] = {}
            if doc_ids:
                for doc in db.query(DocumentORM).filter(DocumentORM.id.in_(doc_ids)).all():
                    doc_map[str(doc.id)] = doc

            # 组装结果
            query_results = []
            for item in fused:
                chunk_id = item["chunk_id"]
                chunk = chunk_map.get(chunk_id)
                if not chunk:
                    continue
                if request.filter:
                    meta = chunk.meta_info or {}
                    if not all(str(meta.get(k)) == str(v) for k, v in request.filter.items()):
                        continue
                doc = doc_map.get(str(chunk.document_id))
                # hybrid 时显示融合分，单模式时显示原始分
                if effective_mode == SearchMode.HYBRID:
                    display_score = item.get("fused_score", item["vec_score"] + item["text_score"])
                elif effective_mode == SearchMode.VECTOR:
                    display_score = item["vec_score"]
                else:
                    display_score = item["text_score"]
                query_results.append(
                    QueryResult(
                        content=chunk.content,
                        score=round(display_score, 4),
                        document_id=chunk.document_id,
                        document_name=doc.filename if doc else "Unknown",
                        chunk_index=chunk.chunk_index,
                        metadata=chunk.meta_info or {},
                    )
                )

            return QueryResponse(
                query=request.query,
                knowledge_base_id=kb_id,
                results=query_results,
                total=len(query_results),
            )

    def _search_vectors(
        self,
        user_id: str,
        kb_id: str,
        query_embedding: List[float],
        top_k: int,
    ) -> List[tuple]:
        conn = self._get_conn(user_id, kb_id)
        try:
            rows = conn.execute(
                """
                    SELECT chunk_id, document_id, distance
                    FROM chunks
                    WHERE embedding MATCH ?
                    AND k = ?
                    ORDER BY distance
                """,
                [json.dumps(query_embedding), top_k],
            ).fetchall()
            # sqlite-vec 返回 L2 距离，转为 relevance score
            return [(r[0], r[1], 1.0 / (1.0 + r[2])) for r in rows]
        finally:
            conn.close()

    def _search_fulltext(
        self,
        user_id: str,
        kb_id: str,
        query: str,
        top_k: int,
    ) -> List[tuple]:
        """FTS5 全文检索，返回 (chunk_id, doc_id, score)。"""
        match_query = self._build_fts_match_query(query)
        if not match_query:
            return []
        conn = self._get_conn(user_id, kb_id)
        try:
            rows = conn.execute(
                """
                    SELECT chunk_id, document_id, bm25(chunks_fts)
                    FROM chunks_fts
                    WHERE content MATCH ?
                    ORDER BY bm25(chunks_fts)
                    LIMIT ?
                """,
                [match_query, top_k],
            ).fetchall()
            # bm25 越小越相关，转为正相关分
            return [(r[0], r[1], 1.0 / (1.0 + abs(r[2]))) for r in rows]
        except sqlite3.OperationalError as exc:
            logger.warning("知识库 FTS5 查询失败: %s", exc)
            return []
        finally:
            conn.close()

    @staticmethod
    def _fuse_hybrid_results(
        candidates: Dict[str, Dict[str, Any]],
        k: int = 60,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """RRF (Reciprocal Rank Fusion) 融合向量与全文结果。"""
        fused = []
        for _chunk_id, data in candidates.items():
            vec_rank = data["vec_rank"]
            text_rank = data["text_rank"]
            vec_part = 1.0 / (k + (vec_rank + 1)) if vec_rank is not None else 0.0
            text_part = 1.0 / (k + (text_rank + 1)) if text_rank is not None else 0.0
            data["fused_score"] = vec_part + text_part
            fused.append(data)
        fused.sort(key=lambda x: x["fused_score"], reverse=True)
        return fused[:top_k]

    @staticmethod
    def _apply_max_spread_filter(
        results: List[Dict[str, Any]],
        score_key: str = "vec_score",
        max_spread_pct: float = 0.65,
    ) -> List[Dict[str, Any]]:
        """保留分数在 top 分的 max_spread_pct 以上的结果，保证多样性。

        借鉴 GitHub Copilot 的 maxSpread 策略，避免返回高度相似的 chunk。
        至少保留 top-1 结果。
        """
        if not results:
            return results

        top_score = results[0].get(score_key, 0.0)
        if top_score <= 0:
            return results

        threshold = top_score * max_spread_pct
        filtered = [r for r in results if r.get(score_key, 0.0) >= threshold]
        return filtered if filtered else results[:1]

    # ==================== 原始数据探查 ====================

    def list_tables(self, user_id: str, kb_id: str) -> List[Dict[str, Any]]:
        """列出知识库底层 SQLite 的所有表及其列信息。"""
        conn = self._get_conn(user_id, kb_id)
        try:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = []
            for (name,) in cur.fetchall():
                # 过滤 sqlite 内部表和 vec0/fts5 内部实现表
                if name == "sqlite_sequence":
                    continue
                if name.startswith("chunks_") and name not in ("chunks", "chunks_fts"):
                    continue
                if not _VALID_SQL_IDENTIFIER.match(name):
                    continue
                try:
                    cols_cur = conn.execute(f'PRAGMA table_info("{name}")')
                    columns = [
                        {"name": col[1], "type": col[2] or "ANY"} for col in cols_cur.fetchall()
                    ]
                except Exception:
                    columns = []
                tables.append({"name": name, "columns": columns})
            return tables
        finally:
            conn.close()

    def execute_raw_sql(self, user_id: str, kb_id: str, sql: str) -> Dict[str, Any]:
        """对知识库底层 SQLite 执行原始 SELECT 查询。"""
        import re

        cleaned = sql.strip()
        if not cleaned:
            raise ValueError("SQL 不能为空")
        # 只允许 SELECT 查询
        first_word = re.sub(r"^\s*(--[^\n]*\n|\s)*", "", cleaned, flags=re.IGNORECASE).lstrip()
        if not re.match(r"^SELECT\b", first_word, re.IGNORECASE):
            raise ValueError("只允许执行 SELECT 查询")

        conn = self._get_conn(user_id, kb_id)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(cleaned)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description] if cur.description else []
            result_rows = [dict(row) for row in rows]
            return {
                "columns": columns,
                "rows": result_rows,
                "row_count": len(result_rows),
            }
        finally:
            conn.close()

    # ==================== 辅助方法 ====================

    def _kb_to_response(self, kb: KnowledgeBaseORM, db: Session) -> KnowledgeBaseResponse:
        doc_count = db.query(DocumentORM).filter(DocumentORM.knowledge_base_id == kb.id).count()
        metadata = self._sync_kb_runtime_metadata(kb.user_id, kb)
        init_status = str(metadata.get("init_status") or KnowledgeBaseInitStatus.READY.value)
        config_complete = self._parse_bool_metadata(
            str(metadata.get("config_complete", "")),
            init_status == KnowledgeBaseInitStatus.READY.value,
        )
        requires_reindex = self._parse_bool_metadata(
            str(metadata.get("requires_reindex", "")),
            init_status == KnowledgeBaseInitStatus.NEEDS_REINDEX.value,
        )
        return KnowledgeBaseResponse(
            id=kb.id,
            name=kb.name,
            description=kb.description,
            user_id=kb.user_id,
            kind=kb.kind or "document",
            embedding_model=kb.embedding_model,
            chunk_size=kb.chunk_size,
            chunk_overlap=kb.chunk_overlap,
            default_search_mode=kb.default_search_mode or SearchMode.FULLTEXT.value,
            default_extraction_mode=kb.default_extraction_mode,
            extraction_mode_mapping=kb.extraction_mode_mapping,
            document_count=doc_count,
            init_status=init_status,
            config_complete=config_complete,
            config_issue=str(metadata.get("config_issue") or "") or None,
            config_version=self._parse_int_metadata(
                str(metadata.get("config_version", "")),
                DEFAULT_CONFIG_VERSION,
            ),
            last_indexed_config_version=self._parse_int_metadata(
                str(metadata.get("last_indexed_config_version", "")),
                0,
            ),
            can_edit_index_config=doc_count == 0,
            requires_reindex=requires_reindex,
            scope=getattr(kb, "scope", "global") or "global",
            workspace_id=getattr(kb, "workspace_id", None),
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        )


# 单例
_sqlite_kb_service: Optional[SQLiteKBService] = None


def get_sqlite_kb_service() -> SQLiteKBService:
    global _sqlite_kb_service
    if _sqlite_kb_service is None:
        _sqlite_kb_service = SQLiteKBService()
    return _sqlite_kb_service
