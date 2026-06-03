import sqlite3
from pathlib import Path

import pytest

from app.document_extraction import DocumentExtractionMode, DocumentExtractionResult
from app.knowledge.models import (
    KnowledgeBaseCreate,
    KnowledgeBaseInitStatus,
    KnowledgeBaseUpdate,
    QueryRequest,
    SearchMode,
)
from app.core.time import utc_now_naive
from app.knowledge.sqlite_kb_service import SQLiteKBService


def _metadata_rows(db_path: Path) -> dict[str, str]:
    conn = sqlite3.connect(db_path)
    try:
        return dict(conn.execute("SELECT key, value FROM kb_metadata").fetchall())
    finally:
        conn.close()


def test_fts_match_query_handles_ip_address_without_syntax_error() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE chunks_fts USING fts5(content)")
        conn.execute(
            "INSERT INTO chunks_fts(content) VALUES (?)",
            [SQLiteKBService._tokenize_for_fts("127.0.0.1 localhost")],
        )

        match_query = SQLiteKBService._build_fts_match_query("127.0.0.1")
        rows = conn.execute(
            "SELECT rowid FROM chunks_fts WHERE content MATCH ?",
            [match_query],
        ).fetchall()

        assert rows == [(1,)]
    finally:
        conn.close()


def test_fts_match_query_ignores_punctuation_only_query() -> None:
    assert SQLiteKBService._build_fts_match_query("...") == ""


class TestApplyMaxSpreadFilter:
    def test_empty_list_returns_empty(self) -> None:
        assert SQLiteKBService._apply_max_spread_filter([]) == []

    def test_single_result_returns_single(self) -> None:
        results = [{"chunk_id": "a", "vec_score": 0.95}]
        filtered = SQLiteKBService._apply_max_spread_filter(results, score_key="vec_score")
        assert len(filtered) == 1
        assert filtered[0]["chunk_id"] == "a"

    def test_filters_low_scoring_results(self) -> None:
        results = [
            {"chunk_id": "a", "vec_score": 0.95},
            {"chunk_id": "b", "vec_score": 0.90},
            {"chunk_id": "c", "vec_score": 0.30},
            {"chunk_id": "d", "vec_score": 0.20},
        ]
        filtered = SQLiteKBService._apply_max_spread_filter(results, score_key="vec_score")
        # threshold = 0.95 * 0.65 = 0.6175
        # a (0.95) ✓, b (0.90) ✓, c (0.30) ✗, d (0.20) ✗
        assert len(filtered) == 2
        assert [r["chunk_id"] for r in filtered] == ["a", "b"]

    def test_all_zero_scores_returns_all(self) -> None:
        results = [
            {"chunk_id": "a", "vec_score": 0.0},
            {"chunk_id": "b", "vec_score": 0.0},
        ]
        filtered = SQLiteKBService._apply_max_spread_filter(results, score_key="vec_score")
        assert len(filtered) == 2

    def test_all_below_threshold_keeps_at_least_top(self) -> None:
        results = [
            {"chunk_id": "a", "fused_score": 0.01},
            {"chunk_id": "b", "fused_score": 0.001},
            {"chunk_id": "c", "fused_score": 0.0009},
        ]
        # threshold = 0.01 * 0.65 = 0.0065, only a passes
        filtered = SQLiteKBService._apply_max_spread_filter(results, score_key="fused_score")
        assert len(filtered) == 1
        assert filtered[0]["chunk_id"] == "a"

    def test_edge_case_threshold_exactly_at_boundary(self) -> None:
        results = [
            {"chunk_id": "a", "vec_score": 1.0},
            {"chunk_id": "b", "vec_score": 0.65},
            {"chunk_id": "c", "vec_score": 0.649},
        ]
        filtered = SQLiteKBService._apply_max_spread_filter(results, score_key="vec_score")
        # threshold = 0.65, b (0.65) ✓, c (0.649) ✗
        assert len(filtered) == 2
        assert [r["chunk_id"] for r in filtered] == ["a", "b"]


