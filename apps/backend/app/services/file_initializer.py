"""文件类型初始化器注册表。

统一管理所有需要特殊初始化的文件类型（知识库、知识图谱、Canvas、数据表等）。
前端和后端 API 通过此注册表分发创建请求，Agent 工具也走同一条路径。

设计原则：
- 每个文件类型对应一个 FileInitializer 子类
- Initializer 负责：参数校验、文件初始化、返回元数据
- Registry 负责：类型注册、按 file_type 查找、按文件后缀推断类型
- 路径校验、越界检查、历史记录由调用方（API/Agent 工具）负责，不在 Initializer 中重复
"""

from __future__ import annotations

import logging
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FileInitResult:
    """文件初始化结果。"""

    file_path: Path
    """创建的文件绝对路径"""
    size: int
    """文件大小（字节）"""
    meta: dict[str, Any] = field(default_factory=dict)
    """附加元数据，会合并到 FileCreateResponse.meta 中"""


class FileInitializer(ABC):
    """文件类型初始化器基类。

    每个子类对应一种文件类型，负责该类型的初始化逻辑。
    """

    # --- 子类必须定义 ---

    file_extension: str
    """文件后缀，如 ".kb.db"、".canvas"、".graph.db" """

    file_type: str
    """文件类型标识，如 "knowledge_base"、"canvas"、"knowledge_graph" """

    display_name: str
    """人类可读的名称，如 "知识库"、"Canvas"、"知识图谱" """

    # --- 子类可选覆盖 ---

    def validate_params(self, params: dict[str, Any]) -> None:
        """校验类型相关参数。默认不做校验。"""

    @abstractmethod
    def initialize(self, file_path: Path, params: dict[str, Any]) -> FileInitResult:
        """执行文件初始化。

        Args:
            file_path: 目标文件绝对路径。父目录已由调用方创建。
            params: 类型相关参数（如 name、description 等）。

        Returns:
            FileInitResult: 包含文件大小和元数据。
        """

    def get_default_params(self) -> dict[str, Any]:
        """返回该类型的默认参数。"""
        return {}


# ---------------------------------------------------------------------------
# Text File Initializer
# ---------------------------------------------------------------------------


class TextFileInitializer(FileInitializer):
    """普通文本文件初始化器。

    覆盖所有可编辑文本后缀（.md, .py, .json, .txt 等），不做特殊初始化。
    """

    file_extension = ""  # text 类型支持多种后缀，不做单一后缀校验
    file_type = "text"
    display_name = "普通文件"

    # 所有视为文本文件的后缀
    suffix_set: set[str] = {
        ".md",
        ".markdown",
        ".mdx",
        ".txt",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".csv",
        ".tsv",
        ".xml",
        ".ini",
        ".conf",
        ".cfg",
        ".toml",
        ".log",
        ".properties",
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".html",
        ".css",
        ".scss",
        ".sql",
        ".sh",
        ".bash",
        ".zsh",
    }

    def initialize(self, file_path: Path, params: dict[str, Any]) -> FileInitResult:
        content = params.get("content", "")
        content_bytes = content.encode("utf-8") if content else b""
        file_path.write_bytes(content_bytes)
        return FileInitResult(
            file_path=file_path,
            size=len(content_bytes),
        )


# ---------------------------------------------------------------------------
# Canvas Initializer
# ---------------------------------------------------------------------------

DEFAULT_CANVAS_CONTENT = '{\n  "nodes": [],\n  "edges": []\n}\n'


class CanvasFileInitializer(FileInitializer):
    """Canvas 文件初始化器。

    写入空的 JSON Canvas 骨架（nodes: [], edges: []）。
    """

    file_extension = ".canvas"
    file_type = "canvas"
    display_name = "Canvas"

    def initialize(self, file_path: Path, params: dict[str, Any]) -> FileInitResult:
        content = params.get("content") or DEFAULT_CANVAS_CONTENT
        content_bytes = content.encode("utf-8")
        file_path.write_bytes(content_bytes)
        return FileInitResult(
            file_path=file_path,
            size=len(content_bytes),
            meta={"resource_type": "canvas", "renderer_hint": "canvas_preview"},
        )


# ---------------------------------------------------------------------------
# Knowledge Base Initializer
# ---------------------------------------------------------------------------


