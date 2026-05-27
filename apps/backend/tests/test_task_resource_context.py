from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.tools import graphrag_tool, knowledge_tool
from app.graphrag.models.entity import Entity
from app.graphrag.models.relation import Relation
from app.services.history import session_history_projection as history_projection
from app.services.session.config_projection import (
    write_workspace_database_mount_data,
)
from app.core import config as config_module
from app.services.task_resource_context import (
    build_task_resource_context,
    format_task_resource_context_for_prompt,
)


def test_task_resource_context_formats_mounted_resources_and_attachments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_dir = tmp_path / "workspace"
    global_workspace_dir = tmp_path / "local_default" / "global_workspace"
    global_resources_dir = global_workspace_dir / "resources"

    write_workspace_database_mount_data(
        workspace_dir,
        {"version": 1, "connector_ids": ["dbc-a", "dbc-missing"]},
    )

    monkeypatch.setattr(
        "app.services.task_resource_context.get_sqlite_kb_service",
        lambda: SimpleNamespace(
            list_knowledge_bases=lambda user_id: [
                SimpleNamespace(id="kb-a", name="财报库", document_count=3),
                SimpleNamespace(id="kb-c", name="别的知识库", document_count=9),
            ]
        ),
    )
    monkeypatch.setattr(
        "app.services.task_resource_context.DatabaseConnectorService",
        lambda *_args, **_kwargs: SimpleNamespace(
            list_connectors=lambda user_id: [
                SimpleNamespace(
                    connector_id="dbc-a",
                    name="订单库",
                    db_type="postgres",
                    readonly=True,
                    default_grants=["schema_read", "data_read"],
                ),
                SimpleNamespace(
                    connector_id="dbc-b",
                    name="日志库",
                    db_type="mysql",
                    readonly=False,
                    default_grants=["schema_read", "data_read", "data_write"],
                ),
            ],
        ),
    )

    # 知识库已取消挂载，改为 AI 自行发现全部知识库
    # 知识图谱已取消挂载，改为扫描文件系统发现
    # 需要在 tmp_path 下创建 SQLite 图谱文件以便测试扫描
    (global_resources_dir / "graphs").mkdir(parents=True, exist_ok=True)
    (global_resources_dir / "graphs" / "graph-a.db").write_bytes(b"")
    (global_resources_dir / "graphs" / "graph-b.db").write_bytes(b"")
    (global_workspace_dir / "shared.md").write_text("shared", encoding="utf-8")
    monkeypatch.setattr(config_module, "WORKSPACE_DIR", tmp_path)

    resource_context = build_task_resource_context(
        user_id="local_default",
        session_id="session-a",
        workspace_dir=workspace_dir,
        attached_files=["report.pdf", "/workspace/notes.md"],
    )
    prompt_context = format_task_resource_context_for_prompt(resource_context)

    assert resource_context["workspace_database_mounts"] == [
        {"connector_id": "dbc-a", "name": "订单库", "db_type": "postgres"},
        {"connector_id": "dbc-missing", "name": "dbc-missing", "db_type": None},
    ]
    assert resource_context["current_session_database_resources"] == [
        {
            "connector_id": "dbc-a",
            "handle": "connector:dbc-a",
            "name": "订单库",
            "db_type": "postgres",
            "readonly": True,
        },
        {
            "connector_id": "dbc-b",
            "handle": "connector:dbc-b",
            "name": "日志库",
            "db_type": "mysql",
            "readonly": False,
        },
    ]
    # 知识库取消挂载后，所有可见知识库都进入上下文
    # 知识图谱取消挂载后，主图谱为 None；全局工作区文件也进入可直接引用对象
    # 对象数 = dbc-a + dbc-missing + kb-a + kb-c + graph-a + graph-b
    # + connector:dbc-a + connector:dbc-b + report.pdf + notes.md
    # + /global/resources/graphs/graph-a.db + /global/resources/graphs/graph-b.db
    # + /global/shared.md = 13
    assert resource_context["direct_reference_object_count"] == 13
    assert resource_context["mounted_knowledge_graph_ids"] == ["graph-a", "graph-b"]
    assert resource_context["attached_files"] == [
        "/workspace/report.pdf",
        "/workspace/notes.md",
    ]
    assert resource_context["global_workspace_resources"] == [
        {
            "relative_path": "resources/graphs/graph-a.db",
            "display_path": "/global/resources/graphs/graph-a.db",
            "size_bytes": 0,
        },
        {
            "relative_path": "resources/graphs/graph-b.db",
            "display_path": "/global/resources/graphs/graph-b.db",
            "size_bytes": 0,
        },
        {
            "relative_path": "shared.md",
            "display_path": "/global/shared.md",
            "size_bytes": 6,
        }
    ]
    assert "工作区挂载摘要：数据库 2 个、知识库 2 个、知识图谱 2 个" in prompt_context
    assert "当前会话资源摘要：数据库句柄 2 个、当前轮附件 2 个" in prompt_context
    assert "全局工作区资源：共 3 个文件" in prompt_context
    assert "/global/shared.md" in prompt_context
    assert "可直接引用资源对象数：13" in prompt_context
    assert "财报库(kb-a, 3 篇文档)" in prompt_context
    assert "当前任务工作区挂载了 2 个数据库连接：订单库(dbc-a, postgres)；dbc-missing(dbc-missing)" in prompt_context
    assert "当前会话已挂载 2 个数据库资源：订单库[connector:dbc-a, postgres]；日志库[connector:dbc-b, mysql]" in prompt_context
    # 主图谱概念已取消
    assert "当前任务主知识图谱" not in prompt_context
    assert "/workspace/report.pdf" in prompt_context


