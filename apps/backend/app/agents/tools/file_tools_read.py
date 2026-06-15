"""ReadFile 工具。

从当前工作区或全局工作区读取文本文件。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult

from .file_tools import MAX_BYTES, MAX_LINE_LENGTH, MAX_LINES, _is_binary_file, _truncate_line
from app.utils.path_utils import as_system_path

from .file_tools_base import (
    LineEndingStyle,
    _resolve_file_path,
    detect_line_ending_style,
    normalize_line_endings_for_display,
)
from .file_tools_restrictions import (
    _detect_file_type_by_magic,
    _get_non_text_hint,
    _is_non_text_by_suffix,
    _match_sensitive_file_pattern,
)


def _read_text_preserve_newlines(path: Path) -> str:
    """以保留原始换行符的方式读取文本文件。"""
    with open(as_system_path(path), encoding="utf-8", errors="replace", newline="") as f:
        return f.read()


class ReadFileParams(BaseModel):
    """ReadFile 参数。"""

    path: str = Field(
        description="要读取的文件路径。相对路径基于当前工作区，绝对路径可直接使用。支持 /global/ 前缀访问全局工作区文件。"
    )
    line_offset: int = Field(
        default=1,
        description=(
            "开始读取的行号（1-based）。默认从第1行开始。"
            "负值从文件尾部计数（如 -100 表示最后100行）。"
            f"绝对值不能超过 {MAX_LINES}。"
        ),
    )
    n_lines: int = Field(
        default=MAX_LINES,
        description=f"最多读取的行数，默认 {MAX_LINES}，最大 {MAX_LINES}。",
        ge=1,
    )
    expand_block: bool = Field(
        default=False,
        description=(
            "是否按缩进自动扩展读取范围。开启后，line_offset 所在行会被视为某个代码块内部，"
            "工具自动向上/向下按缩进边界扩展，读取完整函数/类/条件块。仅对正值 line_offset 有效。"
        ),
    )

    @model_validator(mode="after")
    def _validate_offset(self) -> "ReadFileParams":
        if self.line_offset == 0:
            raise ValueError("line_offset 不能为 0，请用 1 表示第一行，-1 表示最后一行")
        if self.line_offset < -MAX_LINES:
            raise ValueError(f"line_offset 不能小于 -{MAX_LINES}")
        return self


def _leading_indent(line: str) -> int | None:
    """返回一行字符串的前导空格/Tab 数量；空行返回 None。"""
    stripped = line.lstrip()
    if not stripped:
        return None
    return len(line) - len(stripped)


def _is_structural_header(line: str) -> bool:
    """判断一行是否为结构性代码块头（函数/类/异步函数定义）。"""
    stripped = line.lstrip()
    return stripped.startswith(("def ", "class ", "async def "))


def _expand_by_indent(lines: list[str], target_idx: int) -> tuple[int, int]:
    """按缩进扩展代码块，返回包含起止索引（0-based，闭区间）。

    规则：
    - 以 target_idx 所在行为锚点；若为空行则向后找第一个非空行作为基准。
    - 优先把最近的函数/类/异步函数定义视为块头。
    - 若目标行本身就是函数/类定义，则读取该函数/类。
    - 若上方没有函数/类定义，则退回到最近的低缩进行（如 if/for/while）作为块头。
    - 找到块头后，自动把同缩进的装饰器（@...）包含进来。
    - 向下读到第一个缩进 <= 块头缩进的非空行之前。
    """
    n = len(lines)
    if not lines:
        return target_idx, target_idx

    base_idx = target_idx
    while base_idx < n and _leading_indent(lines[base_idx]) is None:
        base_idx += 1
    if base_idx >= n:
        return target_idx, target_idx

    # 如果目标行本身就是结构头，直接用它
    if _is_structural_header(lines[base_idx]):
        header_idx = base_idx
    else:
        # 向上寻找候选块头：缩进严格小于其到目标行之间所有行缩进的非空行
        min_indent = _leading_indent(lines[base_idx])
        assert min_indent is not None

        candidates: list[int] = []
        for i in range(base_idx - 1, -1, -1):
            line = lines[i]
            indent = _leading_indent(line)
            if indent is None:
                continue
            if indent < min_indent:
                candidates.append(i)
                min_indent = indent

        # 优先选最近的结构性定义
        header_idx = -1
        for idx in candidates:
            if _is_structural_header(lines[idx]):
                header_idx = idx
                break
        if header_idx == -1 and candidates:
            # 没有函数/类定义时，使用最近的低缩进块头
            header_idx = candidates[0]
        if header_idx == -1:
            header_idx = base_idx

    header_indent = _leading_indent(lines[header_idx])
    assert header_indent is not None

    # 向上包含同缩进的装饰器
    start_idx = header_idx
    for i in range(header_idx - 1, -1, -1):
        line = lines[i]
        indent = _leading_indent(line)
        if indent is None:
            continue
        stripped = line.lstrip()
        if stripped.startswith("@") and indent == header_indent:
            start_idx = i
        else:
            break

    # 向下扩展，直到遇到缩进 <= header_indent 的非空行
    end_idx = header_idx
    for i in range(header_idx + 1, n):
        line = lines[i]
        indent = _leading_indent(line)
        if indent is None:
            end_idx = i
            continue
        if indent <= header_indent:
            break
        end_idx = i

    return start_idx, end_idx


class ReadFile(AiasysTool):
    """读取当前工作区或全局工作区内的文本文件。"""

    name: str = "ReadFile"
    risk_level: str = "readonly"
    effect_scope: str = "workspace"
    side_effect: bool = False
    description: str = f"""读取当前工作区或全局工作区中的**纯文本文件**。