class KnowledgeBaseInitializer(FileInitializer):
    """知识库文件初始化器。

    创建 SQLite .kb.db 文件，写入 _aiasys_metadata 表，
    并通过 SQLiteKBService 在知识库系统中登记。
    """

    file_extension = ".kb.db"
    file_type = "knowledge_base"
    display_name = "知识库"

    def validate_params(self, params: dict[str, Any]) -> None:
        name = params.get("name", "").strip()
        if not name:
            raise ValueError("知识库名称不能为空")

    def initialize(self, file_path: Path, params: dict[str, Any]) -> FileInitResult:
        from app.knowledge import SQLiteKBService
        from app.knowledge.models import KnowledgeBaseCreate

        name = params.get("name", "").strip()
        description = params.get("description", "")
        user_id = params.get("user_id", "system")
        relative_path = params.get("_relative_path", file_path.name)
        db_path_prefix = params.get("_db_path_prefix", "/workspace")

        # overwrite 场景：删除旧文件，确保全新初始化
        if file_path.exists():
            file_path.unlink()

        # 在知识库系统中登记
        kb = SQLiteKBService().create_knowledge_base(
            user_id,
            KnowledgeBaseCreate(name=name, description=description),
        )

        # 写入 SQLite metadata（失败时清理知识库记录，避免孤儿数据）
        try:
            _write_knowledge_db_metadata(
                file_path=file_path,
                kb_id=kb.id,
                name=kb.name,
                description=kb.description or "",
                db_path=f"{db_path_prefix}/{relative_path}",
            )
        except Exception:
            try:
                SQLiteKBService().delete_knowledge_base(user_id, kb.id)
            except Exception as cleanup_err:
                logger.error("清理知识库记录失败: kb_id=%s, error=%s", kb.id, cleanup_err)
            # 清理残留的半成品文件
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass
            raise

        return FileInitResult(
            file_path=file_path,
            size=file_path.stat().st_size,
            meta={
                "id": kb.id,
                "knowledge_base_id": kb.id,
                "name": kb.name,
                "description": kb.description or "",
                "resource_type": "knowledge",
                "renderer_hint": "knowledge_base_preview",
            },
        )


# ---------------------------------------------------------------------------
# Knowledge Graph Initializer
# ---------------------------------------------------------------------------


class KnowledgeGraphInitializer(FileInitializer):
    """知识图谱文件初始化器。

    创建 SQLite .graph.db 文件，初始化 5 张表（_aiasys_metadata、entities、
    relations、communities、graph_metadata）。
    """

    file_extension = ".graph.db"
    file_type = "knowledge_graph"
    display_name = "知识图谱"

    def validate_params(self, params: dict[str, Any]) -> None:
        graph_id = (params.get("graph_id", "") or "").strip()
        name = (params.get("name", "") or "").strip()
        if not graph_id and not name:
            raise ValueError("graph_id 或 name 不能为空")

    def initialize(self, file_path: Path, params: dict[str, Any]) -> FileInitResult:
        graph_id = params.get("graph_id", "").strip() or file_path.stem.replace(".graph", "")
        name = params.get("name", "").strip() or graph_id
        description = params.get("description", "")
        relative_path = params.get("_relative_path", file_path.name)
        db_path_prefix = params.get("_db_path_prefix", "/workspace")
        db_path = f"{db_path_prefix}/{relative_path}"

        # overwrite 场景：删除旧文件，确保全新初始化
        if file_path.exists():
            file_path.unlink()

        try:
            _create_graph_db_tables(
                file_path=file_path,
                graph_id=graph_id,
                name=name,
                description=description,
                db_path=db_path,
            )
        except Exception:
            # 清理残留的半成品文件
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass
            raise

        return FileInitResult(
            file_path=file_path,
            size=file_path.stat().st_size,
            meta={
                "id": graph_id,
                "name": name,
                "description": description,
                "resource_type": "graph",
                "renderer_hint": "knowledge_graph_preview",
            },
        )


# ---------------------------------------------------------------------------
# 内部辅助函数（从 workspaces_resources_files.py 提取）
# ---------------------------------------------------------------------------


def _write_knowledge_db_metadata(
    *,
    file_path: Path,
    kb_id: str,
    name: str,
    description: str,
    db_path: str = "",
) -> None:
    """写入知识库 SQLite metadata。"""
    try:
        with sqlite3.connect(str(file_path)) as conn:
            conn.execute("PRAGMA journal_mode = DELETE")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _aiasys_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            metadata = {
                "id": kb_id,
                "knowledge_base_id": kb_id,
                "name": name,
                "description": description,
                "resource_type": "knowledge",
                "renderer_hint": "knowledge_base_preview",
            }
            if db_path:
                metadata["db_path"] = db_path
            for key, value in metadata.items():
                conn.execute(
                    "INSERT OR REPLACE INTO _aiasys_metadata (key, value) VALUES (?, ?)",
                    (key, value),
                )
            conn.commit()
    except sqlite3.Error as exc:
        raise RuntimeError(f"写入知识库文件 metadata 失败: {exc}") from exc


