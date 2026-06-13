"""WriteFile / StrReplaceFile 工具。

文件写入与字符串替换编辑。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.file_history import FileHistoryOperation, file_history_service

from .file_tools_base import (
    _resolve_file_path,
    _resolve_global_workspace_root,
    _resolve_workspace_root,
    detect_line_ending_style,
    normalize_line_endings_for_display,
    restore_line_endings,
)
from .file_tools_restrictions import (
    _detect_file_type_by_magic,
    _get_write_discouraged_hint,
    _is_write_discouraged_by_suffix,
    _match_sensitive_file_pattern,
)


def _append_text(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


def _read_text_preserve_newlines(path: Path) -> str:
    """以保留原始换行符的方式读取文件。"""
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        return f.read()


def _write_text_preserve_newlines(path: Path, text: str) -> None:
    """以保留原始换行符的方式写入文件。"""
    with open(path, "w", encoding="utf-8", newline="") as f:
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


def _check_sensitive_path(file_path: Path) -> ToolResult | None:
    """检查目标路径是否命中敏感文件模式。命中则返回错误 ToolResult。"""
    matched_pattern = _match_sensitive_file_pattern(file_path)
    if matched_pattern:
        return ToolResult(
            content=(
                f"`{file_path}` 命中敏感文件模式 `{matched_pattern}`，"
                "禁止写入/编辑以保护凭据安全。"
            ),
            is_error=True,
        )
    return None


def _check_binary_magic(file_path: Path) -> ToolResult | None:
    """通过 magic byte 识别二进制文件。命中则返回错误 ToolResult。"""
    magic = _detect_file_type_by_magic(file_path)
    if magic:
        name, hint = magic
        return ToolResult(
            content=(
                f"`{file_path}` 被识别为 {name} 文件，"
                f"StrReplaceFile 只能编辑纯文本文件。{hint}"
            ),
            is_error=True,
        )
    return None


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
    risk_level: str = "medium"
    effect_scope: str = "workspace"
    side_effect: bool = True
    description: str = """将内容写入当前工作区或全局工作区中的**纯文本文件**。

支持两种模式：
- `overwrite`：覆盖整个文件（默认）
- `append`：追加到现有文件末尾

限制：
- 只能写入文本文件（如 .py、.md、.json、.csv、.txt、.yml、.html、.svg 等）
- 禁止写入 Jupyter Notebook 文件（.ipynb）→ 请使用 ManageNotebook 工具
- 禁止写入二进制文件（图片、Office、PDF、压缩包、可执行文件等）
- 注意：.svg 虽然是图片格式，但本质是文本，**允许**用 WriteFile 写入和编辑
- 如果目标路径在 workspace 外，会报错

特性：
- 自动创建缺失的父目录
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

        sensitive_result = _check_sensitive_path(file_path)
        if sensitive_result:
            return sensitive_result

        # 拒绝写入非文本文件或有专属工具的文件
        if _is_write_discouraged_by_suffix(file_path):
            return ToolResult(
                content=_get_write_discouraged_hint(file_path),
                is_error=True,
            )

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

    @model_validator(mode="before")
    @classmethod
    def _parse_edit_json(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        edit = values.get("edit")
        if isinstance(edit, str):
            try:
                parsed = json.loads(edit)
                values["edit"] = parsed
            except json.JSONDecodeError:
                pass  # 让 model_validate 报原来的错误
        return values


class StrReplaceFile(AiasysTool):
    """通过字符串替换编辑文件内容。"""

    name: str = "StrReplaceFile"
    risk_level: str = "medium"
    effect_scope: str = "workspace"
    side_effect: bool = True
    description: str = """在当前工作区或全局工作区的**纯文本文件**中进行精确的字符串替换编辑。

使用方式：
1. 先用 ReadFile 读取文件，确认要修改的内容
2. 提供 `old`（原字符串）和 `new`（新字符串）
3. 系统会精确匹配 `old` 并进行替换

限制：
- 只能编辑文本文件（如 .py、.md、.json、.csv、.txt、.yml、.html、.svg 等）
- 禁止编辑 Jupyter Notebook 文件（.ipynb）→ 请使用 ManageNotebook 工具
- 禁止编辑二进制文件（图片、Office、PDF、压缩包、可执行文件等）
- 注意：.svg 虽然是图片格式，但本质是文本，**允许**用 StrReplaceFile 编辑

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

        sensitive_result = _check_sensitive_path(file_path)
        if sensitive_result:
            return sensitive_result

        # 拒绝编辑非文本文件或有专属工具的文件
        if _is_write_discouraged_by_suffix(file_path):
            return ToolResult(
                content=_get_write_discouraged_hint(file_path),
                is_error=True,
            )

        magic_result = _check_binary_magic(file_path)
        if magic_result:
            return magic_result

        if not file_path.exists():
            return ToolResult(content=f"`{params.path}` 不存在", is_error=True)
        if not file_path.is_file():
            return ToolResult(content=f"`{params.path}` 不是文件", is_error=True)

        try:
            raw_content = await asyncio.get_event_loop().run_in_executor(
                None, _read_text_preserve_newlines, file_path
            )
        except Exception as e:
            return ToolResult(content=f"读取失败: {e}", is_error=True)

        line_ending_style = detect_line_ending_style(raw_content)
        # 把内容转成模型可匹配的显示格式（CRLF→LF，mixed 中 lone CR 显示为 \\r）
        content = normalize_line_endings_for_display(raw_content, line_ending_style)

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

        # 写回前恢复原始换行符风格
        content_to_write = restore_line_endings(content, line_ending_style)

        try:
            _record_agent_file_history(
                file_path,
                operation="before_update",
                source_detail=self.name,
            )
            await asyncio.get_event_loop().run_in_executor(
                None, _write_text_preserve_newlines, file_path, content_to_write
            )
        except Exception as e:
            return ToolResult(content=f"写入失败: {e}", is_error=True)

        le_info = "，已保持原换行符风格" if line_ending_style != "lf" else ""
        return ToolResult(
            content=f"文件编辑成功。应用了 {len(edits)} 处编辑，共 {total_replacements} 次替换{le_info}。",
        )