def test_wrap_user_prompt_includes_resource_context_and_unwraps() -> None:
    wrapped = history_projection.wrap_user_prompt(
        "请根据当前任务资源回答。",
        runtime_summary=None,
        resource_context="- 当前任务已挂载 1 个知识库：财报库(kb-a)",
    )

    assert history_projection.USER_PROMPT_RESOURCE_CONTEXT_START in wrapped
    assert "财报库(kb-a)" in wrapped
    assert history_projection.unwrap_user_prompt(wrapped) == "请根据当前任务资源回答。"


@pytest.mark.asyncio
async def test_knowledge_query_tool_prefers_mounted_knowledge_bases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_query(user_id, kb_id, request):
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    content=f"{kb_id} result",
                    score=0.9 if kb_id == "kb-mounted" else 0.1,
                    document_name=f"{kb_id}.md",
                    chunk_index=0,
                )
            ]
        )

    tool = knowledge_tool.KnowledgeBaseQuery()
    tool._kb_service = SimpleNamespace(
        list_knowledge_bases=lambda user_id: [
            SimpleNamespace(id="kb-mounted", name="已挂载知识库", document_count=2),
            SimpleNamespace(id="kb-other", name="其他知识库", document_count=5),
        ],
        query=fake_query,
    )
    monkeypatch.setattr(knowledge_tool, "_resolve_current_user_id", lambda: "local_default")
    monkeypatch.setattr(knowledge_tool, "_resolve_workspace_root", lambda scope: Path("/tmp/workspace"))
    monkeypatch.setattr(
        knowledge_tool,
        "resolve_mounted_knowledge_base_summaries",
        lambda user_id=None, workspace_dir=None: [
            {"id": "kb-mounted", "name": "已挂载知识库", "document_count": 2}
        ],
    )

    result = await tool.invoke(
        **knowledge_tool.KnowledgeQueryParams(
            query="营收趋势",
            top_k=3,
        ).model_dump()
    )

    assert "查询范围：当前任务已挂载知识库" in result.output
    assert "已挂载知识库 (kb-mounted)" in result.output
    assert "kb-other" not in result.output


