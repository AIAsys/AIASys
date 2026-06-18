#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


DEFAULT_USER_ID = "local_default"
DEFAULT_WORKSPACE_ID = "resource-db-smoke"
DEFAULT_SESSION_ID = "resource-db-smoke-main"
RESOURCE_METADATA_TABLE = "_aiasys_metadata"


@dataclass(frozen=True)
class ResourceDbAsset:
    relative_path: Path
    metadata: dict[str, Any]


@dataclass(frozen=True)
class SeedTarget:
    user_id: str
    workspace_id: str | None
    session_id: str | None
    workspace_root: Path


RESOURCE_DB_ASSETS = (
    ResourceDbAsset(
        relative_path=Path("knowledge/product-docs.knowledge.db"),
        metadata={
            "resource_type": "knowledge",
            "schema_kind": "aiasys.knowledge_base.sqlite.v1",
            "preview_kind": "knowledge_base",
            "renderer_hint": "knowledge_base_preview",
            "id": "kb-product-docs",
            "description": "产品文档知识库测试资产",
            "document_count": 3,
            "type": "sqlite",
        },
    ),
    ResourceDbAsset(
        relative_path=Path("graphs/project.graph.db"),
        metadata={
            "resource_type": "graph",
            "schema_kind": "aiasys.knowledge_graph.sqlite.v1",
            "preview_kind": "knowledge_graph",
            "renderer_hint": "knowledge_graph_preview",
            "id": "kg-project",
            "description": "项目资源关系图谱测试资产",
            "entity_count": 3,
            "relation_count": 2,
            "document_count": 1,
            "type": "sqlite",
        },
    ),
    ResourceDbAsset(
        relative_path=Path("databases/workspace.sqlite.db"),
        metadata={
            "resource_type": "database",
            "schema_kind": "aiasys.database.sqlite.v1",
            "preview_kind": "database",
            "renderer_hint": "database_preview",
            "id": "workspace-sqlite",
            "handle": "workspace-sqlite",
            "description": "工作区 SQLite 测试数据库",
            "type": "sqlite",
            "scope": "workspace_asset",
            "meta": {
                "readonly": False,
            },
        },
    ),
)


def encode_metadata_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return str(value)


