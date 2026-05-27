"""通用文件读写工具。

本模块是 ReadFile / WriteFile / StrReplaceFile 的当前注册入口。
工具实现按读写职责拆到子模块，共享路径解析 helper 放在 file_tools_base。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .file_tools_base import (
    _resolve_file_path,
    _resolve_global_workspace_root,
    _resolve_session_root,
    _resolve_workspace_root,
)

MAX_LINES = 1000
MAX_LINE_LENGTH = 2000
MAX_BYTES = 100 << 10  # 100KB
MEDIA_SNIFF_BYTES = 8192


def _is_binary_file(path: Path) -> bool:
    """通过检查文件头是否包含 NUL 字节判断是否为二进制文件。"""
    try:
        with path.open("rb") as f:
            header = f.read(MEDIA_SNIFF_BYTES)
    except Exception:
        return False
    return b"\x00" in header


def _truncate_line(line: str, max_len: int = MAX_LINE_LENGTH) -> str:
    if len(line) <= max_len:
        return line
    return line[:max_len] + "\n...[line truncated]\n"


# 延迟导入避免循环引用
from .file_tools_read import ReadFileParams, ReadFile  # noqa: E402
from .file_tools_write import (  # noqa: E402, F401
    FileEdit,
    StrReplaceFileParams,
    StrReplaceFile,
    WriteFileParams,
    WriteFile,
    _append_text,
)
