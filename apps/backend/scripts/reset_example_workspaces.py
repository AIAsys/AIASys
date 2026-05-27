#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import networkx as nx
import yaml


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_WORKSPACES_ROOT = BACKEND_ROOT / "data" / "workspaces"
DEFAULT_GRAPHS_ROOT = BACKEND_ROOT / "data" / "graphs"
LEGACY_EXAMPLE_KNOWLEDGE_BASE_ID = "304efd6d-77b3-4eee-8a88-650749261254"
MANAGED_KNOWLEDGE_BASE_IDS = (
    "kb-workspace-config-demo",
    "kb-preview-artifacts-demo",
    LEGACY_EXAMPLE_KNOWLEDGE_BASE_ID,
)
MANAGED_GRAPH_IDS = (
    "graph-workspace-governance-demo",
    "graph-preview-delivery-demo",
)

MANAGED_WORKSPACE_IDS = (
    "example-code-refactor",
    "example-finance-review",
    "example-paper-reading",
)
MANAGED_SESSION_IDS = (
    "refactor-main",
    "refactor-preview",
    "finance-main",
    "finance-risk-followup",
    "paper-reading-main",
    "paper-reading-translate",
)

DEFAULT_KNOWLEDGE_BASES = {
    "version": 1,
    "knowledge_base_ids": [],
}
DEFAULT_KNOWLEDGE_GRAPHS = {
    "version": 1,
    "knowledge_graph_ids": [],
    "primary_knowledge_graph_id": None,
}
DEFAULT_SAMPLE_PDF = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 64 >>
stream
BT
/F1 18 Tf
36 92 Td
(AIASys PDF Example) Tj
36 -28 Td
(Config Folder Demo) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000241 00000 n 
0000000355 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
425
%%EOF
"""


@dataclass(frozen=True)
class WorkspaceSeed:
    workspace_id: str
    title: str
    description: str
    mode: str
    current_session_id: str
    conversations: list[dict[str, Any]]
    files: dict[str, str]
    config_files: dict[str, Any]


@dataclass(frozen=True)
class SessionSeed:
    session_id: str
    title: str
    mode: str
    history: list[dict[str, Any]]


@dataclass(frozen=True)
class KnowledgeBaseDocumentSeed:
    document_id: str
    filename: str
    content: str


@dataclass(frozen=True)
class KnowledgeBaseSeed:
    knowledge_base_id: str
    name: str
    description: str
    embedding_model: str
    documents: list[KnowledgeBaseDocumentSeed]


@dataclass(frozen=True)
class GraphNodeSeed:
    node_id: str
    entity_type: str
    description: str


@dataclass(frozen=True)
class GraphEdgeSeed:
    source: str
    target: str
    description: str
    strength: float = 1.0


@dataclass(frozen=True)
class KnowledgeGraphSeed:
    graph_id: str
    nodes: list[GraphNodeSeed]
    edges: list[GraphEdgeSeed]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def load_json_if_exists(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_yaml_if_exists(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or default
    except Exception:
        return default


def preserve_config_snapshot(user_dir: Path, workspace_id: str) -> dict[str, Any]:
    workspace_dir = user_dir / workspace_id
    config_dir = workspace_dir / ".aiasys"
    workspace_asset_dir = workspace_dir / "workspace"
    return {
        "mcp": load_yaml_if_exists(config_dir / "mcp_config.json", {"version": 1, "servers": {}}),
        "sample_pdf": (
            (workspace_asset_dir / "sample-preview.pdf").read_bytes()
            if (workspace_asset_dir / "sample-preview.pdf").exists()
            else DEFAULT_SAMPLE_PDF
        ),
    }


def build_example_knowledge_base_seeds() -> list[KnowledgeBaseSeed]:
    return [
        KnowledgeBaseSeed(
            knowledge_base_id="kb-workspace-config-demo",
            name="工作区配置说明库",
            description="用于验证工作区级知识库挂载、切换和详情浏览。",
            embedding_model="text-embedding-3-small",
            documents=[
                KnowledgeBaseDocumentSeed(
                    document_id="doc-kb-config-overview",
                    filename="workspace-config-overview.md",
                    content=(
                        "# 工作区配置总览\n\n"
                        ".aiasys/ 目录下集中放置工作区级 MCP、知识库和知识图谱挂载文件。"
                    ),
                ),
                KnowledgeBaseDocumentSeed(
                    document_id="doc-kb-config-mounts",
                    filename="workspace-mount-policy.md",
                    content=(
                        "# 挂载策略\n\n"
                        "同一个工作区可以挂载多个知识库与多个知识图谱，主资源只负责默认执行入口。"
                    ),
                ),
            ],
        ),
        KnowledgeBaseSeed(
            knowledge_base_id="kb-preview-artifacts-demo",
            name="产物预览验收库",
            description="用于验证 PDF 预览、工作区产物和知识库切换联动。",
            embedding_model="text-embedding-3-small",
            documents=[
                KnowledgeBaseDocumentSeed(
                    document_id="doc-kb-preview-pdf",
                    filename="pdf-preview-checklist.md",
                    content=(
                        "# PDF 预览检查单\n\n"
                        "标题卡片、内嵌预览、全屏预览和下载入口需要保持语义一致。"
                    ),
                ),
                KnowledgeBaseDocumentSeed(
                    document_id="doc-kb-preview-assets",
                    filename="artifact-preview-notes.md",
                    content=(
                        "# 产物预览说明\n\n"
                        "工作区资产继续在右侧承接，重型对象通过独立路由或主画布查看。"
                    ),
                ),
            ],
        ),
    ]


def build_example_knowledge_graph_seeds() -> list[KnowledgeGraphSeed]:
    return [
        KnowledgeGraphSeed(
            graph_id="graph-workspace-governance-demo",
            nodes=[
                GraphNodeSeed("工作区", "concept", "长期任务的一等对象。"),
                GraphNodeSeed("会话", "concept", "工作区内部的对话上下文。"),
                GraphNodeSeed("config目录", "technology", "工作区配置资产的统一目录。"),
                GraphNodeSeed("知识库挂载", "event", "当前任务挂载知识库资源。"),
                GraphNodeSeed("知识图谱挂载", "event", "当前任务挂载知识图谱资源。"),
                GraphNodeSeed("工作区配置页", "product", "配置任务级资源与默认执行入口。"),
            ],
            edges=[
                GraphEdgeSeed("工作区", "会话", "工作区包含多个会话", 1.0),
                GraphEdgeSeed("工作区", "config目录", "配置资产落在 config 目录", 0.9),
                GraphEdgeSeed("工作区配置页", "知识库挂载", "可配置知识库挂载", 0.8),
                GraphEdgeSeed("工作区配置页", "知识图谱挂载", "可配置知识图谱挂载", 0.8),
                GraphEdgeSeed("知识库挂载", "工作区", "挂载结果服务于当前任务", 0.7),
                GraphEdgeSeed("知识图谱挂载", "工作区", "挂载结果服务于当前任务", 0.7),
            ],
        ),
        KnowledgeGraphSeed(
            graph_id="graph-preview-delivery-demo",
            nodes=[
                GraphNodeSeed("PDF预览", "product", "支持标题卡片、内嵌预览和全屏预览。"),
                GraphNodeSeed("主画布", "technology", "用于承接重型对象预览。"),
                GraphNodeSeed("右侧边栏", "product", "默认承接当前任务工作区。"),
                GraphNodeSeed("工作区资产", "concept", "文件、配置、产物的统一入口。"),
                GraphNodeSeed("下载入口", "event", "原文件下载保持附件语义。"),
                GraphNodeSeed("知识路由页", "product", "知识库和知识图谱独立路由页。"),
                GraphNodeSeed("切换验收", "event", "验证多资源切换与挂载。"),
            ],
            edges=[
                GraphEdgeSeed("PDF预览", "主画布", "重型预览可进入主画布", 0.9),
                GraphEdgeSeed("右侧边栏", "工作区资产", "右侧默认承接工作区资产", 1.0),
                GraphEdgeSeed("下载入口", "PDF预览", "下载保持独立语义", 0.7),
                GraphEdgeSeed("知识路由页", "切换验收", "通过独立路由验证切换", 0.8),
                GraphEdgeSeed("工作区资产", "知识路由页", "资源页与知识路由页互补", 0.6),
                GraphEdgeSeed("切换验收", "PDF预览", "同轮验收预览与资源切换", 0.5),
            ],
        ),
    ]


def generate_example_mount_config(workspace_id: str) -> dict[str, dict[str, Any]]:
    if workspace_id == "example-code-refactor":
        return {
            "knowledge_bases": {
                "version": 1,
                "knowledge_base_ids": [
                    "kb-workspace-config-demo",
                    "kb-preview-artifacts-demo",
                ],
            },
            "knowledge_graphs": {
                "version": 1,
                "knowledge_graph_ids": [
                    "graph-workspace-governance-demo",
                    "graph-preview-delivery-demo",
                ],
                "primary_knowledge_graph_id": "graph-workspace-governance-demo",
            },
        }
    if workspace_id == "example-finance-review":
        return {
            "knowledge_bases": {
                "version": 1,
                "knowledge_base_ids": ["kb-preview-artifacts-demo"],
            },
            "knowledge_graphs": {
                "version": 1,
                "knowledge_graph_ids": ["graph-preview-delivery-demo"],
                "primary_knowledge_graph_id": "graph-preview-delivery-demo",
            },
        }
    if workspace_id == "example-paper-reading":
        return {
            "knowledge_bases": {
                "version": 1,
                "knowledge_base_ids": ["kb-workspace-config-demo"],
            },
            "knowledge_graphs": {
                "version": 1,
                "knowledge_graph_ids": ["graph-workspace-governance-demo"],
                "primary_knowledge_graph_id": "graph-workspace-governance-demo",
            },
        }
    return {
        "knowledge_bases": DEFAULT_KNOWLEDGE_BASES,
        "knowledge_graphs": DEFAULT_KNOWLEDGE_GRAPHS,
    }


def build_workspace_seeds(preserved: dict[str, dict[str, Any]], timestamp: str) -> list[WorkspaceSeed]:
    return [
        WorkspaceSeed(
            workspace_id="example-code-refactor",
            title="示例：代码重构工作区",
            description="用于演示需求梳理、PDF 产物预览和 config 配置收口。",
            mode="analysis",
            current_session_id="refactor-preview",
            conversations=[
                {
                    "conversation_id": "refactor-preview",
                    "session_id": "refactor-preview",
                    "title": "会话：PDF 预览验收",
                    "mode": "analysis",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "branched_from_conversation_id": "refactor-main",
                },
                {
                    "conversation_id": "refactor-main",
                    "session_id": "refactor-main",
                    "title": "主对话：需求与现状",
                    "mode": "analysis",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "branched_from_conversation_id": None,
                },
            ],
            files={
                "refactor-checklist.md": "# 重构清单\n\n- 对齐工作区 / 会话语义\n- 收口 `config/` 下的配置资产\n- 验证 PDF 产物预览\n- 跑构建和定向回归测试\n",
                "notes/todo.txt": "1. 盘点工作区当前资产\n2. 检查 config 目录里的 MCP / 知识配置\n3. 复核 PDF 预览和下载入口\n4. 验证 2 个知识库与 2 个知识图谱的切换\n",
            },
            config_files={
                "mcp_config.json": preserved["example-code-refactor"]["mcp"],
                "knowledge-bases.json": generate_example_mount_config("example-code-refactor")[
                    "knowledge_bases"
                ],
                "knowledge-graphs.json": generate_example_mount_config("example-code-refactor")[
                    "knowledge_graphs"
                ],
            },
        ),
        WorkspaceSeed(
            workspace_id="example-finance-review",
            title="示例：财报分析工作区",
            description="用于演示财报问答、指标拆解和风险追问。",
            mode="analysis",
            current_session_id="finance-main",
            conversations=[
                {
                    "conversation_id": "finance-main",
                    "session_id": "finance-main",
                    "title": "主对话：收入与利润拆解",
                    "mode": "analysis",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "branched_from_conversation_id": None,
                },
                {
                    "conversation_id": "finance-risk-followup",
                    "session_id": "finance-risk-followup",
                    "title": "会话：风险追问",
                    "mode": "analysis",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "branched_from_conversation_id": "finance-main",
                },
            ],
            files={
                "quarterly-summary.md": "# 财报摘要\n\n- 收入同比 +18%\n- 毛利率 42.1%\n- 销售费用率上升 2.3pct\n",
                "metrics.csv": "metric,value\nrevenue_growth,0.18\ngross_margin,0.421\nsales_expense_ratio,0.153\n",
            },
            config_files={
                "mcp_config.json": preserved["example-finance-review"]["mcp"],
                "knowledge-bases.json": generate_example_mount_config("example-finance-review")[
                    "knowledge_bases"
                ],
                "knowledge-graphs.json": generate_example_mount_config("example-finance-review")[
                    "knowledge_graphs"
                ],
            },
        ),
        WorkspaceSeed(
            workspace_id="example-paper-reading",
            title="示例：论文阅读工作区",
            description="用于演示论文阅读、问答、术语翻译和笔记整理的任务工作区。",
            mode="research",
            current_session_id="paper-reading-main",
            conversations=[
                {
                    "conversation_id": "paper-reading-main",
                    "session_id": "paper-reading-main",
                    "title": "主对话：阅读与提问",
                    "mode": "research",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "branched_from_conversation_id": None,
                },
                {
                    "conversation_id": "paper-reading-translate",
                    "session_id": "paper-reading-translate",
                    "title": "会话：术语翻译",
                    "mode": "research",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "branched_from_conversation_id": "paper-reading-main",
                },
            ],
            files={
                "paper-notes.md": "# 论文笔记\n\n- 研究问题：多模态检索中的对齐问题\n- 方法：双塔编码 + rerank\n- 结论：在长文场景下显著提升\n",
                "reading-plan.txt": "1. 读摘要\n2. 看方法图\n3. 抽实验结论\n4. 记录问题\n",
            },
            config_files={
                "mcp_config.json": preserved["example-paper-reading"]["mcp"],
                "knowledge-bases.json": generate_example_mount_config("example-paper-reading")[
                    "knowledge_bases"
                ],
                "knowledge-graphs.json": generate_example_mount_config("example-paper-reading")[
                    "knowledge_graphs"
                ],
            },
        ),
    ]


def build_session_seeds(timestamp: str) -> list[SessionSeed]:
    return [
        SessionSeed(
            session_id="refactor-main",
            title="主对话：需求与现状",
            mode="analysis",
            history=[
                {
                    "role": "user",
                    "content": "先帮我梳理这个工作区当前的目标、现状和接下来三步。",
                    "timestamp": timestamp,
                    "metadata": {},
                    "file_snapshot": None,
                },
                {
                    "role": "assistant",
                    "content": "可以。我会先整理目标与约束，再盘点当前资产，并给出下一步重构计划。",
                    "timestamp": timestamp,
                    "metadata": {},
                    "file_snapshot": None,
                },
            ],
        ),
        SessionSeed(
            session_id="refactor-preview",
            title="会话：PDF 预览验收",
            mode="analysis",
            history=[
                {
                    "role": "user",
                    "content": "给我确认一下 PDF 产物预览和 config 目录结构现在是不是已经收口了。",
                    "timestamp": timestamp,
                    "metadata": {},
                    "file_snapshot": None,
                },
                {
                    "role": "assistant",
                    "content": "这里是一个最新的 PDF 产物示例。\n\n![PDF 预览](/workspace/sample-preview.pdf)\n\n你可以继续检查 `.aiasys/knowledge-bases.json`、`.aiasys/knowledge-graphs.json` 和 `.aiasys/mcp_config.json`。当前示例还额外挂载了 2 个知识库和 2 个知识图谱，方便直接测试切换。",
                    "timestamp": timestamp,
                    "metadata": {},
                    "file_snapshot": None,
                },
            ],
        ),
        SessionSeed(
            session_id="finance-main",
            title="主对话：收入与利润拆解",
            mode="analysis",
            history=[
                {
                    "role": "user",
                    "content": "先从收入增速、毛利率和费用率三个角度拆一下这份财报。",
                    "timestamp": timestamp,
                    "metadata": {},
                    "file_snapshot": None,
                },
                {
                    "role": "assistant",
                    "content": "可以。我会先给出三段式摘要，再标注需要继续深挖的异常项。",
                    "timestamp": timestamp,
                    "metadata": {},
                    "file_snapshot": None,
                },
            ],
        ),
        SessionSeed(
            session_id="finance-risk-followup",
            title="会话：风险追问",
            mode="analysis",
            history=[
                {
                    "role": "user",
                    "content": "继续追一下费用率上升是不是一次性因素。",
                    "timestamp": timestamp,
                    "metadata": {},
                    "file_snapshot": None,
                },
                {
                    "role": "assistant",
                    "content": "可以，我会优先找管理层解释、促销活动和渠道变动三个方向。",
                    "timestamp": timestamp,
                    "metadata": {},
                    "file_snapshot": None,
                },
            ],
        ),
        SessionSeed(
            session_id="paper-reading-main",
            title="主对话：阅读与提问",
            mode="research",
            history=[
                {
                    "role": "user",
                    "content": "请先帮我梳理这篇论文的研究问题、方法和主要结论。",
                    "timestamp": timestamp,
                    "metadata": {},
                    "file_snapshot": None,
                },
                {
                    "role": "assistant",
                    "content": "可以。我会先提炼论文问题定义，再拆成方法框架、实验设置和结论三部分来整理。",
                    "timestamp": timestamp,
                    "metadata": {},
                    "file_snapshot": None,
                },
            ],
        ),
        SessionSeed(
            session_id="paper-reading-translate",
            title="会话：术语翻译",
            mode="research",
            history=[
                {
                    "role": "user",
                    "content": "把 introduction 里的关键术语翻成中文，并保留英文原词。",
                    "timestamp": timestamp,
                    "metadata": {},
                    "file_snapshot": None,
                },
                {
                    "role": "assistant",
                    "content": "可以，我会输出双语术语表，优先保留论文原词。",
                    "timestamp": timestamp,
                    "metadata": {},
                    "file_snapshot": None,
                },
            ],
        ),
    ]


def build_session_metadata(seed: SessionSeed, timestamp: str) -> dict[str, Any]:
    return {
        "session_id": seed.session_id,
        "title": seed.title,
        "created_at": timestamp,
        "updated_at": timestamp,
        "message_count": len(seed.history),
        "agent_type": "analysis",
        "status": "active",
        "completed_at": None,
        "completed_message_count": None,
        "tags": [],
        "env_id": None,
        "sandbox_mode": None,
        "recovery_policy": "journal_only",
        "code_timeout": None,
        "mode": seed.mode,
        "session_role": None,
        "task_id": None,
        "task_title": None,
        "exclude_from_user_history": False,
        "project_id": None,
        "team_id": None,
        "bound_lead_session_id": None,
    }


def build_execution_index(session_id: str, timestamp: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "last_sequence": 0,
        "last_record_id": None,
        "last_status": None,
        "total_records": 0,
        "updated_at": timestamp,
    }


def build_execution_recovery(session_id: str, timestamp: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "recovery_policy": "journal_only",
        "idempotency_policy": "assume_non_idempotent",
        "requires_confirmation_for_replay": True,
        "last_runtime_state": "fresh",
        "last_record_id": None,
        "last_rebuild_status": None,
        "last_replay_run_id": None,
        "last_replayed_sequences": [],
        "last_remaining_sequences": [],
        "last_failed_sequence": None,
        "updated_at": timestamp,
    }


def build_dense_embedding(text: str, dimension: int = 1536) -> list[float]:
    raw = text.encode("utf-8")
    if not raw:
        raw = b" "
    vector = [0.0] * dimension
    for index in range(dimension):
        byte = raw[index % len(raw)]
        vector[index] = byte / 255.0
    return vector


def reset_example_knowledge_bases(user_id: str) -> None:
    import sqlite3

    from app.core.database import (
        Document as DocumentORM,
        DocumentChunk as DocumentChunkORM,
        KnowledgeBase as KnowledgeBaseORM,
        SessionLocal,
        init_db,
    )
    from app.core.sqlite_vec import load_vec_extension

    init_db()
    db = SessionLocal()
    kb_dir = BACKEND_ROOT / "data" / "global_assets" / "knowledge"
    kb_dir.mkdir(parents=True, exist_ok=True)

    try:
        managed_ids = set(MANAGED_KNOWLEDGE_BASE_IDS)
        existing_kbs = (
            db.query(KnowledgeBaseORM)
            .filter(
                KnowledgeBaseORM.user_id == user_id,
                KnowledgeBaseORM.id.in_(managed_ids),
            )
            .all()
        )
        for kb in existing_kbs:
            db.delete(kb)
        db.commit()

        # 删除旧的 sqlite-vec 数据库文件
        for kb_id in managed_ids:
            db_path = kb_dir / f"{kb_id}.db"
            if db_path.exists():
                db_path.unlink()

        timestamp = datetime.utcnow()
        for seed in build_example_knowledge_base_seeds():
            kb = KnowledgeBaseORM(
                id=seed.knowledge_base_id,
                name=seed.name,
                description=seed.description,
                user_id=user_id,
                embedding_model=seed.embedding_model,
                chunk_size=512,
                chunk_overlap=50,
                created_at=timestamp,
                updated_at=timestamp,
            )
            db.add(kb)

            # 初始化 sqlite-vec 数据库
            db_path = kb_dir / f"{seed.knowledge_base_id}.db"
            conn = sqlite3.connect(str(db_path))
            load_vec_extension(conn)

            # 示例 embedding 维度固定为 1536（与 build_dense_embedding 默认值一致）
            dimension = 1536
            conn.execute(f'''
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING vec0(
                    chunk_id TEXT,
                    document_id TEXT,
                    chunk_index INTEGER,
                    meta_json TEXT,
                    embedding float[{dimension}]
                )
            ''')
            conn.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    document_id UNINDEXED,
                    content
                )
            ''')

            for index, document_seed in enumerate(seed.documents, start=1):
                doc = DocumentORM(
                    id=document_seed.document_id,
                    knowledge_base_id=seed.knowledge_base_id,
                    filename=document_seed.filename,
                    file_type=Path(document_seed.filename).suffix.lstrip(".") or "md",
                    file_size=len(document_seed.content.encode("utf-8")),
                    status="completed",
                    chunk_count=1,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                db.add(doc)

                chunk_id = f"{document_seed.document_id}-chunk-1"
                chunk = DocumentChunkORM(
                    id=f"chunk-{document_seed.document_id}",
                    document_id=document_seed.document_id,
                    chunk_index=0,
                    content=document_seed.content,
                    meta_info={
                        "doc_id": document_seed.document_id,
                        "filename": document_seed.filename,
                        "kb_id": seed.knowledge_base_id,
                        "example": True,
                    },
                    chunk_id=chunk_id,
                    created_at=timestamp,
                )
                db.add(chunk)

                embedding = build_dense_embedding(
                    f"{seed.name}:{index}:{document_seed.content}",
                    dimension=dimension,
                )
                meta_json = json.dumps({
                    "doc_id": document_seed.document_id,
                    "filename": document_seed.filename,
                    "kb_id": seed.knowledge_base_id,
                    "example": True,
                })
                conn.execute(
                    "INSERT INTO chunks(chunk_id, document_id, chunk_index, meta_json, embedding) VALUES (?, ?, ?, ?, ?)",
                    [chunk_id, document_seed.document_id, 0, meta_json, json.dumps(embedding)],
                )
                conn.execute(
                    "INSERT INTO chunks_fts(chunk_id, document_id, content) VALUES (?, ?, ?)",
                    [chunk_id, document_seed.document_id, document_seed.content],
                )

            conn.commit()
            conn.close()

        db.commit()
    finally:
        db.close()


def reset_example_knowledge_graphs() -> None:
    graphs_root = DEFAULT_GRAPHS_ROOT
    graphs_root.mkdir(parents=True, exist_ok=True)

    for graph_id in MANAGED_GRAPH_IDS:
        shutil.rmtree(graphs_root / graph_id, ignore_errors=True)

    for seed in build_example_knowledge_graph_seeds():
        graph_dir = graphs_root / seed.graph_id
        graph_dir.mkdir(parents=True, exist_ok=True)
        (graph_dir / "subgraphs").mkdir(exist_ok=True)

        graph = nx.Graph()
        for node in seed.nodes:
            graph.add_node(
                node.node_id,
                entity_id=node.node_id,
                entity_type=node.entity_type,
                description=node.description,
                source_id="example-seed",
                metadata_json=json.dumps({"example": True}, ensure_ascii=False),
            )

        for edge_index, edge in enumerate(seed.edges, start=1):
            graph.add_edge(
                edge.source,
                edge.target,
                relation_id=f"{seed.graph_id}-edge-{edge_index}",
                description=edge.description,
                strength=edge.strength,
                source_id="example-seed",
                metadata_json=json.dumps({"example": True}, ensure_ascii=False),
            )

        nx.write_graphml(graph, graph_dir / "knowledge_graph.graphml")


def reset_example_workspaces(workspaces_root: Path, user_id: str) -> None:
    user_dir = workspaces_root / user_id
    user_dir.mkdir(parents=True, exist_ok=True)

    preserved = {
        workspace_id: preserve_config_snapshot(user_dir, workspace_id)
        for workspace_id in MANAGED_WORKSPACE_IDS
    }
    reset_example_knowledge_bases(user_id)
    reset_example_knowledge_graphs()
    timestamp = now_iso()
    workspace_seeds = build_workspace_seeds(preserved, timestamp)
    session_seeds = build_session_seeds(timestamp)

    for workspace_id in MANAGED_WORKSPACE_IDS:
        shutil.rmtree(user_dir / workspace_id, ignore_errors=True)
    for session_id in MANAGED_SESSION_IDS:
        shutil.rmtree(user_dir / session_id, ignore_errors=True)

    for seed in workspace_seeds:
        workspace_dir = user_dir / seed.workspace_id
        (workspace_dir / ".aiasys" / "workspace").mkdir(parents=True, exist_ok=True)
        (workspace_dir / "workspace").mkdir(parents=True, exist_ok=True)
        (workspace_dir / ".aiasys").mkdir(parents=True, exist_ok=True)
        (workspace_dir / "skills").mkdir(parents=True, exist_ok=True)
        (workspace_dir / "attachments").mkdir(parents=True, exist_ok=True)
        (workspace_dir / "artifacts").mkdir(parents=True, exist_ok=True)
        (workspace_dir / ".aiasys" / "session" / "config").mkdir(parents=True, exist_ok=True)

        write_json(
            workspace_dir / ".aiasys" / "workspace" / "workspace.json",
            {
                "workspace_id": seed.workspace_id,
                "title": seed.title,
                "description": seed.description,
                "mode": seed.mode,
                "status": "active",
                "created_at": timestamp,
                "updated_at": timestamp,
                "current_conversation_id": seed.current_session_id,
            },
        )
        write_json(workspace_dir / ".aiasys" / "workspace" / "conversations.json", seed.conversations)

        for relative_path, content in seed.files.items():
            write_text(workspace_dir / relative_path, content)
        for relative_path, payload in seed.config_files.items():
            target = workspace_dir / ".aiasys" / relative_path
            if target.suffix in {".yaml", ".yml"}:
                write_yaml(target, payload)
            else:
                write_json(target, payload)

        if seed.workspace_id == "example-code-refactor":
            write_bytes(
                workspace_dir / "workspace" / "sample-preview.pdf",
                preserved["example-code-refactor"]["sample_pdf"],
            )

    for seed in session_seeds:
        session_dir = user_dir / seed.session_id
        (session_dir / ".aiasys" / "session" / "_active").mkdir(parents=True, exist_ok=True)
        (session_dir / ".aiasys" / "session" / "execution").mkdir(parents=True, exist_ok=True)

        write_json(session_dir / "metadata.json", build_session_metadata(seed, timestamp))
        write_json(session_dir / ".aiasys" / "session" / "_active" / "history.json", seed.history)
        write_json(
            session_dir / ".aiasys" / "session" / "execution" / "records-index.json",
            build_execution_index(seed.session_id, timestamp),
        )
        write_json(
            session_dir / ".aiasys" / "session" / "execution" / "recovery.json",
            build_execution_recovery(seed.session_id, timestamp),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="重置 AIASys 本地 example 工作区与示例会话。")
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=DEFAULT_WORKSPACES_ROOT,
        help="工作区根目录，默认使用 apps/backend/data/workspaces",
    )
    parser.add_argument(
        "--user-id",
        default="local_default",
        help="要重置示例数据的用户 ID，默认 local_default",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reset_example_workspaces(args.workspace_root, args.user_id)
    print(
        f"Reset example workspaces for {args.user_id} under {args.workspace_root}",
    )


if __name__ == "__main__":
    main()