def _create_kb(
    kb_id: str,
    *,
    embedding_model: str | None = "test-embedding-model",
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    default_search_mode: str = SearchMode.FULLTEXT.value,
) -> Path:
    """在全局工作区下直接创建知识库 .db 文件（不经过 service 层，避免 mock 依赖）。"""
    from app.core.config import WORKSPACE_DIR

    workspace_root = WORKSPACE_DIR / "local_default" / "global_workspace"
    kb_dir = workspace_root / ".aiasys" / "knowledge"
    kb_dir.mkdir(parents=True, exist_ok=True)
    db_path = kb_dir / f"{kb_id}.db"
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    SQLiteKBService._ensure_metadata_table(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kb_documents (
            id TEXT PRIMARY KEY,
            
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            status TEXT NOT NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kb_chunks (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            meta_json TEXT,
            chunk_id TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_chunks_doc_id ON kb_chunks(document_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_chunks_chunk_id ON kb_chunks(chunk_id)")

    now = utc_now_naive().isoformat()
    init_status = (
        KnowledgeBaseInitStatus.READY.value
        if embedding_model
        else KnowledgeBaseInitStatus.DRAFT.value
    )
    config_complete = "true" if embedding_model else "false"
    config_issue = "" if embedding_model else "需要先配置 embedding 模型"

    meta_rows = [
        ("schema_version", "1", now),
        ("knowledge_base_id", kb_id, now),
        ("name", kb_id, now),
        ("user_id", "local_default", now),
        ("kind", "document", now),
        ("scope", "global", now),
        ("embedding_model", embedding_model or "", now),
        ("chunk_size", str(chunk_size), now),
        ("chunk_overlap", str(chunk_overlap), now),
        ("default_search_mode", default_search_mode, now),
        ("init_status", init_status, now),
        ("config_complete", config_complete, now),
        ("config_issue", config_issue, now),
        ("config_version", "1", now),
        ("last_indexed_config_version", "0", now),
        ("created_at", now, now),
        ("updated_at", now, now),
    ]
    conn.executemany(
        "INSERT INTO kb_metadata(key, value, updated_at) VALUES (?, ?, ?)",
        meta_rows,
    )
    conn.commit()
    conn.close()
    return db_path


def _add_document_to_kb(
    db_path: Path,
    doc_id: str,
    kb_id: str,
    filename: str = "old.md",
    file_type: str = "md",
    file_size: int = 3,
    chunk_count: int = 1,
) -> None:
    """向已有知识库 .db 插入一条文档记录。"""
    conn = sqlite3.connect(str(db_path))
    now = utc_now_naive().isoformat()
    conn.execute(
        """
        INSERT INTO kb_documents(
            id, filename, file_type, file_size,
            status, chunk_count, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [doc_id, filename, file_type, file_size, "completed", chunk_count, now, now],
    )
    conn.commit()
    conn.close()


def test_create_knowledge_base_persists_import_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "local_default" / "global_workspace"
    monkeypatch.setattr("app.core.config.WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(
        "app.knowledge.sqlite_kb_service.get_llm_config_service",
        lambda: type(
            "LLMConfigStub",
            (),
            {
                "resolve_default_embedding_model_id": lambda self, user_id: "embedding-default",
                "resolve_embedding_model_config": lambda self, user_id, model_id: {
                    "model_name": model_id,
                    "dimension": 3,
                },
            },
        )(),
    )

    service = SQLiteKBService()
    response = service.create_knowledge_base(
        "local_default",
        KnowledgeBaseCreate(
            name="导入配置库",
            embedding_model="embedding-custom",
            chunk_size=256,
            chunk_overlap=32,
            default_search_mode=SearchMode.HYBRID,
        ),
        workspace_root=workspace_root,
        scope="global",
    )

    assert response.embedding_model == "embedding-custom"
    assert response.chunk_size == 256
    assert response.chunk_overlap == 32
    assert response.default_search_mode == SearchMode.HYBRID.value

    metadata = _metadata_rows(workspace_root / ".aiasys" / "knowledge" / f"{response.id}.db")
    assert metadata["knowledge_base_id"] == response.id
    assert metadata["kind"] == "document"
    assert metadata["embedding_model"] == "embedding-custom"
    assert metadata["chunk_size"] == "256"
    assert metadata["chunk_overlap"] == "32"
    assert metadata["default_search_mode"] == SearchMode.HYBRID.value
    assert metadata["init_status"] == KnowledgeBaseInitStatus.READY.value
    assert metadata["config_complete"] == "true"
    assert metadata["config_version"] == "1"
    assert metadata["last_indexed_config_version"] == "0"


def test_create_knowledge_base_without_embedding_stays_draft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.config.WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(
        "app.knowledge.sqlite_kb_service.get_llm_config_service",
        lambda: type(
            "LLMConfigStub",
            (),
            {"resolve_default_embedding_model_id": lambda self, user_id: None},
        )(),
    )

    response = SQLiteKBService().create_knowledge_base(
        "local_default",
        KnowledgeBaseCreate(name="待配置知识库"),
    )

    assert response.embedding_model is None
    assert response.init_status == KnowledgeBaseInitStatus.DRAFT.value
    assert response.config_complete is False
    assert response.config_issue == "需要先配置 embedding 模型"
    assert response.can_edit_index_config is True

    metadata = _metadata_rows(
        tmp_path
        / "local_default"
        / "global_workspace"
        / ".aiasys"
        / "knowledge"
        / f"{response.id}.db"
    )
    assert metadata["init_status"] == KnowledgeBaseInitStatus.DRAFT.value
    assert metadata["config_complete"] == "false"
    assert metadata["config_issue"] == "需要先配置 embedding 模型"


def test_empty_knowledge_base_update_embedding_moves_to_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.config.WORKSPACE_DIR", tmp_path)

    db_path = _create_kb("kb-draft", embedding_model=None)

    response = SQLiteKBService().update_knowledge_base(
        "local_default",
        "kb-draft",
        KnowledgeBaseUpdate(
            embedding_model="embedding-ready",
            chunk_size=256,
            chunk_overlap=32,
            default_search_mode=SearchMode.HYBRID,
        ),
    )

    assert response is not None
    assert response.embedding_model == "embedding-ready"
    assert response.init_status == KnowledgeBaseInitStatus.READY.value
    assert response.config_complete is True
    assert response.config_issue is None
    assert response.config_version == 2

    metadata = _metadata_rows(
        tmp_path / "local_default" / "global_workspace" / ".aiasys" / "knowledge" / "kb-draft.db"
    )
    assert metadata["embedding_model"] == "embedding-ready"
    assert metadata["init_status"] == KnowledgeBaseInitStatus.READY.value
    assert metadata["config_complete"] == "true"
    assert metadata["config_version"] == "2"


@pytest.mark.asyncio
async def test_batch_upload_applies_import_config_and_returns_per_file_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.config.WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(SQLiteKBService, "_ensure_kb_schema", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(SQLiteKBService, "_insert_chunks", lambda *_args, **_kwargs: None)
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        SQLiteKBService,
        "_get_embedder",
        lambda *_args, **_kwargs: type(
            "EmbedderStub",
            (),
            {"embed": AsyncMock(return_value=[[0.1, 0.2, 0.3] for _ in range(100)])},
        )(),
    )
    monkeypatch.setattr(
        "app.knowledge.sqlite_kb_service.get_document_extraction_service",
        lambda: type(
            "ExtractionStub",
            (),
            {
                "extract": lambda self, path, file_bytes, mode=None: DocumentExtractionResult(
                    text=file_bytes.decode("utf-8"),
                    mode_used=DocumentExtractionMode.BASIC,
                    requested_mode=DocumentExtractionMode.parse(mode),
                    file_type=Path(path).suffix.lstrip(".") or "txt",
                )
            },
        )(),
    )

    _create_kb("kb-batch")

    response = await SQLiteKBService().upload_documents(
        user_id="local_default",
        kb_id="kb-batch",
        files=[("a.md", b"alpha content"), ("b.md", b"beta content")],
        extraction_mode="basic",
        embedding_model="embedding-custom",
        chunk_size=128,
        chunk_overlap=16,
        search_mode=SearchMode.HYBRID,
    )

    assert response.success is True
    assert response.total == 2
    assert response.successful_count == 2
    assert response.failed_count == 0
    assert [item.filename for item in response.results] == ["a.md", "b.md"]
    assert all(item.search_mode == SearchMode.HYBRID.value for item in response.results)
    assert all(item.embedding_model == "embedding-custom" for item in response.results)
    assert all(item.chunk_size == 128 for item in response.results)
    assert all(item.chunk_overlap == 16 for item in response.results)

    # 验证 .db 文件中的元数据（替代原来对 aiasys.db ORM 的断言）
    metadata = _metadata_rows(
        tmp_path / "local_default" / "global_workspace" / ".aiasys" / "knowledge" / "kb-batch.db"
    )
    assert metadata["knowledge_base_id"] == "kb-batch"
    assert metadata["embedding_model"] == "embedding-custom"
    assert metadata["chunk_size"] == "128"
    assert metadata["chunk_overlap"] == "16"
    assert metadata["default_search_mode"] == SearchMode.HYBRID.value
    assert metadata["init_status"] == KnowledgeBaseInitStatus.READY.value
    assert metadata["config_complete"] == "true"
    assert metadata["config_version"] == "2"
    assert metadata["last_indexed_config_version"] == "2"


@pytest.mark.asyncio
async def test_upload_document_rejects_draft_knowledge_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.config.WORKSPACE_DIR",
        tmp_path,
    )

    _create_kb("kb-draft-upload", embedding_model=None)
    response = await SQLiteKBService().upload_document(
        user_id="local_default",
        kb_id="kb-draft-upload",
        filename="draft.md",
        file_bytes=b"draft",
    )

    assert response.success is False
    assert response.message == "需要先配置 embedding 模型"
    assert response.embedding_model is None


@pytest.mark.asyncio
async def test_query_rejects_draft_knowledge_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.config.WORKSPACE_DIR",
        tmp_path,
    )

    _create_kb("kb-draft-query", embedding_model=None)

    with pytest.raises(ValueError, match="需要先配置 embedding 模型"):
        await SQLiteKBService().query(
            user_id="local_default",
            kb_id="kb-draft-query",
            request=QueryRequest(query="alpha"),
        )


@pytest.mark.asyncio
async def test_upload_document_rejects_embedding_model_switch_after_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.config.WORKSPACE_DIR",
        tmp_path,
    )
    monkeypatch.setattr(SQLiteKBService, "_ensure_kb_schema", lambda *_args, **_kwargs: None)

    db_path = _create_kb("kb-existing", embedding_model="embedding-a")
    _add_document_to_kb(db_path, "doc-existing", "kb-existing")

    response = await SQLiteKBService().upload_document(
        user_id="local_default",
        kb_id="kb-existing",
        filename="new.md",
        file_bytes=b"new",
        embedding_model="embedding-b",
    )

    assert response.success is False
    assert "不能在导入时切换 embedding 模型" in response.message

    # 验证 .db 中元数据未被修改
    metadata = _metadata_rows(db_path)
    assert metadata["embedding_model"] == "embedding-a"


@pytest.mark.asyncio
async def test_upload_document_rejects_invalid_chunk_config_without_persisting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.config.WORKSPACE_DIR",
        tmp_path,
    )

    db_path = _create_kb("kb-invalid-chunk", chunk_size=512, chunk_overlap=50)

    response = await SQLiteKBService().upload_document(
        user_id="local_default",
        kb_id="kb-invalid-chunk",
        filename="bad.md",
        file_bytes=b"bad",
        chunk_size=32,
        chunk_overlap=8,
    )

    assert response.success is False
    assert "chunk_size 必须在 64-8192 之间" in response.message

    metadata = _metadata_rows(db_path)
    assert metadata["chunk_size"] == "512"
    assert metadata["chunk_overlap"] == "50"


@pytest.mark.asyncio
async def test_upload_document_rejects_chunk_config_change_after_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.config.WORKSPACE_DIR",
        tmp_path,
    )

    db_path = _create_kb(
        "kb-existing-chunk", embedding_model="embedding-a", chunk_size=512, chunk_overlap=50
    )
    _add_document_to_kb(db_path, "doc-existing-chunk", "kb-existing-chunk")

    response = await SQLiteKBService().upload_document(
        user_id="local_default",
        kb_id="kb-existing-chunk",
        filename="new.md",
        file_bytes=b"new",
        chunk_size=256,
        chunk_overlap=32,
    )

    assert response.success is False
    assert "不能在导入时修改分块配置" in response.message

    metadata = _metadata_rows(db_path)
    assert metadata["chunk_size"] == "512"
    assert metadata["chunk_overlap"] == "50"


def test_update_rejects_chunk_config_change_after_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.config.WORKSPACE_DIR",
        tmp_path,
    )

    db_path = _create_kb(
        "kb-update-chunk", embedding_model="embedding-a", chunk_size=512, chunk_overlap=50
    )
    _add_document_to_kb(db_path, "doc-update-chunk", "kb-update-chunk")

    with pytest.raises(ValueError, match="不能直接修改分块配置"):
        SQLiteKBService().update_knowledge_base(
            "local_default",
            "kb-update-chunk",
            KnowledgeBaseUpdate(chunk_size=256),
        )


@pytest.mark.asyncio
async def test_query_uses_knowledge_base_default_search_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock

    used_modes: list[SearchMode] = []

    def fake_search_fulltext(self, user_id, kb_id, query, top_k):
        used_modes.append(SearchMode.FULLTEXT)
        return []

    def fake_search_vectors(self, user_id, kb_id, query_embedding, top_k):
        used_modes.append(SearchMode.VECTOR)
        return []

    monkeypatch.setattr(SQLiteKBService, "_search_fulltext", fake_search_fulltext)
    monkeypatch.setattr(SQLiteKBService, "_search_vectors", fake_search_vectors)
    monkeypatch.setattr(
        SQLiteKBService,
        "_get_embedder",
        lambda *_args, **_kwargs: type(
            "EmbedderStub",
            (),
            {"embed": AsyncMock(return_value=[[0.1, 0.2, 0.3]])},
        )(),
    )

    _create_kb(
        "kb-query-default",
        embedding_model="embedding-a",
        default_search_mode=SearchMode.HYBRID.value,
    )

    response = await SQLiteKBService().query(
        user_id="local_default",
        kb_id="kb-query-default",
        request=QueryRequest(query="alpha"),
    )

    assert response.results == []
    assert used_modes == [SearchMode.VECTOR, SearchMode.FULLTEXT]
