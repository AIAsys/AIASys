"""
SQLite 图存储管理器

将知识图谱的实体和关系存储在 SQLite 中，替代 DuckDB 版本。
每个知识图谱对应一个 SQLite 数据库文件。
"""

import asyncio
import json
import logging
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar

import networkx as nx

from app.core.config import (
    get_user_global_resources_dir,  # 保留用于 _legacy_db_path_for 和 _scan_graph_dirs 兼容旧数据扫描
)
from app.utils.path_utils import as_system_path

from ..models.entity import Entity
from ..models.relation import Relation

logger = logging.getLogger(__name__)

# 合法的 SQL 表名/列名：字母或下划线开头，后跟字母数字下划线
_VALID_SQL_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

_T = TypeVar("_T")


class SQLiteGraphStore:
    """SQLite 知识图谱存储

    存储架构:
    - 实体表: entities
    - 关系表: relations
    - 社区表: communities
    - 元数据表: graph_metadata
    """

    def __init__(self, user_id: str, kg_id: str, db_path: Optional[Path] = None):
        self.user_id = user_id
        self.kg_id = kg_id
        if db_path is None:
            raise ValueError("db_path is required for SQLiteGraphStore")
        self._db_path = db_path
        self._ensure_tables()
        self._nx_graph: Optional[nx.Graph] = None

    @staticmethod
    def _db_path_for(workspace_root: Path, kg_id: str) -> Path:
        """计算图谱 .db 文件在工作区下的路径。"""
        graph_dir = workspace_root / ".aiasys" / "graphs"
        Path(as_system_path(graph_dir)).mkdir(parents=True, exist_ok=True)
        return graph_dir / f"{kg_id}.db"

    @staticmethod
    def _legacy_db_path_for(user_id: str, kg_id: str) -> Path:
        """旧版全局资源路径，用于兼容旧数据。"""
        graph_dir = get_user_global_resources_dir(user_id) / "graphs"
        Path(as_system_path(graph_dir)).mkdir(parents=True, exist_ok=True)
        return graph_dir / f"{kg_id}.db"

    @classmethod
    def find_db_path(
        cls,
        user_id: str,
        kg_id: str,
        *,
        workspace_root: Path | None = None,
        global_workspace_root: Path | None = None,
    ) -> Path | None:
        """在 workspace/global/legacy 三层中查找图谱 .db 文件。"""
        from app.core.config import WORKSPACE_DIR as _WS_DIR

        # 1. 当前工作区
        if workspace_root:
            db_path = cls._db_path_for(workspace_root, kg_id)
            if Path(as_system_path(db_path)).exists():
                return db_path

        # 2. 全局工作区
        if global_workspace_root:
            db_path = cls._db_path_for(global_workspace_root, kg_id)
            if Path(as_system_path(db_path)).exists():
                return db_path

        # 3. 旧全局路径
        legacy = cls._legacy_db_path_for(user_id, kg_id)
        if Path(as_system_path(legacy)).exists():
            return legacy

        # 4. 扫描所有工作区目录
        if user_id:
            user_ws_dir = _WS_DIR / user_id
            if user_ws_dir.exists():
                for ws_dir in sorted(user_ws_dir.iterdir()):
                    if ws_dir.is_dir() and ws_dir.name != "global_workspace":
                        db_path = cls._db_path_for(ws_dir, kg_id)
                        if db_path.exists():
                            return db_path

        return None

    @classmethod
    def _scan_graph_dirs(
        cls,
        user_id: str,
        *,
        workspace_dirs: list[Path] | None = None,
    ) -> list[Path]:
        """扫描所有图谱 .db 文件路径（去重）。

        扫描范围：
        1. workspace_dirs 中指定的工作区目录（.aiasys/graphs/）
        2. 用户所有工作区目录（自动扫描）
        3. 旧全局资源目录（兼容旧数据）
        """
        from app.core.config import WORKSPACE_DIR as _WS_DIR

        search_dirs: list[Path] = []

        if workspace_dirs:
            for ws_root in workspace_dirs:
                search_dirs.append(ws_root / ".aiasys" / "graphs")
        else:
            user_ws_dir = _WS_DIR / user_id
            if user_ws_dir.exists():
                for ws_dir in sorted(user_ws_dir.iterdir()):
                    if ws_dir.is_dir() and ws_dir.name != "global_workspace":
                        search_dirs.append(ws_dir / ".aiasys" / "graphs")
                global_ws = user_ws_dir / "global_workspace"
                if global_ws.exists():
                    search_dirs.append(global_ws / ".aiasys" / "graphs")

        legacy_dir = get_user_global_resources_dir(user_id) / "graphs"
        search_dirs.append(legacy_dir)

        seen_ids: set[str] = set()
        db_files: list[Path] = []
        for graph_dir in search_dirs:
            sys_graph_dir = Path(as_system_path(graph_dir))
            if not sys_graph_dir.exists():
                continue
            for db_file in sorted(sys_graph_dir.glob("*.db")):
                kg_id = db_file.stem
                if kg_id in seen_ids:
                    continue
                seen_ids.add(kg_id)
                db_files.append(db_file)
        return db_files

    async def _get_conn(self) -> sqlite3.Connection:
        loop = asyncio.get_running_loop()

        def _connect() -> sqlite3.Connection:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(as_system_path(str(self._db_path)), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            return conn

        return await loop.run_in_executor(None, _connect)

    async def _run_db(self, fn: Callable[[sqlite3.Connection], _T]) -> _T:
        """在线程池中执行同步 SQLite 操作，避免阻塞事件循环。"""

        def _sync() -> _T:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(as_system_path(str(self._db_path)), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                return fn(conn)
            finally:
                conn.close()

        return await asyncio.to_thread(_sync)

    def _invalidate_graph_cache(self) -> None:
        self._nx_graph = None

    def _resolve_entity_id(self, conn: sqlite3.Connection, reference: str) -> Optional[str]:
        row = conn.execute(
            "SELECT entity_id FROM entities WHERE entity_id = ? OR name = ? LIMIT 1",
            [reference, reference],
        ).fetchone()
        return row["entity_id"] if row else None

    def _resolve_entity_name(self, conn: sqlite3.Connection, reference: str) -> Optional[str]:
        row = conn.execute(
            "SELECT name FROM entities WHERE entity_id = ? OR name = ? LIMIT 1",
            [reference, reference],
        ).fetchone()
        return row["name"] if row else None

    def _build_relation_endpoint_lookup(
        self,
        conn: sqlite3.Connection,
        endpoint_values: set[str],
    ) -> dict[str, str]:
        if not endpoint_values:
            return {}

        endpoint_placeholders = ", ".join(["?"] * len(endpoint_values))
        endpoint_params = list(endpoint_values)
        entity_rows = conn.execute(
            f"""
                SELECT entity_id, name
                FROM entities
                WHERE entity_id IN ({endpoint_placeholders})
                   OR name IN ({endpoint_placeholders})
            """,
            endpoint_params + endpoint_params,
        ).fetchall()
        endpoint_name_by_value: dict[str, str] = {}
        for row in entity_rows:
            endpoint_name_by_value[str(row["entity_id"])] = str(row["name"])
            endpoint_name_by_value[str(row["name"])] = str(row["name"])
        return endpoint_name_by_value

    def _entity_node_attrs(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "entity_id": row["entity_id"],
            "entity_type": row["entity_type"],
            "description": row["description"],
            "metadata_json": row["properties"] or "{}",
            "source_id": row["source_doc_id"],
        }

    def _ensure_tables(self) -> None:
        # Direct sync connection — called from __init__, cannot be async.
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(as_system_path(str(self._db_path)))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    description TEXT,
                    properties TEXT,
                    source_doc_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS relations (
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
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS communities (
                    community_id TEXT PRIMARY KEY,
                    level INTEGER NOT NULL,
                    entity_ids TEXT,
                    summary TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS graph_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    layout_positions TEXT,
                    layout_updated_at TEXT,
                    entity_count INTEGER DEFAULT 0,
                    relation_count INTEGER DEFAULT 0,
                    community_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_entity_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_entity_id)"
            )
            conn.commit()
        finally:
            conn.close()

    def _update_counts(self, conn: sqlite3.Connection) -> None:
        """重新计算并缓存实体、关系、社区数量到 graph_metadata。"""
        entity_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        relation_count = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        community_count = conn.execute("SELECT COUNT(*) FROM communities").fetchone()[0]
        conn.execute(
            """
            INSERT INTO graph_metadata (key, entity_count, relation_count, community_count)
            VALUES ('counts', ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                entity_count = excluded.entity_count,
                relation_count = excluded.relation_count,
                community_count = excluded.community_count
        """,
            [entity_count, relation_count, community_count],
        )

    @staticmethod
    def _get_cached_counts(conn: sqlite3.Connection) -> dict[str, int]:
        """优先读 graph_metadata 计数字段，未命中则回退到 COUNT(*)。"""
        row = conn.execute(
            "SELECT entity_count, relation_count, community_count FROM graph_metadata WHERE key = 'counts'"
        ).fetchone()
        if row is not None and row[0] is not None:
            return {
                "entity_count": int(row[0] or 0),
                "relation_count": int(row[1] or 0),
                "community_count": int(row[2] or 0),
            }
        return {
            "entity_count": conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "relation_count": conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0],
            "community_count": conn.execute("SELECT COUNT(*) FROM communities").fetchone()[0],
        }

    async def save_layout_positions(self, positions: Dict[str, Dict[str, float]]) -> None:
        """将布局位置持久化到 graph_metadata。"""
        import datetime

        conn = await self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO graph_metadata (key, layout_positions, layout_updated_at)
                VALUES ('layout', ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    layout_positions = excluded.layout_positions,
                    layout_updated_at = excluded.layout_updated_at
            """,
                [json.dumps(positions, ensure_ascii=False), datetime.datetime.now().isoformat()],
            )
            conn.commit()
        finally:
            conn.close()

    async def get_layout_positions(self) -> Optional[Dict[str, Dict[str, float]]]:
        """读取持久化的布局位置。"""
        conn = await self._get_conn()
        try:
            row = conn.execute(
                "SELECT layout_positions FROM graph_metadata WHERE key = 'layout'"
            ).fetchone()
            if row and row[0]:
                return json.loads(row[0])
            return None
        finally:
            conn.close()

    @classmethod
    def list_graphs(
        cls,
        user_id: str,
        *,
        workspace_dirs: list[Path] | None = None,
    ) -> List[Dict[str, Any]]:
        """列出用户所有知识图谱。

        扫描范围：
        1. workspace_dirs 中指定的工作区目录（.aiasys/graphs/）
        2. 用户所有工作区目录（自动扫描）
        3. 旧全局资源目录（兼容旧数据）
        """
        db_files = cls._scan_graph_dirs(user_id, workspace_dirs=workspace_dirs)
        graphs: list[Dict[str, Any]] = []

        for db_file in db_files:
            kg_id = db_file.stem
            try:
                with sqlite3.connect(as_system_path(str(db_file))) as conn:
                    conn.row_factory = sqlite3.Row
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS graph_metadata (
                            key TEXT PRIMARY KEY,
                            value TEXT,
                            layout_positions TEXT,
                            layout_updated_at TEXT,
                            entity_count INTEGER DEFAULT 0,
                            relation_count INTEGER DEFAULT 0,
                            community_count INTEGER DEFAULT 0
                        )
                    """)
                    counts = cls._get_cached_counts(conn)
                    doc_count = conn.execute(
                        "SELECT COUNT(DISTINCT source_doc_id) FROM entities WHERE source_doc_id IS NOT NULL"
                    ).fetchone()[0]
                    metadata_rows = conn.execute(
                        "SELECT key, value FROM graph_metadata WHERE key IN ('name', 'description')"
                    ).fetchall()
                    metadata = {row["key"]: row["value"] for row in metadata_rows}
                graphs.append(
                    {
                        "kg_id": kg_id,
                        "name": metadata.get("name") or kg_id,
                        "description": metadata.get("description"),
                        "entity_count": counts["entity_count"],
                        "relation_count": counts["relation_count"],
                        "document_count": doc_count,
                    }
                )
            except sqlite3.Error as exc:
                logger.warning("跳过已损坏的知识图谱数据库: path=%s error=%s", db_file, exc)
        return graphs

    async def set_metadata(self, key: str, value: Optional[str]) -> None:
        """写入图谱级元数据。"""
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError("元数据 key 不能为空")

        conn = await self._get_conn()
        try:
            conn.execute(
                """
                    INSERT INTO graph_metadata (key, value)
                    VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                [normalized_key, value],
            )
            conn.commit()
        finally:
            conn.close()

    async def get_metadata(self, key: str) -> Optional[str]:
        """读取图谱级元数据。"""
        normalized_key = key.strip()
        if not normalized_key:
            return None

        conn = await self._get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM graph_metadata WHERE key = ?",
                [normalized_key],
            ).fetchone()
            return row["value"] if row else None
        finally:
            conn.close()

    async def add_entity(self, entity: Entity) -> None:
        def _sync(conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                    INSERT OR REPLACE INTO entities
                    (entity_id, name, entity_type, description, properties, source_doc_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    entity.entity_id,
                    entity.name,
                    entity.entity_type,
                    entity.description,
                    json.dumps(entity.metadata, ensure_ascii=False) if entity.metadata else "{}",
                    entity.source_id,
                ],
            )
            self._update_counts(conn)
            conn.commit()
            self._invalidate_graph_cache()

        await self._run_db(_sync)

    async def add_relation(self, relation: Relation) -> None:
        def _sync(conn: sqlite3.Connection) -> None:
            source_entity_id = self._resolve_entity_id(conn, relation.source_entity)
            target_entity_id = self._resolve_entity_id(conn, relation.target_entity)
            if source_entity_id is None or target_entity_id is None:
                logger.warning(
                    "跳过关系插入，实体未找到: relation_id=%s source=%s target=%s",
                    relation.relation_id,
                    relation.source_entity,
                    relation.target_entity,
                )
                return
            conn.execute(
                """
                    INSERT OR REPLACE INTO relations
                    (relation_id, source_entity_id, target_entity_id, relation_type, description, strength, properties, source_doc_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    relation.relation_id,
                    source_entity_id,
                    target_entity_id,
                    relation.description[:50],
                    relation.description,
                    relation.strength,
                    (
                        json.dumps(relation.metadata, ensure_ascii=False)
                        if relation.metadata
                        else "{}"
                    ),
                    relation.source_id,
                ],
            )
            self._update_counts(conn)
            conn.commit()
            self._invalidate_graph_cache()

        await self._run_db(_sync)

    async def add_subgraph(
        self, doc_id: str, entities: List[Entity], relations: List[Relation]
    ) -> None:
        def _sync(conn: sqlite3.Connection) -> None:
            try:
                conn.execute("BEGIN")
                if entities:
                    entity_params = [
                        [
                            entity.entity_id,
                            entity.name,
                            entity.entity_type,
                            entity.description,
                            json.dumps(entity.metadata, ensure_ascii=False)
                            if entity.metadata
                            else "{}",
                            doc_id,
                        ]
                        for entity in entities
                    ]
                    conn.executemany(
                        """
                            INSERT OR REPLACE INTO entities
                            (entity_id, name, entity_type, description, properties, source_doc_id)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        entity_params,
                    )
                for relation in relations:
                    source_entity_id = self._resolve_entity_id(conn, relation.source_entity)
                    target_entity_id = self._resolve_entity_id(conn, relation.target_entity)
                    if source_entity_id is None or target_entity_id is None:
                        logger.warning(
                            "跳过关系插入，实体未找到: relation_id=%s source=%s target=%s",
                            relation.relation_id,
                            relation.source_entity,
                            relation.target_entity,
                        )
                        continue
                    conn.execute(
                        """
                            INSERT OR REPLACE INTO relations
                            (relation_id, source_entity_id, target_entity_id, relation_type, description, strength, properties, source_doc_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            relation.relation_id,
                            source_entity_id,
                            target_entity_id,
                            relation.description[:50],
                            relation.description,
                            relation.strength,
                            (
                                json.dumps(relation.metadata, ensure_ascii=False)
                                if relation.metadata
                                else "{}"
                            ),
                            doc_id,
                        ],
                    )
                self._update_counts(conn)
                conn.execute("COMMIT")
                self._invalidate_graph_cache()
            except Exception:
                conn.execute("ROLLBACK")
                raise

        await self._run_db(_sync)

    async def search_entities(
        self, query: str, entity_type: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        def _sync(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
            sql = """
                SELECT entity_id, name, entity_type, description, properties
                FROM entities
                WHERE (name LIKE ? OR description LIKE ?)
            """
            params = [f"%{query}%", f"%{query}%"]
            if entity_type:
                sql += " AND entity_type = ?"
                params.append(entity_type)
            sql += " LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "entity_id": r["entity_id"],
                    "name": r["name"],
                    "entity_type": r["entity_type"],
                    "description": r["description"],
                    "properties": json.loads(r["properties"]) if r["properties"] else {},
                }
                for r in rows
            ]

        return await self._run_db(_sync)

    async def get_entity(self, name: str) -> Optional[Dict[str, Any]]:
        def _sync(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
            row = conn.execute(
                "SELECT entity_id, name, entity_type, description, properties FROM entities WHERE name = ? OR entity_id = ? LIMIT 1",
                [name, name],
            ).fetchone()
            if not row:
                return None
            return {
                "entity_id": row["entity_id"],
                "name": row["name"],
                "entity_type": row["entity_type"],
                "description": row["description"],
                "properties": json.loads(row["properties"]) if row["properties"] else {},
            }

        return await self._run_db(_sync)

    async def get_entity_relations(
        self,
        entity_name: str,
        relation_type: Optional[str] = None,
        direction: str = "both",
        limit: int = 20,
    ) -> tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """查询一个实体的直接关系，兼容关系端点中存储实体 ID 或实体名的历史数据。"""

        def _sync(
            conn: sqlite3.Connection,
        ) -> tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
            entity = conn.execute(
                """
                    SELECT entity_id, name, entity_type, description
                    FROM entities
                    WHERE name = ? OR entity_id = ?
                    LIMIT 1
                """,
                [entity_name, entity_name],
            ).fetchone()
            if not entity:
                return None, []

            identity_values = {
                str(entity["entity_id"]),
                str(entity["name"]),
            }
            placeholders = ", ".join(["?"] * len(identity_values))
            identity_params = list(identity_values)

            if direction == "outgoing":
                where_clause = f"source_entity_id IN ({placeholders})"
                query_params: List[Any] = identity_params.copy()
            elif direction == "incoming":
                where_clause = f"target_entity_id IN ({placeholders})"
                query_params = identity_params.copy()
            else:
                where_clause = (
                    f"(source_entity_id IN ({placeholders}) "
                    f"OR target_entity_id IN ({placeholders}))"
                )
                query_params = identity_params + identity_params

            normalized_relation_type = str(relation_type or "").strip()
            if normalized_relation_type:
                where_clause += (
                    " AND (relation_type = ? OR relation_type LIKE ? OR description LIKE ?)"
                )
                relation_like = f"%{normalized_relation_type}%"
                query_params.extend([normalized_relation_type, relation_like, relation_like])

            query_params.append(limit)
            relation_rows = conn.execute(
                f"""
                    SELECT relation_id, source_entity_id, target_entity_id, relation_type,
                           description, strength, source_doc_id
                    FROM relations
                    WHERE {where_clause}
                    ORDER BY strength DESC, relation_id ASC
                    LIMIT ?
                """,
                query_params,
            ).fetchall()

            endpoint_values: set[str] = set()
            for row in relation_rows:
                endpoint_values.add(str(row["source_entity_id"]))
                endpoint_values.add(str(row["target_entity_id"]))

            endpoint_name_by_value = self._build_relation_endpoint_lookup(
                conn,
                endpoint_values,
            )

            relations: List[Dict[str, Any]] = []
            for row in relation_rows:
                source_raw = str(row["source_entity_id"])
                target_raw = str(row["target_entity_id"])
                source_name = endpoint_name_by_value.get(source_raw, source_raw)
                target_name = endpoint_name_by_value.get(target_raw, target_raw)
                if source_raw in identity_values or source_name in identity_values:
                    relative_direction = "outgoing"
                elif target_raw in identity_values or target_name in identity_values:
                    relative_direction = "incoming"
                else:
                    relative_direction = "both"
                relations.append(
                    {
                        "relation_id": row["relation_id"],
                        "source": source_name,
                        "target": target_name,
                        "relation_type": row["relation_type"],
                        "description": row["description"],
                        "strength": row["strength"],
                        "source_doc_id": row["source_doc_id"],
                        "direction": relative_direction,
                    }
                )

            return (
                {
                    "entity_id": entity["entity_id"],
                    "name": entity["name"],
                    "entity_type": entity["entity_type"],
                    "description": entity["description"],
                },
                relations,
            )

        return await self._run_db(_sync)

    async def create_entity(
        self,
        name: str,
        entity_type: str = "concept",
        description: str = "",
        properties: Optional[Dict[str, Any]] = None,
        source_doc_id: str = "manual",
    ) -> Dict[str, Any]:
        """创建手工实体，返回创建后的实体。"""
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("实体名称不能为空")

        normalized_type = entity_type.strip() if entity_type else "concept"
        normalized_description = description.strip() if description else ""
        entity_properties = properties or {}

        conn = await self._get_conn()
        try:
            row = conn.execute(
                "SELECT entity_id FROM entities WHERE name = ?",
                [normalized_name],
            ).fetchone()
            if row:
                raise ValueError(f"实体已存在: {normalized_name}")

            entity_id = str(uuid.uuid4())
            conn.execute(
                """
                    INSERT INTO entities
                    (entity_id, name, entity_type, description, properties, source_doc_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    entity_id,
                    normalized_name,
                    normalized_type or "concept",
                    normalized_description,
                    json.dumps(entity_properties, ensure_ascii=False),
                    source_doc_id,
                ],
            )
            self._update_counts(conn)
            conn.commit()
            self._invalidate_graph_cache()
            return {
                "entity_id": entity_id,
                "name": normalized_name,
                "entity_type": normalized_type or "concept",
                "description": normalized_description,
                "properties": entity_properties,
            }
        finally:
            conn.close()

    async def create_relation(
        self,
        source_entity_id: str,
        target_entity_id: str,
        relation_type: str = "related_to",
        description: str = "",
        strength: float = 1.0,
        properties: Optional[Dict[str, Any]] = None,
        source_doc_id: str = "manual",
    ) -> Dict[str, Any]:
        """创建手工关系，返回创建后的关系。"""
        normalized_source = str(source_entity_id or "").strip()
        normalized_target = str(target_entity_id or "").strip()
        if not normalized_source:
            raise ValueError("源节点不能为空")
        if not normalized_target:
            raise ValueError("目标节点不能为空")

        normalized_type = str(relation_type or "").strip() or "related_to"
        normalized_description = str(description or "").strip()
        normalized_strength = float(strength or 1.0)
        relation_properties = properties or {}

        conn = await self._get_conn()
        try:
            source_row = conn.execute(
                "SELECT entity_id, name FROM entities WHERE entity_id = ? OR name = ? LIMIT 1",
                [normalized_source, normalized_source],
            ).fetchone()
            target_row = conn.execute(
                "SELECT entity_id, name FROM entities WHERE entity_id = ? OR name = ? LIMIT 1",
                [normalized_target, normalized_target],
            ).fetchone()
            if not source_row:
                raise ValueError("源节点不存在")
            if not target_row:
                raise ValueError("目标节点不存在")

            source_id = str(source_row["entity_id"])
            target_id = str(target_row["entity_id"])
            if source_id == target_id:
                raise ValueError("不能连接节点自身")

            duplicate = conn.execute(
                """
                    SELECT relation_id FROM relations
                    WHERE source_entity_id = ?
                      AND target_entity_id = ?
                      AND relation_type = ?
                    LIMIT 1
                """,
                [source_id, target_id, normalized_type],
            ).fetchone()
            if duplicate:
                raise ValueError("相同关系已存在")

            relation_id = str(uuid.uuid4())
            conn.execute(
                """
                    INSERT INTO relations
                    (relation_id, source_entity_id, target_entity_id, relation_type, description, strength, properties, source_doc_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    relation_id,
                    source_id,
                    target_id,
                    normalized_type,
                    normalized_description,
                    normalized_strength,
                    json.dumps(relation_properties, ensure_ascii=False),
                    source_doc_id,
                ],
            )
            self._update_counts(conn)
            conn.commit()
            self._invalidate_graph_cache()
            return {
                "relation_id": relation_id,
                "source": source_id,
                "source_name": str(source_row["name"]),
                "target": target_id,
                "target_name": str(target_row["name"]),
                "relation_type": normalized_type,
                "description": normalized_description,
                "strength": normalized_strength,
                "properties": relation_properties,
            }
        finally:
            conn.close()

    async def update_entity(
        self,
        entity_id: str,
        name: Optional[str] = None,
        entity_type: Optional[str] = None,
        description: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """更新实体信息，返回更新后的实体"""
        conn = await self._get_conn()
        try:
            # 先获取当前实体
            row = conn.execute(
                "SELECT entity_id, name, entity_type, description, properties FROM entities WHERE entity_id = ?",
                [entity_id],
            ).fetchone()
            if not row:
                return None

            new_name = name if name is not None else row["name"]
            new_type = entity_type if entity_type is not None else row["entity_type"]
            new_description = description if description is not None else row["description"]
            current_properties = json.loads(row["properties"]) if row["properties"] else {}
            new_properties = properties if properties is not None else current_properties

            conn.execute(
                """
                    UPDATE entities
                    SET name = ?, entity_type = ?, description = ?, properties = ?
                    WHERE entity_id = ?
                """,
                [
                    new_name,
                    new_type,
                    new_description,
                    json.dumps(new_properties, ensure_ascii=False),
                    entity_id,
                ],
            )
            conn.commit()
            self._invalidate_graph_cache()
            return {
                "entity_id": entity_id,
                "name": new_name,
                "entity_type": new_type,
                "description": new_description,
                "properties": new_properties,
            }
        finally:
            conn.close()

    async def delete_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """删除实体，并同步删除连接到该实体的关系。"""
        normalized_entity_id = str(entity_id or "").strip()
        if not normalized_entity_id:
            return None

        conn = await self._get_conn()
        transaction_started = False
        try:
            row = conn.execute(
                """
                    SELECT entity_id, name
                    FROM entities
                    WHERE entity_id = ? OR name = ?
                    LIMIT 1
                """,
                [normalized_entity_id, normalized_entity_id],
            ).fetchone()
            if not row:
                return None

            identity_values = [str(row["entity_id"]), str(row["name"])]
            placeholders = ", ".join(["?"] * len(identity_values))

            conn.execute("BEGIN")
            transaction_started = True
            relation_cursor = conn.execute(
                f"""
                    DELETE FROM relations
                    WHERE source_entity_id IN ({placeholders})
                       OR target_entity_id IN ({placeholders})
                """,
                identity_values + identity_values,
            )
            conn.execute("DELETE FROM entities WHERE entity_id = ?", [row["entity_id"]])
            self._update_counts(conn)
            conn.execute("COMMIT")
            self._invalidate_graph_cache()
            return {
                "entity_id": str(row["entity_id"]),
                "name": str(row["name"]),
                "deleted_relations": int(relation_cursor.rowcount or 0),
            }
        except Exception:
            if transaction_started:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    async def get_all_entities(
        self, entity_type: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        def _sync(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
            sql = "SELECT entity_id, name, entity_type, description FROM entities WHERE 1=1"
            params = []
            if entity_type:
                sql += " AND entity_type = ?"
                params.append(entity_type)
            sql += " LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "entity_id": r["entity_id"],
                    "name": r["name"],
                    "entity_type": r["entity_type"],
                    "description": r["description"],
                }
                for r in rows
            ]

        return await self._run_db(_sync)

    async def get_statistics(self) -> Dict[str, Any]:
        def _sync(conn: sqlite3.Connection) -> Dict[str, Any]:
            counts = self._get_cached_counts(conn)
            doc_count = conn.execute(
                "SELECT COUNT(DISTINCT source_doc_id) FROM entities"
            ).fetchone()[0]
            type_rows = conn.execute("SELECT DISTINCT entity_type FROM entities").fetchall()
            return {
                "entity_count": counts["entity_count"],
                "relation_count": counts["relation_count"],
                "document_count": doc_count,
                "entity_types": [r[0] for r in type_rows],
            }

        return await self._run_db(_sync)

    async def save_communities(self, communities: Dict[int, Dict[str, Any]]) -> None:
        def _sync(conn: sqlite3.Connection) -> None:
            try:
                conn.execute("BEGIN")
                conn.execute("DELETE FROM communities")
                for level, level_data in communities.items():
                    for comm_id, data in level_data.items():
                        entity_ids = data.get("entity_ids") or data.get("nodes") or []
                        conn.execute(
                            """
                                INSERT INTO communities
                                (community_id, level, entity_ids, summary)
                                VALUES (?, ?, ?, ?)
                            """,
                            [
                                str(comm_id) if isinstance(comm_id, int) else str(comm_id),
                                int(level),
                                json.dumps(entity_ids, ensure_ascii=False),
                                data.get("summary", ""),
                            ],
                        )
                self._update_counts(conn)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            self._invalidate_graph_cache()

        await self._run_db(_sync)

    async def get_communities(self, level: int = 0) -> List[Dict[str, Any]]:
        conn = await self._get_conn()
        try:
            rows = conn.execute(
                "SELECT community_id, entity_ids, summary FROM communities WHERE level = ?",
                [level],
            ).fetchall()
            return [
                {
                    "community_id": r["community_id"],
                    "entity_ids": json.loads(r["entity_ids"]) if r["entity_ids"] else [],
                    "summary": r["summary"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def delete_graph(self) -> None:
        if self._db_path.exists():
            try:
                self._db_path.unlink()
            except FileNotFoundError:
                pass
            except Exception:
                logger.warning("删除图谱数据库失败: %s", self._db_path, exc_info=True)

    # ==================== 原始数据探查接口 ====================

    async def list_tables(self) -> List[Dict[str, Any]]:
        """返回当前数据库中所有用户表的名称和列信息。"""
        conn = await self._get_conn()
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            tables = []
            for row in cursor.fetchall():
                table_name = row["name"]
                if not _VALID_SQL_IDENTIFIER.match(table_name):
                    continue
                col_cursor = conn.execute(f'PRAGMA table_info("{table_name}")')
                columns = [
                    {
                        "name": c["name"],
                        "type": c["type"],
                        "notnull": bool(c["notnull"]),
                        "pk": bool(c["pk"]),
                    }
                    for c in col_cursor.fetchall()
                ]
                tables.append({"name": table_name, "columns": columns})
            return tables
        finally:
            conn.close()

    async def execute_raw_sql(self, sql: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
        """执行原始 SQL 查询并返回结果。仅允许 SELECT 语句。"""
        import re

        conn = await self._get_conn()
        try:
            cleaned = sql.strip()
            if not cleaned:
                raise ValueError("SQL 不能为空")
            # 去除 SQL 行注释，再检测分号，防止注释绕过
            no_comments = re.sub(r"--[^\n]*", "", cleaned)
            first_word = re.sub(r"^\s*", "", no_comments, flags=re.IGNORECASE).lstrip()
            if not re.match(r"^SELECT\b", first_word, re.IGNORECASE) or re.search(
                r";", no_comments
            ):
                raise ValueError("只允许执行 SELECT 查询")

            cursor = conn.execute(cleaned, params or [])
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            result_rows = []
            for row in rows:
                result_rows.append({col: row[col] for col in columns})
            return {"columns": columns, "rows": result_rows, "row_count": len(result_rows)}
        finally:
            conn.close()

    # ==================== networkx 视图接口 ====================

    async def get_graph(self) -> nx.Graph:
        """返回当前 SQLite 图谱的 networkx 内存视图。"""
        if self._nx_graph is None:
            self._nx_graph = await self._load_graph()
        return self._nx_graph

    async def _load_graph(self) -> nx.Graph:
        graph = nx.Graph()
        conn = await self._get_conn()
        try:
            entity_rows = conn.execute(
                "SELECT entity_id, name, entity_type, description, properties, source_doc_id FROM entities"
            ).fetchall()
            entity_name_by_id: dict[str, str] = {}
            for r in entity_rows:
                graph.add_node(r["name"], **self._entity_node_attrs(r))
                entity_name_by_id[r["entity_id"]] = r["name"]
            relation_rows = conn.execute(
                "SELECT relation_id, source_entity_id, target_entity_id, relation_type, description, strength FROM relations"
            ).fetchall()
            for r in relation_rows:
                source_name = entity_name_by_id.get(r["source_entity_id"])
                target_name = entity_name_by_id.get(r["target_entity_id"])
                if source_name and target_name:
                    graph.add_edge(
                        source_name,
                        target_name,
                        relation_id=r["relation_id"],
                        relation_type=r["relation_type"],
                        description=r["description"],
                        strength=r["strength"],
                    )
        finally:
            conn.close()
        return graph

    async def get_subgraph(self, entity_names: List[str], depth: int = 1) -> nx.Graph:
        """按实体名称从 SQLite 读取子图，并返回 networkx 图对象。"""
        if not entity_names:
            return nx.Graph()

        def _sync(conn: sqlite3.Connection) -> nx.Graph:
            placeholders = ", ".join(["?"] * len(entity_names))
            entity_rows = conn.execute(
                f"""
                    WITH RECURSIVE subgraph_entities AS (
                        SELECT entity_id, name, entity_type, description, properties, source_doc_id, 0 as depth
                        FROM entities
                        WHERE name IN ({placeholders}) OR entity_id IN ({placeholders})
                        UNION ALL
                        SELECT e.entity_id, e.name, e.entity_type, e.description, e.properties, e.source_doc_id, se.depth + 1
                        FROM subgraph_entities se
                        JOIN relations r
                            ON se.entity_id = r.source_entity_id
                            OR se.name = r.source_entity_id
                            OR se.entity_id = r.target_entity_id
                            OR se.name = r.target_entity_id
                        JOIN entities e
                            ON e.entity_id = r.source_entity_id
                            OR e.name = r.source_entity_id
                            OR e.entity_id = r.target_entity_id
                            OR e.name = r.target_entity_id
                        WHERE se.depth < ?
                            AND e.entity_id != se.entity_id
                    )
                    SELECT DISTINCT entity_id, name, entity_type, description, properties, source_doc_id
                    FROM subgraph_entities
                """,
                entity_names + entity_names + [depth],
            ).fetchall()

            graph = nx.Graph()
            entity_lookup = {}
            for r in entity_rows:
                graph.add_node(r["name"], **self._entity_node_attrs(r))
                entity_lookup[r["entity_id"]] = r["name"]
                entity_lookup[r["name"]] = r["name"]

            if not entity_lookup:
                return graph

            entity_values = list(entity_lookup)
            id_placeholders = ", ".join(["?"] * len(entity_values))
            relation_rows = conn.execute(
                f"""
                    SELECT relation_id, source_entity_id, target_entity_id, relation_type, description, strength
                    FROM relations
                    WHERE source_entity_id IN ({id_placeholders}) AND target_entity_id IN ({id_placeholders})
                """,
                entity_values + entity_values,
            ).fetchall()

            for r in relation_rows:
                source = entity_lookup.get(r["source_entity_id"])
                target = entity_lookup.get(r["target_entity_id"])
                if source and target:
                    graph.add_edge(
                        source,
                        target,
                        relation_id=r["relation_id"],
                        relation_type=r["relation_type"],
                        description=r["description"],
                        strength=r["strength"],
                    )
            return graph

        return await self._run_db(_sync)

    async def get_visualization_graph(
        self,
        limit: int = 180,
        offset: int = 0,
    ) -> tuple[nx.Graph, bool]:
        """按实体关联度在 SQL 层面排序分页，避免全量加载内存。"""
        conn = await self._get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            if limit <= 0 or total <= limit:
                graph = await self.get_graph()
                return graph.copy(), False

            entity_rows = conn.execute(
                """
                    SELECT e.entity_id, e.name, e.entity_type, e.description,
                           e.properties, e.source_doc_id,
                           COUNT(r.relation_id) AS degree
                    FROM entities e
                    LEFT JOIN relations r
                        ON e.entity_id = r.source_entity_id
                        OR e.entity_id = r.target_entity_id
                    GROUP BY e.entity_id
                    ORDER BY degree DESC, e.name COLLATE NOCASE
                    LIMIT ? OFFSET ?
                """,
                [limit, offset],
            ).fetchall()

            graph = nx.Graph()
            entity_name_by_id: dict[str, str] = {}
            for r in entity_rows:
                graph.add_node(r["name"], **self._entity_node_attrs(r))
                entity_name_by_id[r["entity_id"]] = r["name"]

            if entity_name_by_id:
                placeholders = ", ".join(["?"] * len(entity_name_by_id))
                relation_rows = conn.execute(
                    f"""
                        SELECT relation_id, source_entity_id, target_entity_id,
                               relation_type, description, strength
                        FROM relations
                        WHERE source_entity_id IN ({placeholders})
                          AND target_entity_id IN ({placeholders})
                    """,
                    list(entity_name_by_id.keys()) * 2,
                ).fetchall()
                for r in relation_rows:
                    source_name = entity_name_by_id.get(r["source_entity_id"])
                    target_name = entity_name_by_id.get(r["target_entity_id"])
                    if source_name and target_name:
                        graph.add_edge(
                            source_name,
                            target_name,
                            relation_id=r["relation_id"],
                            relation_type=r["relation_type"],
                            description=r["description"],
                            strength=r["strength"],
                        )

            return graph, True
        finally:
            conn.close()

    async def serialize_graph(
        self,
        subgraph: Optional[nx.Graph] = None,
        communities: Optional[Dict[str, Any]] = None,
        source: str = "unknown",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        target = subgraph if subgraph is not None else await self.get_graph()
        community_lookup: dict[str, list[str]] = {}
        for community_id, community_data in (communities or {}).items():
            entity_ids = []
            if isinstance(community_data, dict):
                raw_entity_ids = (
                    community_data.get("entity_ids")
                    or community_data.get("nodes")
                    or community_data.get("members")
                    or []
                )
                if isinstance(raw_entity_ids, str):
                    try:
                        raw_entity_ids = json.loads(raw_entity_ids)
                    except json.JSONDecodeError:
                        raw_entity_ids = []
                if isinstance(raw_entity_ids, list):
                    entity_ids = [str(item) for item in raw_entity_ids]
            for entity_id in entity_ids:
                community_lookup.setdefault(entity_id, []).append(str(community_id))

        node_ids: dict[Any, str] = {}
        nodes = []
        for node, data in target.nodes(data=True):
            node_id = str(data.get("entity_id") or node)
            node_ids[node] = node_id
            metadata = {}
            metadata_json = data.get("metadata_json")
            if isinstance(metadata_json, str) and metadata_json.strip():
                try:
                    parsed_metadata = json.loads(metadata_json)
                    if isinstance(parsed_metadata, dict):
                        metadata = parsed_metadata
                except json.JSONDecodeError:
                    metadata = {}
            community_ids = community_lookup.get(node_id, []) or community_lookup.get(str(node), [])
            nodes.append(
                {
                    "id": node_id,
                    "name": str(node),
                    "entity_type": data.get("entity_type", "unknown") or "unknown",
                    "description": data.get("description", "") or "",
                    "degree": int(target.degree(node)),
                    "community_ids": community_ids,
                    "primary_community": community_ids[0] if community_ids else None,
                    "properties": metadata,
                }
            )
        edges = []
        for u, v, data in target.edges(data=True):
            source_id = node_ids.get(u, str(u))
            target_id = node_ids.get(v, str(v))
            relation_type = data.get("relation_type", "") or ""
            strength = float(data.get("strength", 1.0) or 1.0)
            edges.append(
                {
                    "id": data.get("relation_id") or f"{source_id}->{target_id}:{relation_type}",
                    "source": source_id,
                    "target": target_id,
                    "relation_type": relation_type,
                    "description": data.get("description", "") or relation_type,
                    "strength": strength,
                    "metadata": {},
                }
            )
        return {
            "source": source,
            "nodes": nodes,
            "edges": edges,
            "truncated": bool(kwargs.get("truncated", False)),
            "total_nodes": int(kwargs.get("total_nodes", target.number_of_nodes())),
            "total_edges": int(kwargs.get("total_edges", target.number_of_edges())),
        }
