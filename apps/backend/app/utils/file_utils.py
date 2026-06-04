"""
文件工具模块

用于文件监控和内容读取
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class FileSnapshot:
    """文件快照"""

    path: str  # 相对路径
    size: int
    mtime: float


# 文本文件扩展名列表
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
    ".html",
    ".css",
    ".scss",
    ".less",
    ".xml",
    ".ini",
    ".conf",
    ".sh",
    ".bash",
    ".zsh",
    ".sql",
    ".log",
}

# 系统内部文件/目录列表（不应显示给用户，也不应包含在文件变更事件中）
SYSTEM_FILES: Set[str] = {
    ".cleanup_marker",
    "metadata.json",
    "history.json",
    "file_snapshots.json",
}

# 系统目录名（不应扫描）
SYSTEM_DIR_NAMES: Set[str] = {
    ".aiasys",
}

# 最大直接推送内容大小 (100KB)
MAX_CONTENT_SIZE = 100 * 1024


def is_text_file(path: str) -> bool:
    """判断是否为文本文件"""
    suffix = Path(path).suffix.lower()
    return suffix in TEXT_EXTENSIONS


async def scan_directory(workspace: Path) -> Dict[str, FileSnapshot]:
    """
    扫描目录，返回文件快照字典，自动忽略系统文件和目录

    Args:
        workspace: 工作目录路径

    Returns:
        {相对路径: FileSnapshot}
    """
    files = {}

    if not workspace.exists():
        return files

    for file_path in workspace.rglob("*"):
        if file_path.is_file():
            # 检查是否为系统文件
            if file_path.name in SYSTEM_FILES:
                continue

            # 检查绝对路径中是否包含屏蔽的目录部分
            try:
                rel_path = file_path.relative_to(workspace)
                parts = rel_path.parts

                # 如果任意目录部分为系统目录，则跳过
                is_system_dir = any(part in SYSTEM_DIR_NAMES for part in parts[:-1])

                if is_system_dir:
                    continue

                stat = file_path.stat()
                files[str(rel_path)] = FileSnapshot(
                    path=str(rel_path), size=stat.st_size, mtime=stat.st_mtime
                )
            except (ValueError, OSError):
                # 跳过无法访问的文件
                continue

    return files


def compare_files(
    before: Dict[str, FileSnapshot],
    after: Dict[str, FileSnapshot],
    workspace: Path,
) -> List[dict]:
    """
    对比两个文件快照，返回变更列表

    Args:
        before: 之前的快照
        after: 之后的快照
        workspace: 工作目录路径（用于读取内容）

    Returns:
        变更列表，包含 content 字段（如果是小文本文件）
    """
    changes = []

    # 检测新增和修改
    for path, info in after.items():
        event = None

        if path not in before:
            event = "created"
        elif before[path].mtime != info.mtime or before[path].size != info.size:
            event = "modified"

        if event:
            change = {
                "path": path,
                "event": event,
                "size": info.size,
                "modified": info.mtime,
                "is_text": is_text_file(path),
                "has_content": False,
            }

            # 小文本文件直接读取内容
            if change["is_text"] and info.size <= MAX_CONTENT_SIZE:
                try:
                    content = read_text_file(workspace / path)
                    if content is not None:
                        change["content"] = content
                        change["has_content"] = True
                except Exception:
                    pass  # 读取失败则不带内容

            changes.append(change)

    # 检测删除
    for path in before:
        if path not in after:
            changes.append(
                {
                    "path": path,
                    "event": "deleted",
                    "size": 0,
                    "modified": 0,
                    "is_text": False,
                    "has_content": False,
                }
            )

    return changes


def read_text_file(file_path: Path) -> Optional[str]:
    """
    读取文本文件内容

    Args:
        file_path: 文件绝对路径

    Returns:
        文件内容，失败返回 None
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None
