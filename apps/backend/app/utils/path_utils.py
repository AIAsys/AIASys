"""路径工具，主要处理 Windows 长路径前缀。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def normalize_windows_long_path(path: Path | str) -> str:
    r"""在 Windows 下为绝对路径自动添加 \\?\ 前缀以绕过 MAX_PATH。

    返回字符串可直接用于 open() / os.* / shutil.* 等系统 IO API。

    规则：
    - 非 Windows 平台原样返回。
    - 已经是 \\?\ 或 \\?\UNC\ 前缀的原样返回。
    - 相对路径不添加前缀（Windows 长路径前缀只支持绝对路径）。
    - 路径会先 resolve() 并转反斜杠，去掉尾部反斜杠。
    - 长度 <= 240 时不加前缀，避免无端污染常规路径。
    """
    raw = str(path)

    if sys.platform != "win32":
        return raw

    if raw.startswith("\\\\?\\") or raw.startswith("\\\\?\\UNC\\"):
        return raw

    resolved = Path(raw).resolve()
    if not resolved.is_absolute():
        return raw

    abs_path = os.path.abspath(resolved)
    norm = abs_path.replace("/", "\\").rstrip("\\")

    if len(norm) <= 240:
        return norm

    return f"\\\\?\\{norm}"


def as_system_path(path: Path | str) -> str:
    """即将交给系统 IO 时使用的路径字符串。"""
    return normalize_windows_long_path(path)
