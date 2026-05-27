"""文件工具共享的路径解析 helper。

供 file_tools / file_tools_read / file_tools_write 等子模块共用，
避免循环导入。
"""

from __future__ import annotations

from pathlib import Path

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
