"""WriteFile / StrReplaceFile 工具。

文件写入与字符串替换编辑。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.file_history import FileHistoryOperation, file_history_service

from .file_tools_base import (
    _resolve_file_path,
    _resolve_global_workspace_root,
    _resolve_workspace_root,
)


def _append_text(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


def _relative_to_root(path: Path, root: Path) -> str | None:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if not (resolved_path == resolved_root or resolved_path.is_relative_to(resolved_root)):
        return None
    return resolved_path.relative_to(resolved_root).as_posix()


def _record_agent_file_history(
    file_path: Path,
    *,
    operation: FileHistoryOperation,
    source_detail: str,
) -> None:
    for root in (_resolve_global_workspace_root(), _resolve_workspace_root()):
        if root is None:
            continue
        relative_path = _relative_to_root(file_path, root)
        if relative_path is None:
            continue
        file_history_service.record_file_before_change(
            root,
            relative_path,
            operation=operation,
            source="agent_tool",
            source_detail=source_detail,
        )
        return


# ---------------------------------------------------------------------------
# WriteFile
# ---------------------------------------------------------------------------


class WriteFileParams(BaseModel):
    """WriteFile 参数。"""

    path: str = Field(
        description="要写入的文件路径。相对路径基于当前工作区。支持 /global/ 前缀写入全局工作区。"
    )
    content: str = Field(description="要写入的文件内容")
    mode: Literal["overwrite", "append"] = Field(
        default="overwrite",
        description="写入模式：`overwrite` 覆盖整个文件，`append` 追加到末尾",
    )


class WriteFile(AiasysTool):
    """写入或追加文件内容。"""

    name: str = "WriteFile"
    description: str = """将内容写入当前工作区或全局工作区中的文件。

支持两种模式：
- `overwrite`：覆盖整个文件（默认）
- `append`：追加到现有文件末尾

特性：
- 自动创建缺失的父目录
- 如果目标路径在 workspace 外，会报错
"""
    params: type[BaseModel] = WriteFileParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = WriteFileParams.model_validate(kwargs)

        if not params.path:
            return ToolResult(content="文件路径不能为空", is_error=True)

        try:
            file_path = _resolve_file_path(params.path)
        except ValueError as e:
            return ToolResult(content=str(e), is_error=True)

        # 创建父目录
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return ToolResult(content=f"创建父目录失败: {e}", is_error=True)

        try:
            if params.mode == "overwrite":
                _record_agent_file_history(
                    file_path,
                    operation="before_overwrite",
                    source_detail=self.name,
                )
                await asyncio.get_event_loop().run_in_executor(
                    None, file_path.write_text, params.content, "utf-8"
                )
            else:
                _record_agent_file_history(
                    file_path,
                    operation="before_update",
                    source_detail=self.name,
                )
                await asyncio.get_event_loop().run_in_executor(
                    None, _append_text, file_path, params.content
                )
        except Exception as e:
            return ToolResult(content=f"写入失败: {e}", is_error=True)

        action = "覆盖" if params.mode == "overwrite" else "追加"
        size = file_path.stat().st_size
        return ToolResult(
            content=f"文件已成功{action}。当前大小: {size} 字节。",
        )


# ---------------------------------------------------------------------------
# StrReplaceFile
# ---------------------------------------------------------------------------


class FileEdit(BaseModel):
    """单次编辑操作。"""

    old: str = Field(description="要替换的旧字符串，支持多行")
    new: str = Field(description="用于替换的新字符串，支持多行")
    replace_all: bool = Field(
        default=False,
        description="是否替换所有匹配项。默认只替换第一个",
    )


class StrReplaceFileParams(BaseModel):
    """StrReplaceFile 参数。"""

    path: str = Field(
        description="要编辑的文件路径。相对路径基于当前工作区。支持 /global/ 前缀编辑全局工作区文件。"
    )
    edit: FileEdit | list[FileEdit] = Field(
        description="要应用的编辑操作。可以传入单个 edit 或 edit 列表"
    )


class StrReplaceFile(AiasysTool):
    """通过字符串替换编辑文件内容。"""

    name: str = "StrReplaceFile"
    description: str = """在当前工作区或全局工作区的文件中进行精确的字符串替换编辑。

使用方式：
1. 先用 ReadFile 读取文件，确认要修改的内容
2. 提供 `old`（原字符串）和 `new`（新字符串）
3. 系统会精确匹配 `old` 并进行替换

注意事项：
- `old` 必须与文件中的内容完全匹配（包括空格和换行）
- 默认只替换第一个匹配项；设置 `replace_all=true` 替换所有
- 如果 `old` 在文件中找不到，会报错
- 支持批量编辑：传入 `edit` 列表可一次性应用多处修改
"""
    params: type[BaseModel] = StrReplaceFileParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = StrReplaceFileParams.model_validate(kwargs)

        if not params.path:
            return ToolResult(content="文件路径不能为空", is_error=True)

        try:
            file_path = _resolve_file_path(params.path)
        except ValueError as e:
            return ToolResult(content=str(e), is_error=True)

        if not file_path.exists():
            return ToolResult(content=f"`{params.path}` 不存在", is_error=True)
        if not file_path.is_file():
            return ToolResult(content=f"`{params.path}` 不是文件", is_error=True)

        try:
            content = await asyncio.get_event_loop().run_in_executor(
                None, file_path.read_text, "utf-8", "replace"
            )
        except Exception as e:
            return ToolResult(content=f"读取失败: {e}", is_error=True)

        original = content
        edits = [params.edit] if isinstance(params.edit, FileEdit) else params.edit

        total_replacements = 0
        for edit in edits:
            if edit.old == edit.new:
                continue
            if edit.old not in content:
                return ToolResult(
                    content=f"未找到匹配字符串: {edit.old[:80]}...",
                    is_error=True,
                )
            if edit.replace_all:
                count = content.count(edit.old)
                content = content.replace(edit.old, edit.new)
                total_replacements += count
            else:
                content = content.replace(edit.old, edit.new, 1)
                total_replacements += 1

        if content == original:
            return ToolResult(
                content="未进行任何替换，可能是 old 和 new 相同",
                is_error=True,
            )

        try:
            _record_agent_file_history(
                file_path,
                operation="before_update",
                source_detail=self.name,
            )
            await asyncio.get_event_loop().run_in_executor(
                None, file_path.write_text, content, "utf-8"
            )
        except Exception as e:
            return ToolResult(content=f"写入失败: {e}", is_error=True)

        return ToolResult(
            content=f"文件编辑成功。应用了 {len(edits)} 处编辑，共 {total_replacements} 次替换。",
        )
