"""文件工具共享的路径解析 helper。

供 file_tools / file_tools_read / file_tools_write 等子模块共用，
避免循环导入。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from app.services.history import current_global_workspace, current_session_root, current_workspace


def _resolve_workspace_root() -> Path | None:
    workspace = current_workspace.get()
    if workspace:
        return Path(workspace)
    return None


def _resolve_session_root() -> Path | None:
    session_root = current_session_root.get()
    if session_root:
        return Path(session_root)
    return None


def _resolve_global_workspace_root() -> Path | None:
    global_workspace = current_global_workspace.get()
    if global_workspace:
        return Path(global_workspace)
    return None


def _resolve_file_path(path_str: str) -> Path:
    """将用户传入的路径解析为绝对路径。

    规则：
    - /global/... 前缀映射到全局工作区目录
    - /workspace/... 前缀映射到当前工作区目录
    - 其他绝对路径直接使用
    - 相对路径优先基于当前 workspace，其次基于 session root
    - 禁止 .. 逃逸
    """
    normalized = path_str.replace("\\", "/").strip()

    # 处理 /global/... 前缀
    if normalized.startswith("/global/"):
        global_workspace = _resolve_global_workspace_root()
        if global_workspace is None:
            raise ValueError(f"路径 `{path_str}` 指向全局工作区，但当前上下文未设置全局工作区。")
        relative_part = normalized[len("/global/") :]
        p = Path(relative_part)
        if ".." in p.parts:
            raise ValueError(f"路径 `{path_str}` 包含非法的 .. 逃逸。")
        resolved = (global_workspace / p).resolve()
        # 二次校验：解析后必须在全局工作区内
        if not (
            resolved == global_workspace.resolve()
            or resolved.is_relative_to(global_workspace.resolve())
        ):
            raise ValueError(f"路径 `{path_str}` 解析后超出全局工作区范围。")
        return resolved

    # 处理 /workspace/... 前缀（上传 API 返回的路径格式）
    if normalized.startswith("/workspace/"):
        workspace = _resolve_workspace_root()
        if workspace is None:
            raise ValueError(f"路径 `{path_str}` 指向工作区，但当前上下文未设置工作区。")
        relative_part = normalized[len("/workspace/") :]
        p = Path(relative_part)
        if ".." in p.parts:
            raise ValueError(f"路径 `{path_str}` 包含非法的 .. 逃逸。")
        resolved = (workspace / p).resolve()
        workspace_resolved = workspace.resolve()
        if not (resolved == workspace_resolved or resolved.is_relative_to(workspace_resolved)):
            raise ValueError(f"路径 `{path_str}` 解析后超出工作区范围。")
        return resolved

    p = Path(normalized)

    if p.is_absolute():
        resolved = p.resolve()
    else:
        workspace = _resolve_workspace_root()
        if workspace:
            base = workspace
        else:
            session_root = _resolve_session_root()
            base = session_root or Path.cwd()
        resolved = (base / p).resolve()

    # 路径逃逸检查：解析后不能超出 workspace/session/global 范围
    workspace = _resolve_workspace_root()
    session_root = _resolve_session_root()
    global_workspace = _resolve_global_workspace_root()
    allowed_bases: list[Path] = []
    if workspace:
        allowed_bases.append(workspace.resolve())
    if session_root:
        allowed_bases.append(session_root.resolve())
    if global_workspace:
        allowed_bases.append(global_workspace.resolve())

    if allowed_bases:
        in_any = any(resolved == base or resolved.is_relative_to(base) for base in allowed_bases)
        if not in_any:
            raise ValueError(
                f"路径 `{path_str}` 解析后超出允许范围。"
                "相对路径请基于当前工作区，或使用 /global/ 前缀访问全局工作区。"
            )

    return resolved


# ---------------------------------------------------------------------------
# 换行符处理 helper
# ---------------------------------------------------------------------------

LineEndingStyle = Literal["lf", "crlf", "mixed"]


def detect_line_ending_style(text: str) -> LineEndingStyle:
    """检测文本的换行符风格。

    - 同时存在 \r\n 和 \n（且后者不跟在 \r 后）→ mixed
    - 只有 \r\n → crlf
    - 只有 \n 或只有 \r → lf
    """
    has_crlf = False
    has_lf = False
    has_lone_cr = False

    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\r":
            if i + 1 < len(text) and text[i + 1] == "\n":
                has_crlf = True
                i += 2
                continue
            has_lone_cr = True
        elif ch == "\n":
            has_lf = True
        i += 1

    if has_crlf and (has_lf or has_lone_cr):
        return "mixed"
    if has_crlf:
        return "crlf"
    return "lf"


def normalize_line_endings_for_display(text: str, style: LineEndingStyle) -> str:
    """把原始文本转为模型可读的显示格式。

    - crlf：把 \r\n 转为 \n（模型看到 LF，但 style 信息会单独返回）
    - mixed：把 lone \r 显示为 \\r，保留 \n
    """
    if style == "crlf":
        return text.replace("\r\n", "\n")
    if style == "mixed":
        # lone CR 显示为转义序列，让模型知道这里有个 CR
        return text.replace("\r\n", "\n").replace("\r", "\\r")
    return text


def restore_line_endings(text: str, style: LineEndingStyle) -> str:
    """把编辑后的显示文本恢复为指定换行符风格。"""
    if style == "crlf":
        # 先把已有的 \r\n 规范化，再把 \n 转成 \r\n
        return text.replace("\r\n", "\n").replace("\n", "\r\n")
    if style == "mixed":
        # 模型看到的 \\r 需要恢复为 \r；这里不处理 CRLF，因为 mixed 场景下我们已把 CRLF 拆成 lone CR
        return text.replace("\\r", "\r")
    return text