@pytest.mark.asyncio
async def test_create_knowledge_base_tool_wraps_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / ".aiasys").mkdir()
    token_ws = knowledge_tool.current_workspace.set(str(workspace_dir))
    try:
        created_requests = []
        tool = knowledge_tool.CreateKnowledgeBase()
        tool._kb_service = SimpleNamespace(
            create_knowledge_base=lambda user_id, request, workspace_root=None, scope="workspace", workspace_id=None: (
                created_requests.append((user_id, request))
                or SimpleNamespace(
                    id="kb-new",
                    name=request.name,
                    kind=request.kind.value,
                    embedding_model=request.embedding_model or "embedding-default",
                    chunk_size=request.chunk_size,
                    chunk_overlap=request.chunk_overlap,
                    default_search_mode=request.default_search_mode.value,
                    model_dump=lambda *args, **kwargs: {
                        "id": "kb-new",
                        "name": request.name,
                        "kind": request.kind.value,
                        "default_search_mode": request.default_search_mode.value,
                    },
                )
            )
        )
        monkeypatch.setattr(knowledge_tool, "_resolve_current_user_id", lambda: "local_default")

        result = await tool.invoke(
            name="项目资料库",
            description="项目文档",
            embedding_model="embedding-x",
            chunk_size=256,
            chunk_overlap=20,
        )
    finally:
        knowledge_tool.current_workspace.reset(token_ws)

    assert result.is_error is False
    assert "知识库创建成功：项目资料库" in result.output
    assert created_requests[0][0] == "local_default"
    assert created_requests[0][1].name == "项目资料库"
    assert created_requests[0][1].embedding_model == "embedding-x"


@pytest.mark.asyncio
async def test_update_knowledge_base_tool_wraps_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updated_requests = []
    tool = knowledge_tool.UpdateKnowledgeBase()
    tool._kb_service = SimpleNamespace(
        update_knowledge_base=lambda user_id, kb_id, request: (
            updated_requests.append((user_id, kb_id, request))
            or SimpleNamespace(
                id=kb_id,
                name=request.name or "项目资料库",
                description=request.description,
                embedding_model=request.embedding_model or "embedding-default",
                chunk_size=request.chunk_size or 512,
                chunk_overlap=request.chunk_overlap or 50,
                default_search_mode=(
                    request.default_search_mode.value
                    if request.default_search_mode
                    else "hybrid"
                ),
                default_extraction_mode=request.default_extraction_mode,
                requires_reindex=False,
                model_dump=lambda *args, **kwargs: {
                    "id": kb_id,
                    "name": request.name or "项目资料库",
                    "description": request.description,
                    "default_search_mode": (
                        request.default_search_mode.value
                        if request.default_search_mode
                        else "hybrid"
                    ),
                },
            )
        )
    )
    monkeypatch.setattr(knowledge_tool, "_resolve_current_user_id", lambda: "local_default")

    result = await tool.invoke(
        base_id="kb-new",
        name="项目资料库 v2",
        description="更新后的资料库",
        default_search_mode="hybrid",
        default_extraction_mode="docling",
        extraction_mode_mapping={".pdf": "docling"},
    )

    assert result.is_error is False
    assert "知识库已更新：项目资料库 v2" in result.output
    assert "默认检索策略: hybrid" in result.output
    assert updated_requests[0][0] == "local_default"
    assert updated_requests[0][1] == "kb-new"
    assert updated_requests[0][2].name == "项目资料库 v2"
    assert updated_requests[0][2].default_search_mode.value == "hybrid"
    assert updated_requests[0][2].default_extraction_mode == "docling"
    assert updated_requests[0][2].extraction_mode_mapping == {".pdf": "docling"}


@pytest.mark.asyncio
async def test_upload_documents_to_knowledge_base_tool_reads_workspace_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source_file = workspace / "notes.md"
    source_file.write_text("# Notes\n\ncontent", encoding="utf-8")
    uploads = []

    async def fake_upload_document(**kwargs):
        payload = dict(kwargs)
        uploads.append(kwargs)
        return SimpleNamespace(
            success=True,
            document_id="doc-1",
            filename=kwargs["filename"],
            message="上传成功",
            chunk_count=1,
            extraction_mode=kwargs["extraction_mode"],
            model_dump=lambda *args, **model_dump_kwargs: {
                "success": True,
                "document_id": "doc-1",
                "filename": payload["filename"],
                "message": "上传成功",
                "chunk_count": 1,
                "extraction_mode": payload["extraction_mode"],
            },
        )

    tool = knowledge_tool.UploadDocumentsToKnowledgeBase()
    tool._kb_service = SimpleNamespace(
        get_knowledge_base=lambda user_id, kb_id: SimpleNamespace(id=kb_id, name="项目资料库"),
        upload_document=fake_upload_document,
    )
    monkeypatch.setattr(knowledge_tool, "_resolve_current_user_id", lambda: "local_default")
    token = knowledge_tool.current_workspace.set(str(workspace))
    try:
        result = await tool.invoke(
            base_id="kb-new",
            files=["notes.md"],
            extraction_mode="enhanced",
            embedding_model="embedding-x",
            chunk_size=256,
            chunk_overlap=32,
            search_mode="hybrid",
        )
    finally:
        knowledge_tool.current_workspace.reset(token)

    assert result.is_error is False
    assert "上传成功：1 个" in result.output
    assert uploads[0]["user_id"] == "local_default"
    assert uploads[0]["kb_id"] == "kb-new"
    assert uploads[0]["filename"] == "notes.md"
    assert uploads[0]["file_bytes"] == source_file.read_bytes()
    assert uploads[0]["extraction_mode"] == "enhanced"
    assert uploads[0]["embedding_model"] == "embedding-x"
    assert uploads[0]["chunk_size"] == 256
    assert uploads[0]["chunk_overlap"] == 32
    assert uploads[0]["search_mode"] == "hybrid"


