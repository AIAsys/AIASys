"""Codex 风格 memory 文件布局。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.services.memory.constants import (
    MEMORY_FILE_NAME,
    MEMORY_SUMMARY_FILE_NAME,
    RAW_MEMORIES_FILE_NAME,
    ROLLOUT_SUMMARIES_DIR_NAME,
)
from app.services.memory.store import MemoryStore
from app.utils.path_utils import as_system_path


@dataclass(frozen=True)
class MemoryLayout:
    """用户默认层 memory 根目录下的固定文件布局。"""

    root: Path
    memory: Path
    summary: Path
    raw_memories: Path
    rollout_summaries: Path


def get_memory_layout(root: Path) -> MemoryLayout:
    """返回 Codex 风格 memory layout，不产生文件系统副作用。"""
    root = Path(root)
    return MemoryLayout(
        root=root,
        memory=root / MEMORY_FILE_NAME,
        summary=root / MEMORY_SUMMARY_FILE_NAME,
        raw_memories=root / RAW_MEMORIES_FILE_NAME,
        rollout_summaries=root / ROLLOUT_SUMMARIES_DIR_NAME,
    )


def ensure_memory_layout(root: Path) -> MemoryLayout:
    """确保用户默认层 memory 目录和可读镜像文件存在。"""
    import logging

    logger = logging.getLogger(__name__)
    layout = get_memory_layout(root)
    os.makedirs(as_system_path(layout.root), exist_ok=True)
    os.makedirs(as_system_path(layout.rollout_summaries), exist_ok=True)
    # memory/summary 走 MemoryStore，通过安全扫描与 Windows 长路径前缀
    MemoryStore(layout.memory).initialize()
    MemoryStore(layout.summary).initialize()
    # raw_memories 是内部镜像，可跳过安全扫描路径
    if not os.path.exists(as_system_path(layout.raw_memories)):
        logger.info("重建 raw memories 占位文件: %s", layout.raw_memories)
        Path(as_system_path(layout.raw_memories)).write_text("# Raw Memories\n\nNo raw memories yet.\n", encoding="utf-8")
    return layout