本工具只能读取文本文件（如 .py、.md、.json、.csv、.txt、.yml、.html 等）。
遇到以下类型的文件时，请改用其他方式处理，不要调用 ReadFile：
- Excel 表格（.xlsx / .xls / .xlsm）→ 用 Shell 工具运行 Python（pandas / openpyxl）读取
- PDF（.pdf）→ 用 Shell 工具运行 Python（PyPDF2 / pdfplumber）提取文本
- Office 文档（.docx / .doc / .pptx / .ppt）→ 用 Shell 工具运行 Python（python-docx 等）提取
- 图片（.png / .jpg / .gif 等）→ 用 ReadMediaFile 工具
- 视频（.mp4 / .avi / .mov 等）→ 用 ReadMediaFile 工具
- 压缩包（.zip / .tar.gz / .7z 等）→ 用 Shell 工具解压后读取
- 可执行文件、数据库文件等二进制文件 → 不适用

支持分页读取：通过 line_offset 和 n_lines 控制读取范围。
- line_offset 为正值时从文件头部计数（1-based）
- line_offset 为负值时从文件尾部计数（如 -100 读取最后100行）
- 输出带行号（cat -n 格式），方便 Agent 定位

缩进感知代码块读取（expand_block=true）：
- 指定 line_offset 后，自动向上/向下按缩进边界扩展，读取完整函数/类/条件块
- 适用于只想读取某个代码块而非整个文件的场景

