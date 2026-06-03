"""通用文件读写工具。

本模块是 ReadFile / WriteFile / StrReplaceFile 的当前注册入口。
工具实现按读写职责拆到子模块，共享路径解析 helper 放在 file_tools_base。
"""

from __future__ import annotations

from pathlib import Path

MAX_LINES = 1000
MAX_LINE_LENGTH = 2000
MAX_BYTES = 100 << 10  # 100KB
MEDIA_SNIFF_BYTES = 8192


# 常见非文本文件扩展名（不区分大小写）。
# 被此集合命中的文件会被 ReadFile 直接拒绝，并给出具体的替代建议。
_NON_TEXT_SUFFIXES = frozenset({
    # Office
    ".xlsx",
    ".xls",
    ".xlsm",
    ".docx",
    ".doc",
    ".pptx",
    ".ppt",
    # PDF
    ".pdf",
    # 压缩
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    # 图片（SVG 是文本，不在此列）
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".webp",
    ".ico",
    ".tiff",
    ".tif",
    # 视频
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".flv",
    ".wmv",
    # 音频
    ".mp3",
    ".wav",
    ".flac",
    ".aac",
    ".ogg",
    ".wma",
    # 可执行 / 库
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    # 数据库
    ".db",
    ".sqlite",
    ".sqlite3",
    # 其他设计 / 二进制格式
    ".psd",
    ".ai",
    ".sketch",
})


def _is_binary_file(path: Path) -> bool:
    """通过检查文件头是否包含 NUL 字节判断是否为二进制文件。"""
    try:
        with path.open("rb") as f:
            header = f.read(MEDIA_SNIFF_BYTES)
    except Exception:
        return False
    return b"\x00" in header


def _is_non_text_by_suffix(path: Path) -> bool:
    """通过文件扩展名判断是否为已知的非文本文件。"""
    return path.suffix.lower() in _NON_TEXT_SUFFIXES


def _get_non_text_hint(path: Path) -> str:
    """根据文件扩展名返回文件类型描述和替代建议。"""
    suffix = path.suffix.lower()
    name = path.name

    if suffix in (".xlsx", ".xls", ".xlsm"):
        return (
            f"`{name}` 是 Excel 表格文件，ReadFile 不能直接读取。"
            "如需查看内容，请用 Shell 工具运行 Python（如 pandas / openpyxl）将其转为文本格式。"
        )
    if suffix == ".pdf":
        return (
            f"`{name}` 是 PDF 文件，ReadFile 不能直接读取。"
            "如需提取文本，请用 Shell 工具运行 Python（如 PyPDF2 / pdfplumber）提取。"
        )
    if suffix in (".docx", ".doc", ".pptx", ".ppt"):
        return (
            f"`{name}` 是 Office 文档，ReadFile 不能直接读取。"
            "如需提取文本，请用 Shell 工具运行 Python（如 python-docx）提取。"
        )
    if suffix in (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"):
        return (
            f"`{name}` 是压缩文件，ReadFile 不能直接读取。"
            "如需查看内容，请用 Shell 工具的 `unzip` / `tar` 命令解压后再读取。"
        )
    if suffix in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".tiff", ".tif"):
        return (
            f"`{name}` 是图片文件，ReadFile 不能直接读取。"
            "请使用 ReadMediaFile 工具查看图片内容。"
        )
    if suffix in (".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv"):
        return (
            f"`{name}` 是视频文件，ReadFile 不能直接读取。"
            "请使用 ReadMediaFile 工具查看视频内容。"
        )
    if suffix in (".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma"):
        return f"`{name}` 是音频文件，当前不支持直接读取音频内容。"
    if suffix in (".exe", ".dll", ".so", ".dylib", ".bin"):
        return f"`{name}` 是可执行或库文件，ReadFile 不支持读取。"
    if suffix in (".db", ".sqlite", ".sqlite3"):
        return (
            f"`{name}` 是数据库文件，ReadFile 不支持读取。"
            "如需查看内容，请用 Shell 工具的 sqlite3 命令查询。"
        )
    return f"`{name}` 是非文本文件，ReadFile 只能读取纯文本文件。"


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
