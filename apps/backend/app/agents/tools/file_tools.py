"""通用文件读写工具。

本模块是 ReadFile / WriteFile / StrReplaceFile 的当前注册入口。
工具实现按读写职责拆到子模块，共享路径解析 helper 放在 file_tools_base，
文件类型限制 helper 放在 file_tools_restrictions 以避免循环导入。
"""

from __future__ import annotations

from pathlib import Path

MAX_LINES = 1000
MAX_LINE_LENGTH = 2000
MAX_BYTES = 100 << 10  # 100KB
MEDIA_SNIFF_BYTES = 8192


# 常见非文本文件扩展名（不区分大小写）。
# 被此集合命中的文件会被 ReadFile 直接拒绝，并给出具体的替代建议。
# 为了保持向后兼容，仍从 file_tools_restrictions 导出。
from .file_tools_restrictions import (
    _NON_TEXT_SUFFIXES,
    _WRITE_DISCOURAGED_SUFFIXES,
    _get_non_text_hint,
    _get_write_discouraged_hint,
    _is_non_text_by_suffix,
    _is_write_discouraged_by_suffix,
)


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
from .file_tools_read import (  # noqa: E402, F401
    ReadFile,
    ReadFileParams,
)
from .file_tools_write import (  # noqa: E402, F401
    FileEdit,
    StrReplaceFile,
    StrReplaceFileParams,
    WriteFile,
    WriteFileParams,
    _append_text,
)
