"""Codex 风格 memory 文件布局。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.memory.constants import (
    MEMORY_FILE_NAME,
    MEMORY_SUMMARY_FILE_NAME,
    RAW_MEMORIES_FILE_NAME,
    ROLLOUT_SUMMARIES_DIR_NAME,
)


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
    layout.root.mkdir(parents=True, exist_ok=True)
    layout.rollout_summaries.mkdir(parents=True, exist_ok=True)
    if not layout.memory.exists():
        logger.info("重建空的 memory 文件: %s", layout.memory)
        layout.memory.write_text("", encoding="utf-8")
    if not layout.summary.exists():
        logger.info("重建空的 memory summary 文件: %s", layout.summary)
        layout.summary.write_text("", encoding="utf-8")
    if not layout.raw_memories.exists():
        logger.info("重建 raw memories 占位文件: %s", layout.raw_memories)
        layout.raw_memories.write_text("# Raw Memories\n\nNo raw memories yet.\n", encoding="utf-8")
    return layout
