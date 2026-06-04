"""Skill 目录指纹计算。

用于检测工作区副本是否被本地修改，以及源是否有更新。
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


META_FILE_NAME = ".aiasys-skill-meta.json"


def compute_directory_fingerprint(directory: Path) -> str:
    """计算目录内容指纹。

    递归遍历目录下所有文件，各自 SHA256，按相对路径排序后拼接，
    再算一次总 SHA256。

    跳过：
    - 隐藏文件/目录（以 . 开头）
    - 元数据文件 .aiasys-skill-meta.json
    - 符号链接（避免循环引用）

    只认文件内容，不认权限/时间戳。
    """
    hashes: list[str] = []
    for file_path in sorted(directory.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.name.startswith("."):
            continue
        if file_path.name == META_FILE_NAME:
            continue
        if file_path.is_symlink():
            continue
        try:
            relative = file_path.relative_to(directory).as_posix()
            file_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
            hashes.append(f"{relative}:{file_hash}")
        except Exception:
            logger.warning("Failed to compute hash for %s: %s", file_path, exc_info=True)
            continue

    combined = "\n".join(hashes)
    return hashlib.sha256(combined.encode()).hexdigest()