@pytest.mark.asyncio
async def test_list_knowledge_base_documents_tool_returns_doc_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = knowledge_tool.ListKnowledgeBaseDocuments()
    tool._kb_service = SimpleNamespace(
        get_knowledge_base=lambda user_id, kb_id: SimpleNamespace(id=kb_id, name="项目资料库"),
        list_documents=lambda user_id, kb_id, skip=0, limit=100: [
            SimpleNamespace(
                id="doc-1",
                knowledge_base_id=kb_id,
                filename="notes.md",
                file_type="md",
                file_size=120,
                status="completed",
                chunk_count=3,
                error_message=None,
                created_at="2026-05-20T00:00:00",
                updated_at="2026-05-20T00:00:00",
                model_dump=lambda *args, **kwargs: {
                    "id": "doc-1",
                    "knowledge_base_id": kb_id,
                    "filename": "notes.md",
                    "status": "completed",
                    "chunk_count": 3,
                },
            ),
            SimpleNamespace(
                id="doc-2",
                knowledge_base_id=kb_id,
                filename="broken.pdf",
                file_type="pdf",
                file_size=240,
                status="failed",
                chunk_count=0,
                error_message="解析失败",
                created_at="2026-05-20T00:00:00",
                updated_at="2026-05-20T00:00:00",
                model_dump=lambda *args, **kwargs: {
                    "id": "doc-2",
                    "knowledge_base_id": kb_id,
                    "filename": "broken.pdf",
                    "status": "failed",
                    "chunk_count": 0,
                },
            ),
        ],
    )
    monkeypatch.setattr(knowledge_tool, "_resolve_current_user_id", lambda: "local_default")

    result = await tool.invoke(base_id="kb-new", status="completed")

    assert result.is_error is False
    assert "document_id: doc-1" in result.output
    assert "notes.md" in result.output
    assert "doc-2" not in result.output


@pytest.mark.asyncio
async def test_delete_documents_from_knowledge_base_tool_batches_doc_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted = []
    tool = knowledge_tool.DeleteDocumentsFromKnowledgeBase()
    tool._kb_service = SimpleNamespace(
        get_knowledge_base=lambda user_id, kb_id: SimpleNamespace(id=kb_id, name="项目资料库"),
        delete_document=lambda user_id, kb_id, doc_id: deleted.append(
            (user_id, kb_id, doc_id)
        )
        or doc_id != "missing-doc",
    )
    monkeypatch.setattr(knowledge_tool, "_resolve_current_user_id", lambda: "local_default")

    result = await tool.invoke(
        base_id="kb-new",
        doc_ids=["doc-1", "missing-doc"],
    )

    assert result.is_error is True
    assert "已删除文档：1 个" in result.output
    assert "未删除文档：1 个" in result.output
    assert deleted == [
        ("local_default", "kb-new", "doc-1"),
        ("local_default", "kb-new", "missing-doc"),
    ]


@pytest.mark.asyncio
async def test_delete_knowledge_base_tool_wraps_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted = []
    tool = knowledge_tool.DeleteKnowledgeBase()
    tool._kb_service = SimpleNamespace(
        delete_knowledge_base=lambda user_id, kb_id: deleted.append((user_id, kb_id))
        or True
    )
    monkeypatch.setattr(knowledge_tool, "_resolve_current_user_id", lambda: "local_default")

    result = await tool.invoke(base_id="kb-new")

    assert result.is_error is False
    assert "知识库已删除：kb-new" in result.output
    assert deleted == [("local_default", "kb-new")]


