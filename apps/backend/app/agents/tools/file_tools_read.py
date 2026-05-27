"""ReadFile 工具。

从当前工作区或全局工作区读取文本文件。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult

from .file_tools import (
    MAX_BYTES,
    MAX_LINE_LENGTH,
    MAX_LINES,
    _is_binary_file,
    _truncate_line,
)
from .file_tools_base import _resolve_file_path


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

    @model_validator(mode="after")
    def _validate_offset(self) -> "ReadFileParams":
        if self.line_offset == 0:
            raise ValueError("line_offset 不能为 0，请用 1 表示第一行，-1 表示最后一行")
        if self.line_offset < -MAX_LINES:
            raise ValueError(f"line_offset 不能小于 -{MAX_LINES}")
        return self


class ReadFile(AiasysTool):
    """读取当前工作区或全局工作区内的文本文件。"""

    name: str = "ReadFile"
    description: str = f"""读取当前工作区或全局工作区中的文本文件内容。

支持分页读取：通过 line_offset 和 n_lines 控制读取范围。
- line_offset 为正值时从文件头部计数（1-based）
- line_offset 为负值时从文件尾部计数（如 -100 读取最后100行）
- 输出带行号（cat -n 格式），方便 Agent 定位

限制：
- 单次最多读取 {MAX_LINES} 行或 {MAX_BYTES} 字节
- 单行超过 {MAX_LINE_LENGTH} 字符会被截断
- 拒绝读取二进制文件（图片、视频、可执行文件等）
- 拒绝读取敏感文件（.env、密钥文件等）
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

        # 敏感文件检查
        sensitive_names = {
            ".env",
            ".env.local",
            ".env.production",
            ".git-credentials",
            "id_rsa",
            "id_ed25519",
        }
        if file_path.name in sensitive_names or any(
            part.startswith(".") and "env" in part for part in file_path.parts
        ):
            return ToolResult(
                content=f"`{params.path}` 是敏感文件，禁止读取以保护凭据安全。",
                is_error=True,
            )

        if not file_path.exists():
            return ToolResult(content=f"`{params.path}` 不存在", is_error=True)
        if not file_path.is_file():
            return ToolResult(content=f"`{params.path}` 不是文件", is_error=True)

        # 二进制检查
        if _is_binary_file(file_path):
            return ToolResult(
                content=f"`{params.path}` 是二进制文件，请使用其他工具读取。",
                is_error=True,
            )

        try:
            content = await asyncio.get_event_loop().run_in_executor(
                None, file_path.read_text, "utf-8", "replace"
            )
        except Exception as e:
            return ToolResult(content=f"读取失败: {e}", is_error=True)

        lines = content.splitlines(keepends=True)
        total_lines = len(lines)

        if params.line_offset < 0:
            return self._read_tail(params, lines, total_lines, file_path)
        else:
            return self._read_forward(params, lines, total_lines, file_path)

    def _read_forward(
        self,
        params: ReadFileParams,
        lines: list[str],
        total_lines: int,
        file_path: Path,
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

        return ToolResult(content=output or msg)

    def _read_tail(
        self,
        params: ReadFileParams,
        lines: list[str],
        total_lines: int,
        file_path: Path,
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

        return ToolResult(content=output or msg)