def _create_graph_db_tables(
    *,
    file_path: Path,
    graph_id: str,
    name: str,
    description: str,
    db_path: str = "",
) -> None:
    """创建知识图谱 SQLite 表结构并写入初始 metadata。"""
    try:
        with sqlite3.connect(str(file_path)) as conn:
            conn.execute("PRAGMA journal_mode = DELETE")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _aiasys_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
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
            conn.execute(
                "INSERT OR REPLACE INTO _aiasys_metadata (key, value) VALUES (?, ?)",
                ("id", graph_id),
            )
            conn.execute(
                "INSERT OR REPLACE INTO _aiasys_metadata (key, value) VALUES (?, ?)",
                ("resource_type", "graph"),
            )
            conn.execute(
                "INSERT OR REPLACE INTO _aiasys_metadata (key, value) VALUES (?, ?)",
                ("renderer_hint", "knowledge_graph_preview"),
            )
            if db_path:
                conn.execute(
                    "INSERT OR REPLACE INTO _aiasys_metadata (key, value) VALUES (?, ?)",
                    ("db_path", db_path),
                )
            conn.execute(
                "INSERT OR REPLACE INTO graph_metadata (key, value) VALUES (?, ?)",
                ("name", name),
            )
            if description:
                conn.execute(
                    "INSERT OR REPLACE INTO graph_metadata (key, value) VALUES (?, ?)",
                    ("description", description),
                )
            conn.commit()
    except sqlite3.Error as exc:
        raise RuntimeError(f"创建知识图谱数据库失败: {exc}") from exc


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class FileInitializerRegistry:
    """文件类型初始化器注册表。

    使用方式：
        registry = get_file_initializer_registry()
        initializer = registry.get("knowledge_base")
        result = initializer.initialize(file_path, params)
    """

    def __init__(self) -> None:
        self._by_type: dict[str, FileInitializer] = {}
        self._by_extension: dict[str, FileInitializer] = {}
        self._text_initializer: TextFileInitializer | None = None

    def register(self, initializer: FileInitializer) -> None:
        """注册一个初始化器。"""
        self._by_type[initializer.file_type] = initializer

        if isinstance(initializer, TextFileInitializer):
            self._text_initializer = initializer
            for suffix in initializer.suffix_set:
                self._by_extension[suffix] = initializer
        else:
            self._by_extension[initializer.file_extension] = initializer

    def get(self, file_type: str) -> FileInitializer:
        """按 file_type 查找初始化器。

        Raises:
            KeyError: 未找到对应的初始化器。
        """
        if file_type not in self._by_type:
            raise KeyError(f"未知的文件类型: {file_type}")
        return self._by_type[file_type]

    def guess_from_path(self, path: str | Path) -> FileInitializer | None:
        """根据文件路径后缀推断初始化器。

        Returns:
            匹配的初始化器，或 None（后缀无法识别时）。
        """
        suffix = Path(str(path)).suffix.lower()
        # 先精确匹配（如 .kb.db）
        if suffix in self._by_extension:
            return self._by_extension[suffix]
        # 检查双后缀（如 .graph.db, .table.db, .kb.db）
        path_str = str(path).lower()
        for ext, init in self._by_extension.items():
            if path_str.endswith(ext):
                return init
        return None

    def list_all(self) -> list[FileInitializer]:
        """列出所有已注册的初始化器。"""
        return list(self._by_type.values())

    def get_file_types_for_ui(self) -> list[dict[str, str]]:
        """返回前端"新建文件"对话框所需的文件类型列表。"""
        result: list[dict[str, str]] = []
        for init in self._by_type.values():
            result.append(
                {
                    "file_type": init.file_type,
                    "display_name": init.display_name,
                    "file_extension": init.file_extension,
                }
            )
        return result


# 模块级单例
_registry: FileInitializerRegistry | None = None


def get_file_initializer_registry() -> FileInitializerRegistry:
    """获取 FileInitializerRegistry 单例。"""
    global _registry
    if _registry is None:
        _registry = FileInitializerRegistry()
        _registry.register(TextFileInitializer())
        _registry.register(CanvasFileInitializer())
        _registry.register(KnowledgeBaseInitializer())
        _registry.register(KnowledgeGraphInitializer())
    return _registry