@pytest.mark.asyncio
async def test_graph_entity_search_tool_uses_all_mounted_graphs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(graphrag_tool, "resolve_mounted_knowledge_graph_ids", lambda: ["graph-a", "graph-b"])

    services = {
        "graph-a": SimpleNamespace(
            search=lambda query, entity_type=None: [
                {"name": "Alpha", "entity_type": "concept", "description": "from graph-a"}
            ]
        ),
        "graph-b": SimpleNamespace(
            search=lambda query, entity_type=None: [
                {"name": "Beta", "entity_type": "concept", "description": "from graph-b"}
            ]
        ),
    }
    monkeypatch.setattr(
        graphrag_tool,
        "get_graphrag_service_for_tools",
        lambda graph_id="system": services[graph_id],
    )

    tool = graphrag_tool.SearchKnowledgeGraphEntities()
    result = await tool.invoke(
        **graphrag_tool.GraphEntitySearchParams(
            query="概念",
            limit=5,
        ).model_dump()
    )

    assert "图谱: graph-a" in result.output
    assert "图谱: graph-b" in result.output


@pytest.mark.asyncio
async def test_list_knowledge_graphs_tool_uses_current_user_when_listing_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_user_ids: list[str] = []

    monkeypatch.setattr(graphrag_tool, "resolve_mounted_knowledge_graph_ids", lambda: [])

    class FakeGraphStore:
        @classmethod
        def list_graphs(cls, user_id: str):
            captured_user_ids.append(user_id)
            return [{"kg_id": "graph-user"}]

    class FakeGraphService:
        def get_statistics(self):
            return {"entity_count": 2, "relation_count": 1, "document_count": 1}

    monkeypatch.setattr(graphrag_tool, "SQLiteGraphStore", FakeGraphStore)
    monkeypatch.setattr(
        graphrag_tool,
        "get_graphrag_service_for_tools",
        lambda graph_id="system": FakeGraphService(),
    )

    tool = graphrag_tool.ListKnowledgeGraphs()
    token = graphrag_tool.current_user_id.set("user-graph")
    try:
        result = await tool.invoke(
            **graphrag_tool.ListKnowledgeGraphsParams(scope="all").model_dump()
        )
    finally:
        graphrag_tool.current_user_id.reset(token)

    assert result.is_error is False
    assert captured_user_ids == ["user-graph"]
    assert "graph-user" in result.output


@pytest.mark.asyncio
async def test_create_and_delete_knowledge_graph_tools_manage_global_graph(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core import config as config_module
    from app.graphrag.core import sqlite_graph_store

    # 设置 WORKSPACE_DIR 到 tmp_path，图谱自动创建在正确路径下
    monkeypatch.setattr(config_module, "WORKSPACE_DIR", tmp_path)
    # 设置 current_workspace 上下文，让 _resolve_graph_workspace_root 能找到工作区
    workspace_dir = tmp_path / "user-graph-crud" / "test-ws"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / ".aiasys").mkdir()
    monkeypatch.setattr(
        graphrag_tool,
        "_resolve_graph_workspace_root",
        lambda scope: workspace_dir,
    )

    token_uid = graphrag_tool.current_user_id.set("user-graph-crud")
    try:
        create_tool = graphrag_tool.CreateKnowledgeGraph()
        create_result = await create_tool.invoke(
            **graphrag_tool.CreateKnowledgeGraphParams(
                graph_id="project-notes",
                name="项目笔记",
                description="手工维护的项目图谱",
            ).model_dump()
        )

        graphs = sqlite_graph_store.SQLiteGraphStore.list_graphs("user-graph-crud")

        duplicate_result = await create_tool.invoke(
            **graphrag_tool.CreateKnowledgeGraphParams(
                graph_id="project-notes",
            ).model_dump()
        )

        delete_tool = graphrag_tool.DeleteKnowledgeGraph()
        delete_result = await delete_tool.invoke(
            **graphrag_tool.DeleteKnowledgeGraphParams(
                graph_id="project-notes",
            ).model_dump()
        )
        # 图谱应该创建在 tmp_path 下的某个工作区里，通过 scan 找到
        db_files = sqlite_graph_store.SQLiteGraphStore._scan_graph_dirs(
            "user-graph-crud"
        )
        graph_path = db_files[0] if db_files else tmp_path / "__nonexistent__"
    finally:
        graphrag_tool.current_user_id.reset(token_uid)

    assert create_result.is_error is False
    assert "知识图谱创建成功：项目笔记" in create_result.output
    assert graphs == [
        {
            "kg_id": "project-notes",
            "name": "项目笔记",
            "description": "手工维护的项目图谱",
            "entity_count": 0,
            "relation_count": 0,
            "document_count": 0,
        }
    ]
    assert duplicate_result.is_error is True
    assert "知识图谱已存在：project-notes" in duplicate_result.output
    assert delete_result.is_error is False
    assert "知识图谱已删除：project-notes" in delete_result.output
    assert not graph_path.exists()


