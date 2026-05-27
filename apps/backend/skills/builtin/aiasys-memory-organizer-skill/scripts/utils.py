"""Shared utilities for memory-organizer skill scripts.

只提供文件操作工具，不调用 LLM。
整理逻辑由读取 SKILL.md 的 Agent 自行完成。
"""

from __future__ import annotations

import difflib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


def get_workspace_root() -> Path:
    """从环境变量获取工作区根目录。"""
    ws_root = os.environ.get("AIASYS_WORKSPACE_ROOT", "")
    if ws_root:
        return Path(ws_root).resolve()
    raise RuntimeError("无法确定工作区根目录：缺少 AIASYS_WORKSPACE_ROOT 环境变量")


def get_global_memory_dir(workspace_root: Path | str) -> Path:
    """从工作区根目录推导出全局 memory 目录。"""
    workspace_root = Path(workspace_root)
    user_dir = workspace_root.parent
    return user_dir / "global_workspace" / ".aiasys" / ".memory"


def get_workspace_memory_dir(workspace_root: Path | str) -> Path:
    """返回工作区层 memory 目录。"""
    return Path(workspace_root) / ".aiasys" / "memory"


def resolve_memory_paths(workspace_root: Path | str) -> dict[str, Path]:
    """解析所有 memory 文件路径，返回 {target: path} 字典。"""
    workspace_root = Path(workspace_root)
    global_dir = get_global_memory_dir(workspace_root)
    ws_dir = get_workspace_memory_dir(workspace_root)
    return {
        "memory": global_dir / "MEMORY.md",
        "summary": global_dir / "memory_summary.md",
        "raw": global_dir / "raw_memories.md",
        "rollout_dir": global_dir / "rollout_summaries",
        "workspace": ws_dir / "workspace_memory.md",
    }


def read_text_file(path: Path, default: str = "") -> str:
    """安全读取文本文件。"""
    try:
        if path.exists():
            return path.read_text(encoding="utf-8")
    except Exception:
        pass
    return default


def atomic_write_file(path: Path, content: str) -> None:
    """原子写入：临时文件 + fsync + os.replace。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
        if os.name != "nt":
            try:
                dir_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
    except Exception:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def backup_file(path: Path) -> Path | None:
    """创建带时间戳的备份文件，返回备份路径；文件不存在时返回 None。"""
    if not path.exists():
        return None
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_suffix(f"{path.suffix}.backup-{timestamp}")
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup_path


def generate_diff_report(original: str, new: str, target_name: str) -> dict[str, Any]:
    """生成 diff 报告，返回结构化数据。"""
    original_lines = original.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = list(
        difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"{target_name}-original",
            tofile=f"{target_name}-new",
            lineterm="",
        )
    )

    added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))

    return {
        "target": target_name,
        "original_size": len(original),
        "new_size": len(new),
        "size_delta": len(new) - len(original),
        "lines_added": added,
        "lines_removed": removed,
        "diff": "\n".join(diff),
    }


def json_output(data: dict[str, Any]) -> None:
    """输出 JSON 到 stdout。"""
    print(json.dumps(data, ensure_ascii=False, indent=2))


def error_output(message: str) -> None:
    """输出错误 JSON 到 stdout 并退出。"""
    print(json.dumps({"error": message}, ensure_ascii=False))
