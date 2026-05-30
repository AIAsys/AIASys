"""
工作区文件树与文件访问配置模型。

硬编码默认值作为兜底，配置文件 .aiasys/file-tree-config.json 用于覆盖。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONFIG_FILE_NAME = "file-tree-config.json"

# =============================================================================
# 硬编码默认值（配置文件不存在或被删时兜底）
# =============================================================================

DEFAULT_HIDDEN_PATTERNS: list[str] = [
    # .aiasys 下不应对用户和 Agent 暴露的内部目录
    ".aiasys/session",
    ".aiasys/session/**",
    ".aiasys/file-history",
    ".aiasys/file-history/**",
    ".aiasys/.memory/state.db",
    ".aiasys/.memory/*.lock",
    ".aiasys/.memory/*.snapshots.json",
    ".aiasys/memory/*.lock",
    ".aiasys/workspace",
    ".aiasys/workspace/**",
    # 隐藏标记文件
    "**/__aiasys_folder__.md",
    # SQLite 临时文件
    "*-shm",
    "**/*-shm",
    "*-wal",
    "**/*-wal",
    "*-journal",
    "**/*-journal",
]

DEFAULT_INTERNAL_ROOT_FILES: list[str] = [
    ".cleanup_marker",
    "metadata.json",
    "history.json",
    "file_snapshots.json",
]

DEFAULT_INTERNAL_SESSION_DIRS: list[str] = [
    ".aiasys",
    ".env",
    "env",
]

DEFAULT_INTERNAL_SESSION_FILES: list[str] = [
    ".cleanup_marker",
    "metadata.json",
    "history.json",
    "file_snapshots.json",
]

DEFAULT_BLOCKED_SUBDIRS: list[str] = [
    ".aiasys/session",
    ".aiasys/.memory",
]

DEFAULT_EDITABLE_EXTENSIONS: list[str] = [
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
    ".ipynb",
    ".canvas",
]


# =============================================================================
# 配置读写
# =============================================================================


class FileTreeConfig:
    """工作区文件树配置，从 .aiasys/file-tree-config.json 读取。"""

    def __init__(
        self,
        *,
        hidden_patterns: list[str] | None = None,
        internal_root_files: list[str] | None = None,
        internal_session_dirs: list[str] | None = None,
        internal_session_files: list[str] | None = None,
        blocked_subdirs: list[str] | None = None,
        editable_extensions: list[str] | None = None,
    ):
        self.hidden_patterns = hidden_patterns or list(DEFAULT_HIDDEN_PATTERNS)
        self.internal_root_files = internal_root_files or list(DEFAULT_INTERNAL_ROOT_FILES)
        self.internal_session_dirs = internal_session_dirs or list(DEFAULT_INTERNAL_SESSION_DIRS)
        self.internal_session_files = internal_session_files or list(DEFAULT_INTERNAL_SESSION_FILES)
        self.blocked_subdirs = blocked_subdirs or list(DEFAULT_BLOCKED_SUBDIRS)
        self.editable_extensions = editable_extensions or list(DEFAULT_EDITABLE_EXTENSIONS)

    @staticmethod
    def defaults() -> FileTreeConfig:
        return FileTreeConfig()

    def to_dict(self) -> dict[str, Any]:
        return {
            "_schema_version": 1,
            "hidden_patterns": self.hidden_patterns,
            "internal_root_files": self.internal_root_files,
            "internal_session_dirs": self.internal_session_dirs,
            "internal_session_files": self.internal_session_files,
            "blocked_subdirs": self.blocked_subdirs,
            "editable_extensions": self.editable_extensions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileTreeConfig:
        return cls(
            hidden_patterns=_read_str_list(data, "hidden_patterns"),
            internal_root_files=_read_str_list(data, "internal_root_files"),
            internal_session_dirs=_read_str_list(data, "internal_session_dirs"),
            internal_session_files=_read_str_list(data, "internal_session_files"),
            blocked_subdirs=_read_str_list(data, "blocked_subdirs"),
            editable_extensions=_read_str_list(data, "editable_extensions"),
        )


def _read_str_list(data: dict[str, Any], key: str) -> list[str] | None:
    value = data.get(key)
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return None


def get_config_path(workspace_dir: Path) -> Path:
    return workspace_dir / ".aiasys" / CONFIG_FILE_NAME


def ensure_config(workspace_dir: Path) -> FileTreeConfig:
    """确保配置文件存在，不存在时写入默认值。返回当前生效配置。"""
    config_path = get_config_path(workspace_dir)
    if config_path.exists():
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return FileTreeConfig.from_dict(payload)
        except (json.JSONDecodeError, Exception):
            logger.warning("文件树配置文件损坏，重建默认配置: %s", config_path)

    config = FileTreeConfig.defaults()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("已创建默认文件树配置: %s", config_path)
    return config


def read_config(workspace_dir: Path) -> FileTreeConfig:
    """读取配置，文件不存在时返回硬编码默认值（不自动创建文件）。"""
    config_path = get_config_path(workspace_dir)
    if not config_path.exists():
        return FileTreeConfig.defaults()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return FileTreeConfig.from_dict(payload)
    except (json.JSONDecodeError, Exception):
        logger.warning("文件树配置文件损坏，使用默认值: %s", config_path)
    return FileTreeConfig.defaults()