@pytest.mark.asyncio
async def test_graphrag_entity_and_relation_tools_manage_sqlite_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.graphrag.core import SQLiteGraphStore
    from app.graphrag.service import GraphRAGService

    store = SQLiteGraphStore(
        user_id="local_default",
        kg_id="graph-crud",
        db_path=tmp_path / "graph-crud.db",
    )
    service = GraphRAGService(
        kb_id="graph-crud",
        auto_init_llm=False,
        graph_store=store,
    )
    monkeypatch.setattr(
        graphrag_tool,
        "get_graphrag_service_for_tools",
        lambda graph_id="system", **_kwargs: service,
    )

    create_entity_tool = graphrag_tool.CreateGraphEntity()
    first_result = await create_entity_tool.invoke(
        **graphrag_tool.CreateGraphEntityParams(
            base_id="graph-crud",
            name="实体A",
            entity_type="concept",
            description="原始描述",
            properties={"source": "manual"},
        ).model_dump()
    )
    second_result = await create_entity_tool.invoke(
        **graphrag_tool.CreateGraphEntityParams(
            base_id="graph-crud",
            name="实体B",
            entity_type="concept",
            description="目标实体",
        ).model_dump()
    )

    entity_a = store.get_entity("实体A")
    assert entity_a is not None

    update_result = await graphrag_tool.UpdateGraphEntity().invoke(
        **graphrag_tool.UpdateGraphEntityParams(
            base_id="graph-crud",
            entity_id=str(entity_a["entity_id"]),
            description="更新后的描述",
            properties={"source": "tool"},
        ).model_dump()
    )
    relation_result = await graphrag_tool.CreateGraphRelation().invoke(
        **graphrag_tool.CreateGraphRelationParams(
            base_id="graph-crud",
            source_entity_id="实体A",
            target_entity_id="实体B",
            relation_type="depends_on",
            description="实体A 依赖实体B",
            strength=2.5,
            properties={"evidence": "unit-test"},
        ).model_dump()
    )
    delete_result = await graphrag_tool.DeleteGraphEntity().invoke(
        **graphrag_tool.DeleteGraphEntityParams(
            base_id="graph-crud",
            entity_id="实体B",
        ).model_dump()
    )

    updated_entity = store.get_entity("实体A")
    _, relations = store.get_entity_relations("实体A")

    assert first_result.is_error is False
    assert "已创建实体" in first_result.output
    assert second_result.is_error is False
    assert update_result.is_error is False
    assert "更新后的描述" in update_result.output
    assert updated_entity is not None
    assert updated_entity["description"] == "更新后的描述"
    assert updated_entity["properties"] == {"source": "tool"}
    assert relation_result.is_error is False
    assert "类型: depends_on" in relation_result.output
    assert delete_result.is_error is False
    assert "同步删除关系数: 1" in delete_result.output
    assert store.get_entity("实体B") is None
    assert relations == []