def write_metadata_table(conn: sqlite3.Connection, metadata: dict[str, Any]) -> None:
    conn.execute(f"DROP TABLE IF EXISTS {RESOURCE_METADATA_TABLE}")
    conn.execute(
        f"""
        CREATE TABLE {RESOURCE_METADATA_TABLE} (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.executemany(
        f"INSERT INTO {RESOURCE_METADATA_TABLE} (key, value) VALUES (?, ?)",
        [(str(key), encode_metadata_value(value)) for key, value in sorted(metadata.items())],
    )


def write_knowledge_db(db_path: Path, metadata: dict[str, Any]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        write_metadata_table(conn, metadata)
        conn.execute(
            """
            CREATE TABLE documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source_path TEXT,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id)
            )
            """
        )
        documents = [
            (
                "doc-resource-tree",
                "资源资产树约定",
                "docs/resource-tree.md",
                "资源型 SQLite 文件优先通过 _aiasys_metadata 声明类型。",
            ),
            (
                "doc-preview-factory",
                "预览工厂约定",
                "docs/preview-factory.md",
                "文件预览工厂根据 resource_type 和 renderer_hint 选择渲染器。",
            ),
            (
                "doc-metadata-priority",
                "metadata 优先级",
                "docs/metadata-priority.md",
                "文件名用于人类识别，metadata 是系统识别资源类型的第一优先级。",
            ),
        ]
        conn.executemany(
            """
            INSERT INTO documents (id, title, source_path, content)
            VALUES (?, ?, ?, ?)
            """,
            documents,
        )
        conn.executemany(
            """
            INSERT INTO chunks (id, document_id, chunk_index, content)
            VALUES (?, ?, ?, ?)
            """,
            [
                (f"chunk-{document_id}-0", document_id, 0, content)
                for document_id, _title, _source_path, content in documents
            ],
        )
        conn.commit()
    finally:
        conn.close()


def write_graph_db(db_path: Path, metadata: dict[str, Any]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        write_metadata_table(conn, metadata)
        conn.execute(
            """
            CREATE TABLE entities (
                entity_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                description TEXT,
                properties TEXT,
                source_doc_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE relations (
                relation_id TEXT PRIMARY KEY,
                source_entity_id TEXT NOT NULL,
                target_entity_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                description TEXT,
                strength REAL DEFAULT 1.0,
                properties TEXT,
                source_doc_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE communities (
                community_id TEXT PRIMARY KEY,
                level INTEGER NOT NULL,
                entity_ids TEXT,
                summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO entities
            (entity_id, name, entity_type, description, properties, source_doc_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "entity-workspace-asset",
                    "工作区资产",
                    "concept",
                    "用户在工作区目录树中看到的文件型资源。",
                    json.dumps({"source": "seed"}, ensure_ascii=False),
                    "doc-resource-tree",
                ),
                (
                    "entity-resource-metadata",
                    "资源 metadata",
                    "contract",
                    "资源型数据库文件里的自描述识别信息。",
                    json.dumps({"source": "seed"}, ensure_ascii=False),
                    "doc-resource-tree",
                ),
                (
                    "entity-preview-renderer",
                    "专用预览器",
                    "frontend",
                    "根据资源类型打开知识库、知识图谱或数据库预览。",
                    json.dumps({"source": "seed"}, ensure_ascii=False),
                    "doc-resource-tree",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO relations
            (
                relation_id,
                source_entity_id,
                target_entity_id,
                relation_type,
                description,
                strength,
                properties,
                source_doc_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "rel-asset-has-metadata",
                    "entity-workspace-asset",
                    "entity-resource-metadata",
                    "has_metadata",
                    "工作区资产通过 metadata 声明资源类型。",
                    1.0,
                    "{}",
                    "doc-resource-tree",
                ),
                (
                    "rel-metadata-selects-renderer",
                    "entity-resource-metadata",
                    "entity-preview-renderer",
                    "selects_renderer",
                    "预览工厂根据 metadata 选择专用预览器。",
                    0.9,
                    "{}",
                    "doc-resource-tree",
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO communities (community_id, level, entity_ids, summary)
            VALUES (?, ?, ?, ?)
            """,
            (
                "community-resource-preview",
                0,
                json.dumps(
                    [
                        "entity-workspace-asset",
                        "entity-resource-metadata",
                        "entity-preview-renderer",
                    ],
                    ensure_ascii=False,
                ),
                "资源型 DB 资产渲染链路",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def write_database_db(db_path: Path, metadata: dict[str, Any]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        write_metadata_table(conn, metadata)
        conn.execute(
            """
            CREATE TABLE sample_metrics (
                name TEXT PRIMARY KEY,
                value REAL NOT NULL,
                unit TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE sample_events (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.executemany(
            "INSERT INTO sample_metrics (name, value, unit) VALUES (?, ?, ?)",
            [
                ("documents", 3, "count"),
                ("entities", 3, "count"),
                ("relations", 2, "count"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO sample_events (id, category, title)
            VALUES (?, ?, ?)
            """,
            [
                ("evt-metadata", "resource", "metadata 优先识别"),
                ("evt-renderer", "preview", "专用预览器打开"),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def write_resource_db_assets(
    workspace_root: Path,
    *,
    overwrite: bool = False,
) -> list[dict[str, Any]]:
    writers = {
        "knowledge": write_knowledge_db,
        "graph": write_graph_db,
        "database": write_database_db,
    }
    results: list[dict[str, Any]] = []

    for asset in RESOURCE_DB_ASSETS:
        db_path = workspace_root / asset.relative_path
        resource_type = str(asset.metadata["resource_type"])
        if db_path.exists() and not overwrite:
            status = "exists"
        else:
            if db_path.exists():
                db_path.unlink()
            writers[resource_type](db_path, dict(asset.metadata))
            status = "created"

        results.append(
            {
                "relative_path": asset.relative_path.as_posix(),
                "path": str(db_path),
                "status": status,
                "metadata": dict(asset.metadata),
            }
        )

    return results


def resolve_or_create_target(
    *,
    user_id: str,
    workspace_id: str | None,
    session_id: str | None,
    create_workspace: bool,
    registry: Any | None = None,
) -> SeedTarget:
    if registry is None:
        from app.services.workspace_registry import get_workspace_registry_service

        registry = get_workspace_registry_service()

    resolved_workspace_id = workspace_id or DEFAULT_WORKSPACE_ID
    resolved_session_id = session_id

    if resolved_session_id:
        existing_workspace_id = registry.find_workspace_id_by_session_id(
            user_id,
            resolved_session_id,
        )
        if existing_workspace_id:
            return SeedTarget(
                user_id=user_id,
                workspace_id=existing_workspace_id,
                session_id=resolved_session_id,
                workspace_root=registry.get_workspace_root(
                    user_id,
                    existing_workspace_id,
                ),
            )

    try:
        workspace = registry.get_workspace(
            user_id,
            resolved_workspace_id,
            include_conversations=True,
        )
    except FileNotFoundError:
        if not create_workspace:
            raise
        workspace = registry.create_workspace(
            user_id=user_id,
            workspace_id=resolved_workspace_id,
            title="资源型 DB metadata smoke",
            description="用于验证工作区资产树中的资源型 SQLite 文件识别与渲染。",
            initial_conversation_id=resolved_session_id or DEFAULT_SESSION_ID,
            initial_conversation_title="资源型 DB 测试会话",
        )

    if resolved_session_id:
        bound_workspace_id = registry.find_workspace_id_by_session_id(
            user_id,
            resolved_session_id,
        )
        if bound_workspace_id is None and create_workspace:
            registry.create_conversation(
                user_id=user_id,
                workspace_id=resolved_workspace_id,
                conversation_id=resolved_session_id,
                title="资源型 DB 测试会话",
                make_current=True,
            )
            bound_workspace_id = resolved_workspace_id
        if bound_workspace_id:
            resolved_workspace_id = bound_workspace_id

    if resolved_session_id is None and workspace.current_conversation is not None:
        resolved_session_id = workspace.current_conversation.session_id

    if resolved_session_id:
        workspace_root = registry.get_logical_workspace_root(
            user_id,
            resolved_session_id,
        )
    else:
        workspace_root = registry.get_workspace_root(user_id, resolved_workspace_id)

    return SeedTarget(
        user_id=user_id,
        workspace_id=resolved_workspace_id,
        session_id=resolved_session_id,
        workspace_root=workspace_root,
    )


def seed_resource_db_test_assets(
    *,
    user_id: str = DEFAULT_USER_ID,
    workspace_id: str | None = DEFAULT_WORKSPACE_ID,
    session_id: str | None = None,
    create_workspace: bool = True,
    overwrite: bool = False,
    registry: Any | None = None,
) -> dict[str, Any]:
    target = resolve_or_create_target(
        user_id=user_id,
        workspace_id=workspace_id,
        session_id=session_id,
        create_workspace=create_workspace,
        registry=registry,
    )
    files = write_resource_db_assets(target.workspace_root, overwrite=overwrite)
    return {
        "user_id": target.user_id,
        "workspace_id": target.workspace_id,
        "session_id": target.session_id,
        "workspace_root": str(target.workspace_root),
        "files": files,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="初始化工作区资源型 SQLite DB 测试资产。",
    )
    parser.add_argument("--user-id", default=DEFAULT_USER_ID)
    parser.add_argument("--workspace-id", default=DEFAULT_WORKSPACE_ID)
    parser.add_argument(
        "--session-id",
        default=None,
        help="指定后优先写入该会话对应的逻辑工作区。",
    )
    parser.add_argument(
        "--no-create-workspace",
        action="store_true",
        help="目标工作区不存在时直接报错。",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="覆盖已存在的测试 DB 文件。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = seed_resource_db_test_assets(
        user_id=args.user_id,
        workspace_id=args.workspace_id,
        session_id=args.session_id,
        create_workspace=not args.no_create_workspace,
        overwrite=args.overwrite,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
