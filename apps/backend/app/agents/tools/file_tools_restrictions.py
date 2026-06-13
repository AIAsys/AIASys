"""文件类型限制共享 helper。

供 ReadFile / WriteFile / StrReplaceFile 共用，避免循环导入。
"""

from __future__ import annotations

import re
from pathlib import Path


# 常见非文本文件扩展名（不区分大小写）。
# 被此集合命中的文件会被 ReadFile 直接拒绝，并给出具体的替代建议。
_NON_TEXT_SUFFIXES: frozenset[str] = frozenset(
    {
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
    }
)


# WriteFile / StrReplaceFile 不应直接处理的文件扩展名。
# 包含所有已知非文本格式，以及有专属工具的文本格式（如 .ipynb → ManageNotebook）。
_WRITE_DISCOURAGED_SUFFIXES: frozenset[str] = frozenset(
    {
        ".ipynb",  # Jupyter Notebook：应使用 ManageNotebook
    }
    | _NON_TEXT_SUFFIXES
)


def _is_non_text_by_suffix(path: Path) -> bool:
    """通过文件扩展名判断是否为已知的非文本文件。"""
    return path.suffix.lower() in _NON_TEXT_SUFFIXES


def _is_write_discouraged_by_suffix(path: Path) -> bool:
    """通过文件扩展名判断是否为 WriteFile / StrReplaceFile 不应直接写入的文件。"""
    return path.suffix.lower() in _WRITE_DISCOURAGED_SUFFIXES


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
            f"`{name}` 是图片文件，ReadFile 不能直接读取。请使用 ReadMediaFile 工具查看图片内容。"
        )
    if suffix in (".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv"):
        return (
            f"`{name}` 是视频文件，ReadFile 不能直接读取。请使用 ReadMediaFile 工具查看视频内容。"
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


def _get_write_discouraged_hint(path: Path) -> str:
    """根据文件扩展名返回 WriteFile / StrReplaceFile 的拒绝提示。"""
    suffix = path.suffix.lower()
    name = path.name

    if suffix == ".ipynb":
        return (
            f"`{name}` 是 Jupyter Notebook 文件，WriteFile 不能直接写入。"
            "请使用 ManageNotebook 工具创建、读取或编辑 Notebook。"
        )
    if suffix in (".xlsx", ".xls", ".xlsm"):
        return f"`{name}` 是 Excel 表格文件，WriteFile 不能直接写入。请用 Shell 工具运行 Python（如 pandas / openpyxl）生成。"
    if suffix == ".pdf":
        return f"`{name}` 是 PDF 文件，WriteFile 不能直接写入。请用 Shell 工具运行 Python 生成 PDF。"
    if suffix in (".docx", ".doc", ".pptx", ".ppt"):
        return f"`{name}` 是 Office 文档，WriteFile 不能直接写入。请用 Shell 工具运行 Python（如 python-docx）生成。"
    if suffix in (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"):
        return f"`{name}` 是压缩文件，WriteFile 不能直接写入。请用 Shell 工具的 `zip` / `tar` 命令生成。"
    if suffix in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".tiff", ".tif"):
        return f"`{name}` 是图片文件，WriteFile 不能直接写入。请使用图片生成工具或 Shell 命令创建。"
    if suffix in (".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv"):
        return f"`{name}` 是视频文件，WriteFile 不能直接写入。请使用视频处理工具或 Shell 命令创建。"
    if suffix in (".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma"):
        return f"`{name}` 是音频文件，WriteFile 不能直接写入。请使用音频处理工具或 Shell 命令创建。"
    if suffix in (".exe", ".dll", ".so", ".dylib", ".bin"):
        return f"`{name}` 是可执行或库文件，WriteFile 不能直接写入。"
    if suffix in (".db", ".sqlite", ".sqlite3"):
        return f"`{name}` 是数据库文件，WriteFile 不能直接写入。请用数据库工具或 Shell 操作。"
    return f"`{name}` 是非文本文件，WriteFile 只能写入纯文本文件。"


# ---------------------------------------------------------------------------
# .gitignore 风格敏感文件模式
# ---------------------------------------------------------------------------

# 敏感文件/目录模式。语法接近 .gitignore：
# - `*` 匹配任意字符（不含 `/`）
# - `?` 匹配单个字符
# - `**` 匹配零个或多个目录层级
# - 无 `/` 的模式匹配任意路径段的文件名
# - 以 `/` 开头的模式相对于工作区根目录锚定
_SENSITIVE_FILE_PATTERNS: tuple[str, ...] = (
    # 环境变量/密钥文件
    ".env",
    ".env.*",
    # 密钥 / 证书 / 凭据
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12",
    "id_rsa",
    "id_rsa.*",
    "id_ed25519",
    "id_ed25519.*",
    "id_ecdsa",
    "id_ecdsa.*",
    "id_dsa",
    "id_dsa.*",
    # git / net / 云服务凭据
    ".git-credentials",
    ".netrc",
    ".pypirc",
    # SSH / AWS / Docker 配置
    ".ssh/**",
    ".aws/credentials",
    ".aws/config",
    ".docker/config.json",
    # 移动/通用密钥库
    "*.keystore",
    "keystore*",
    # 常见凭据 JSON
    "credentials.json",
    "service_account*.json",
    "client_secret*.json",
)


def _compile_gitignore_pattern(pattern: str) -> re.Pattern[str]:
    """把 .gitignore 风格模式编译成正则表达式。

    支持：
    - `*` 匹配除 `/` 外任意字符序列
    - `?` 匹配单个字符（除 `/`）
    - `**` 匹配零个或多个目录层级
    - 前导 `/` 锚定到根目录
    - 其他字符原义匹配（含 `.`）
    """
    original = pattern
    anchored = pattern.startswith("/")
    if anchored:
        pattern = pattern[1:]

    # 转义普通字符，但保留 *、?、** 语义
    # 先把 ** 替换为占位符，避免被 * 规则覆盖
    placeholder = "\x00"
    pattern = pattern.replace("**", placeholder)

    parts: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            parts.append("[^/]*")
            i += 1
        elif ch == "?":
            parts.append("[^/]")
            i += 1
        elif ch == placeholder:
            parts.append(".*")
            i += 1
        else:
            parts.append(re.escape(ch))
            i += 1

    regex = "".join(parts)

    if anchored:
        regex = f"^{regex}"
    else:
        # 无斜杠：匹配任意路径段的文件名或整个路径。
        # 例如 `.env` 应匹配 `.env`、`.env.local`、`config/.env`。
        # 策略：在段边界后开始匹配。
        regex = f"(?:^|/){regex}"

    # 目录模式（以 `/` 结尾）匹配该目录及其内容
    if original.endswith("/"):
        # 目录模式：匹配该目录以及目录下任意内容
        regex = f"{regex.rstrip('/')}(?:/.*)?$"
    else:
        # 文件模式：匹配到路径末尾
        regex = f"{regex}$"

    return re.compile(regex, re.IGNORECASE)


# 预编译所有模式以提高性能
_SENSITIVE_FILE_REGEXES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (pat, _compile_gitignore_pattern(pat)) for pat in _SENSITIVE_FILE_PATTERNS
)