限制：
- 单次最多读取 {MAX_LINES} 行或 {MAX_BYTES} 字节
- 单行超过 {MAX_LINE_LENGTH} 字符会被截断
- 拒绝读取非文本文件（含二进制文件和已知非文本格式）
"""
    params: type[BaseModel] = ReadFileParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = ReadFileParams.model_validate(kwargs)

        if not params.path:
            return ToolResult(content="文件路径不能为空", is_error=True)

        try:
            file_path = _resolve_file_path(params.path)
        except ValueError as e:
            return ToolResult(content=str(e), is_error=True)

        # 敏感文件检查（.gitignore 风格模式）
        matched_pattern = _match_sensitive_file_pattern(file_path)
        if matched_pattern:
            return ToolResult(
                content=(
                    f"`{params.path}` 命中敏感文件模式 `{matched_pattern}`，"
                    "禁止读取以保护凭据安全。"
                ),
                is_error=True,
            )

        if not os.path.exists(as_system_path(file_path)):
            return ToolResult(content=f"`{params.path}` 不存在", is_error=True)
        if not os.path.isfile(as_system_path(file_path)):
            return ToolResult(content=f"`{params.path}` 不是文件", is_error=True)

        # 已知非文本扩展名检查（优先于 NUL 字节检测，可给出更精确的替代建议）
        if _is_non_text_by_suffix(file_path):
            return ToolResult(
                content=_get_non_text_hint(file_path),
                is_error=True,
            )

        # NUL 字节兜底检测（覆盖扩展名黑名单未涵盖的二进制文件）
        if _is_binary_file(file_path):
            return ToolResult(
                content=(
                    f"`{params.path}` 是二进制文件，ReadFile 只能读取纯文本文件。"
                    "如需提取内容，请用 Shell 工具运行对应的解析命令。"
                ),
                is_error=True,
            )

        # Magic-byte 检测（覆盖扩展名缺失/错误但内容实为二进制的情况）
        magic = _detect_file_type_by_magic(file_path)
        if magic:
            name, hint = magic
            return ToolResult(
                content=(
                    f"`{params.path}` 被识别为 {name} 文件，"
                    f"ReadFile 只能读取纯文本文件。{hint}"
                ),
                is_error=True,
            )

        try:
            raw_content = await asyncio.get_event_loop().run_in_executor(
                None, _read_text_preserve_newlines, file_path
            )
        except Exception as e:
            return ToolResult(content=f"读取失败: {e}", is_error=True)

        line_ending_style = detect_line_ending_style(raw_content)
        content = normalize_line_endings_for_display(raw_content, line_ending_style)

        lines = content.splitlines(keepends=True)
        total_lines = len(lines)

        effective_params = params
        if params.expand_block and params.line_offset > 0:
            start_idx, end_idx = _expand_by_indent(lines, params.line_offset - 1)
            effective_params = params.model_copy(
                update={
                    "line_offset": start_idx + 1,
                    "n_lines": end_idx - start_idx + 1,
                }
            )

        if effective_params.line_offset < 0:
            return self._read_tail(
                effective_params, lines, total_lines, file_path, line_ending_style
            )
        else:
            return self._read_forward(
                effective_params, lines, total_lines, file_path, line_ending_style
            )

    def _read_forward(
        self,
        params: ReadFileParams,
        lines: list[str],
        total_lines: int,
        file_path: Path,
        line_ending_style: LineEndingStyle,
    ) -> ToolResult:
        start_idx = params.line_offset - 1
        if start_idx >= total_lines:
            return ToolResult(
                content=f"文件共 {total_lines} 行，请求从第 {params.line_offset} 行开始，超出范围。",
            )

        result_lines: list[str] = []
        truncated_line_nos: list[int] = []
        n_bytes = 0
        max_lines_reached = False
        max_bytes_reached = False

        for i in range(start_idx, total_lines):
            line_no = i + 1
            raw_line = lines[i]
            truncated = _truncate_line(raw_line)
            if truncated != raw_line:
                truncated_line_nos.append(line_no)
            line_bytes = len(truncated.encode("utf-8"))
            if n_bytes + line_bytes > MAX_BYTES:
                max_bytes_reached = True
                break
            result_lines.append(truncated)
            n_bytes += line_bytes
            if len(result_lines) >= params.n_lines:
                break
            if len(result_lines) >= MAX_LINES:
                max_lines_reached = True
                break

        output_lines = [
            f"{start_idx + 1 + idx:6d}\t{line.rstrip()}" for idx, line in enumerate(result_lines)
        ]
        output = "\n".join(output_lines)

        msg = (
            f"从第 {start_idx + 1} 行开始读取了 {len(result_lines)} 行。文件总行数: {total_lines}。"
        )
        if max_lines_reached:
            msg += f" 达到最大行数限制 {MAX_LINES}。"
        elif max_bytes_reached:
            msg += f" 达到最大字节限制 {MAX_BYTES}。"
        elif start_idx + len(result_lines) >= total_lines:
            msg += " 已到达文件末尾。"
        if truncated_line_nos:
            msg += f" 第 {truncated_line_nos} 行被截断。"
        msg += f" 换行符风格: {_line_ending_label(line_ending_style)}。"

        return ToolResult(content=output or msg)

    def _read_tail(
        self,
        params: ReadFileParams,
        lines: list[str],
        total_lines: int,
        file_path: Path,
        line_ending_style: LineEndingStyle,
    ) -> ToolResult:
        tail_count = abs(params.line_offset)
        line_limit = min(params.n_lines, MAX_LINES)

        start_idx = max(0, total_lines - tail_count)
        selected = lines[start_idx : start_idx + line_limit]

        # 字节限制
        n_bytes = 0
        kept = 0
        for line in reversed(selected):
            truncated = _truncate_line(line)
            line_bytes = len(truncated.encode("utf-8"))
            if n_bytes + line_bytes > MAX_BYTES:
                break
            n_bytes += line_bytes
            kept += 1

        if kept < len(selected):
            selected = selected[len(selected) - kept :]
            max_bytes_reached = True
        else:
            max_bytes_reached = False

        truncated_line_nos: list[int] = []
        output_lines: list[str] = []
        for idx, raw_line in enumerate(selected):
            line_no = start_idx + idx + 1
            truncated = _truncate_line(raw_line)
            if truncated != raw_line:
                truncated_line_nos.append(line_no)
            output_lines.append(f"{line_no:6d}\t{truncated.rstrip()}")

        output = "\n".join(output_lines)
        msg = f"从第 {start_idx + 1} 行开始读取了 {len(selected)} 行（尾部模式）。文件总行数: {total_lines}。"
        if max_bytes_reached:
            msg += f" 达到最大字节限制 {MAX_BYTES}。"
        if truncated_line_nos:
            msg += f" 第 {truncated_line_nos} 行被截断。"
        msg += f" 换行符风格: {_line_ending_label(line_ending_style)}。"

        return ToolResult(content=output or msg)


def _line_ending_label(style: LineEndingStyle) -> str:
    if style == "crlf":
        return "CRLF (Windows 风格)"
    if style == "mixed":
        return "mixed (混合换行符)"
    return "LF (Unix 风格)"