@pytest.mark.asyncio
async def test_graphrag_query_entity_relations_tool_returns_filtered_relations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.graphrag.core import SQLiteGraphStore
    from app.graphrag.service import GraphRAGService

    store = SQLiteGraphStore(
        user_id="local_default",
        kg_id="graph-relations",
        db_path=tmp_path / "graph-relations.db",
    )
    await store.add_subgraph(
        doc_id="doc-1",
        entities=[
            Entity(entity_id="e-a", name="实体A", entity_type="concept", description="A"),
            Entity(entity_id="e-b", name="实体B", entity_type="concept", description="B"),
            Entity(entity_id="e-c", name="实体C", entity_type="concept", description="C"),
        ],
        relations=[
            Relation(
                relation_id="r-ab",
                source_entity="e-a",
                target_entity="e-b",
                description="依赖实体B",
                strength=8,
            ),
            Relation(
                relation_id="r-ca",
                source_entity="e-c",
                target_entity="e-a",
                description="引用实体A",
                strength=4,
            ),
        ],
    )
    service = GraphRAGService(
        kb_id="graph-relations",
        auto_init_llm=False,
        graph_store=store,
    )
    monkeypatch.setattr(
        graphrag_tool,
        "get_graphrag_service_for_tools",
        lambda graph_id="system", **_kwargs: service,
    )

    tool = graphrag_tool.QueryEntityRelations()
    result = await tool.invoke(
        **graphrag_tool.EntityRelationsParams(
            base_id="graph-relations",
            entity_name="实体A",
            direction="outgoing",
        ).model_dump()
    )

    assert result.is_error is False
    assert "实体A -> 实体B" in result.output
    assert "实体C -> 实体A" not in result.output


@pytest.mark.asyncio
async def test_graphrag_get_community_report_tool_filters_community(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeGraphService:
        def get_communities(self, level: int = 0):
            assert level == 0
            return [
                {
                    "community_id": "c-1",
                    "size": 2,
                    "weight": 0.8,
                    "entity_types": {"concept": 2},
                    "key_entities": ["实体A", "实体B"],
                },
                {
                    "community_id": "c-2",
                    "size": 1,
                    "weight": 0.2,
                    "entity_types": {"person": 1},
                    "key_entities": ["实体C"],
                },
            ]

        async def build_community_reports(self, level: int = 0):
            assert level == 0
            return {"c-1": "社区 c-1 报告"}

    monkeypatch.setattr(
        graphrag_tool,
        "get_graphrag_service_for_tools",
        lambda graph_id="system", **_kwargs: FakeGraphService(),
    )

    tool = graphrag_tool.GetCommunityReport()
    result = await tool.invoke(
        **graphrag_tool.CommunityReportParams(
            base_id="graph-community",
            community_id="c-1",
        ).model_dump()
    )

    assert result.is_error is False
    assert "社区 c-1 报告" in result.output
    assert "实体A" in result.output
    assert "c-2" not in result.output


@pytest.mark.asyncio
async def test_graphrag_upload_documents_to_graph_tool_reads_workspace_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    document_path = workspace / "notes.md"
    document_path.write_text("# 图谱文档\n实体A 依赖 实体B", encoding="utf-8")
    calls: list[dict[str, object]] = []

    class FakeGraphService:
        async def add_document_from_file(
            self,
            *,
            filename: str,
            file_bytes: bytes,
            extraction_mode: str | None = None,
            doc_id: str | None = None,
            resolve_entities: bool = True,
        ):
            calls.append(
                {
                    "filename": filename,
                    "file_bytes": file_bytes,
                    "extraction_mode": extraction_mode,
                    "doc_id": doc_id,
                    "resolve_entities": resolve_entities,
                }
            )
            return {
                "doc_id": doc_id or "doc-generated",
                "entity_count": 2,
                "relation_count": 1,
                "token_count": 12,
                "merged_entities": 0,
                "filename": filename,
                "file_type": "markdown",
                "extraction_mode": extraction_mode or "enhanced",
                "requested_mode": extraction_mode or "enhanced",
                "warnings": [],
                "text_length": 12,
            }

    monkeypatch.setattr(
        graphrag_tool,
        "get_graphrag_service_for_tools",
        lambda graph_id="system", **_kwargs: FakeGraphService(),
    )
    token = knowledge_tool.current_workspace.set(str(workspace))
    try:
        tool = graphrag_tool.UploadDocumentsToGraph()
        result = await tool.invoke(
            **graphrag_tool.UploadDocumentsToGraphParams(
                base_id="graph-upload",
                files=["notes.md"],
                doc_id_prefix="batch",
                extraction_mode="basic",
                resolve_entities=False,
            ).model_dump()
        )
    finally:
        knowledge_tool.current_workspace.reset(token)

    assert result.is_error is False
    assert "成功导入 1 个文件" in result.output
    assert calls == [
        {
            "filename": "notes.md",
            "file_bytes": document_path.read_bytes(),
            "extraction_mode": "basic",
            "doc_id": "batch-1",
            "resolve_entities": False,
        }
    ]