def _match_sensitive_file_pattern(path: Path) -> str | None:
    """检查路径是否命中敏感文件模式。

    返回命中的模式字符串；未命中返回 None。
    """
    # 使用相对路径（若可能）和文件名进行匹配
    rel = path.as_posix()
    for pattern, regex in _SENSITIVE_FILE_REGEXES:
        if regex.search(rel):
            return pattern
    return None


# ---------------------------------------------------------------------------
# Magic-byte 文件类型检测
# ---------------------------------------------------------------------------

# 文件签名 -> (类型名, 读取建议)
# 用于在扩展名不可信或缺失时识别二进制文件。
_MAGIC_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    # 文档 / 压缩
    (b"%PDF", "PDF", "如需提取文本，请用 Shell 工具运行 Python（如 PyPDF2 / pdfplumber）提取。"),
    (b"PK\x03\x04", "ZIP/Office", "这是 Office/压缩文件，请用 Shell 工具的 `unzip` / 对应库读取。"),
    (b"PK\x05\x06", "ZIP（空归档）", "这是压缩文件，请用 Shell 工具的 `unzip` 读取。"),
    (b"PK\x07\x08", "ZIP", "这是压缩文件，请用 Shell 工具的 `unzip` 读取。"),
    (b"Rar!", "RAR", "这是 RAR 压缩文件，请用 Shell 工具解压后读取。"),
    (b"7z\xbc\xaf'\x1c", "7z", "这是 7z 压缩文件，请用 Shell 工具解压后读取。"),
    (b"\x1f\x8b", "gzip", "这是 gzip 压缩文件，请用 Shell 工具解压后读取。"),
    (b"BZh", "bzip2", "这是 bzip2 压缩文件，请用 Shell 工具解压后读取。"),
    (b"\xfd7zXZ", "xz", "这是 xz 压缩文件，请用 Shell 工具解压后读取。"),
    (b"ustar\x00", "tar", "这是 tar 归档文件，请用 Shell 工具 `tar` 读取。"),
    (b"ustar ", "tar", "这是 tar 归档文件，请用 Shell 工具 `tar` 读取。"),
    # 图片
    (b"\x89PNG\r\n\x1a\n", "PNG", "请使用 ReadMediaFile 工具查看图片内容。"),
    (b"\xff\xd8\xff", "JPEG", "请使用 ReadMediaFile 工具查看图片内容。"),
    (b"GIF87a", "GIF", "请使用 ReadMediaFile 工具查看图片内容。"),
    (b"GIF89a", "GIF", "请使用 ReadMediaFile 工具查看图片内容。"),
    (b"BM", "BMP", "请使用 ReadMediaFile 工具查看图片内容。"),
    (b"RIFF", "WEBP/RIFF", "请使用 ReadMediaFile 工具查看图片内容。"),
    # 视频 / 音频
    (b"\x00\x00\x00\x14ftyp", "MP4", "请使用 ReadMediaFile 工具查看视频内容。"),
    (b"\x00\x00\x00\x18ftyp", "MP4", "请使用 ReadMediaFile 工具查看视频内容。"),
    (b"\x00\x00\x00\x20ftyp", "MP4", "请使用 ReadMediaFile 工具查看视频内容。"),
    (b"ID3", "MP3", "当前不支持直接读取音频内容。"),
    # 可执行 / 库
    (b"MZ", "Windows 可执行文件", "ReadFile 不支持读取可执行文件。"),
    (b"\x7fELF", "ELF", "ReadFile 不支持读取可执行/库文件。"),
    (b"\xcf\xfa\xed\xfe", "Mach-O", "ReadFile 不支持读取可执行/库文件。"),
    (b"\xfe\xed\xfa\xcf", "Mach-O", "ReadFile 不支持读取可执行/库文件。"),
    (b"\xca\xfe\xba\xbe", "Mach-O（通用二进制）", "ReadFile 不支持读取可执行/库文件。"),
    # 数据库
    (b"SQLite format 3", "SQLite", "如需查看内容，请用 Shell 工具的 sqlite3 命令查询。"),
)


def _detect_file_type_by_magic(path: Path) -> tuple[str, str] | None:
    """通过文件头 magic byte 识别文件类型。

    返回 (类型名, 建议说明)；无法识别返回 None。
    """
    try:
        with path.open("rb") as f:
            header = f.read(32)
    except Exception:
        return None
    if not header:
        return None

    for signature, name, hint in _MAGIC_SIGNATURES:
        if len(signature) > len(header):
            continue
        if signature == header[: len(signature)]:
            return name, hint

    # MP4 / ftyp 类：offset 4 处为 "ftyp"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "MP4", "请使用 ReadMediaFile 工具查看视频内容。"

    return None


def _is_binary_by_magic(path: Path) -> bool:
    """通过 magic byte 判断是否为已知二进制格式。"""
    return _detect_file_type_by_magic(path) is not None
