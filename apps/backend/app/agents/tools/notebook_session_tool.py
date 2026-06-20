"""
Notebook 会话辅助工具。

目标：
- 把 notebook-first 工作流拆成更细的工具，而不是继续把所有轻量动作都塞进 REPL
- 明确区分当前会话私有 notebook 与工作区共享 notebook
- 复用现有 notebook path / scope 校验，避免跨会话误写
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agents.tools.notebook_file_tool import NotebookCellInput
from app.agents.tools.notebook_utils import (
    build_text_preview,
    default_notebook,
    ensure_notebook_shape,
    load_notebook,
    resolve_notebook_targets,
    resolve_workspace_root_from_context,
    source_to_text,
    summarize_cells,
    write_notebook,
)
from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult


def _normalize_notebook_directory(directory: str | None) -> Path:
    raw_value = (directory or "").strip()
    if not raw_value:
        return Path(".")

    normalized = Path(raw_value.replace("\\", "/"))
    if normalized.is_absolute() or any(part == ".." for part in normalized.parts):
        raise ValueError("Notebook 目录无效，必须是当前作用域内的相对路径")
    if normalized.parts and normalized.parts[0] == ".aiasys":
        raise ValueError("不允许访问 .aiasys 内部目录")
    return normalized


def _resolve_directory_under_root(root: Path, directory: str | None) -> tuple[Path, Path]:
    relative_dir = _normalize_notebook_directory(directory)
    resolved_dir = (root / relative_dir).resolve()
    root_resolved = root.resolve()
    try:
        resolved_dir.relative_to(root_resolved)
    except ValueError:
        raise ValueError("Notebook 目录超出当前允许范围。")
    return relative_dir, resolved_dir


def _make_cell_payload(cell: NotebookCellInput) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": cell.cell_id,
        "cell_type": cell.cell_type,
        "metadata": dict(cell.metadata),
        "source": cell.source,
    }
    if cell.cell_type == "code":
        payload["outputs"] = list(cell.outputs)
        payload["execution_count"] = cell.execution_count
    return payload


def _derive_notebook_title(notebook: dict[str, Any], fallback_name: str) -> str:
    for cell in notebook.get("cells", []):
        source = source_to_text(cell.get("source", "")).strip()
        if not source:
            continue
        first_line = source.splitlines()[0].strip()
        if not first_line:
            continue
        if first_line.startswith("#"):
            return first_line.lstrip("#").strip() or fallback_name
        return build_text_preview(first_line, 80) or fallback_name
    return fallback_name


def _collect_notebook_file_items(
    *,
    root: Path,
    relative_dir: Path,
    storage_scope: str,
    max_results: int,
) -> list[dict[str, Any]]:
    if not root.exists():
        return []

    pattern_root = root if relative_dir == Path(".") else root / relative_dir
    if not pattern_root.exists():
        return []

    results: list[dict[str, Any]] = []
    for notebook_path in sorted(pattern_root.rglob("*.ipynb"))[: max(1, max_results)]:
        try:
            relative_path = notebook_path.resolve().relative_to(root.resolve())
        except Exception:
            continue

        notebook: dict[str, Any] | None = None
        parse_error: str | None = None
        try:
            notebook = load_notebook(notebook_path)
        except json.JSONDecodeError as exc:
            parse_error = str(exc)

        stat = notebook_path.stat()
        cells = list(notebook.get("cells", [])) if notebook else []
        output_cells = sum(1 for cell in cells if list(cell.get("outputs") or []))
        code_cells = sum(1 for cell in cells if cell.get("cell_type") == "code")

        results.append(
            {
                "path": relative_path.as_posix(),
                "storage_scope": storage_scope,
                "exists": True,
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "cell_count": len(cells),
                "code_cell_count": code_cells,
                "output_cell_count": output_cells,
                "title": _derive_notebook_title(notebook or {}, notebook_path.stem),
                "parse_error": parse_error,
            }
        )
    return results


class ListSessionNotebooksParams(BaseModel):
    directory: str | None = Field(
        default="notebooks",
        description="当前会话私有 notebook 搜索目录；为空则从当前会话根目录递归扫描",
    )
    max_results: int = Field(
        default=100,
        ge=1,
        le=500,
        description="最多返回多少个 notebook",
    )


class ListSessionNotebooks(AiasysTool):
    name: str = "ListSessionNotebooks"
    description: str = """列出当前工作区中的 Jupyter notebook（.ipynb）文件。

适用场景：
- 查看当前工作区已有哪些 notebook
- 确认 scratch notebook / 实验 notebook 是否已经存在
- 在继续执行前判断是否应复用现有 notebook
"""
    params: type[BaseModel] = ListSessionNotebooksParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = ListSessionNotebooksParams.model_validate(kwargs)

        workspace_root = resolve_workspace_root_from_context()
        if workspace_root is None:
            return ToolResult(
                content="当前缺少逻辑工作区上下文，无法列出 notebook。",
                is_error=True,
            )

        try:
            relative_dir, resolved_dir = _resolve_directory_under_root(
                workspace_root,
                params.directory,
            )
        except ValueError as exc:
            return ToolResult(
                content=str(exc),
                is_error=True,
            )

        notebooks = _collect_notebook_file_items(
            root=workspace_root,
            relative_dir=relative_dir,
            storage_scope="workspace",
            max_results=params.max_results,
        )
        return ToolResult(
            content=json.dumps(
                {
                    "status": "success",
                    "scope": "workspace",
                    "directory": relative_dir.as_posix() if relative_dir != Path(".") else "",
                    "workspace_root": str(workspace_root.resolve()),
                    "resolved_directory": str(resolved_dir),
                    "count": len(notebooks),
                    "notebooks": notebooks,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


class CreateSessionNotebookParams(BaseModel):
    notebook_path: str = Field(description="当前会话私有 notebook 相对路径，仅允许 .ipynb 文件")
    title: str | None = Field(
        default=None,
        description="可选标题；若未提供 cells，会自动生成一个 markdown 标题 cell",
    )
    cells: list[NotebookCellInput] = Field(
        default_factory=list,
        description="初始化时写入的 notebook cells；为空时仅创建空 notebook 或标题 cell",
    )
    metadata_patch: dict[str, Any] = Field(
        default_factory=dict,
        description="要 merge 到 notebook metadata 的补丁",
    )
    overwrite: bool = Field(
        default=False,
        description="目标 notebook 已存在时是否允许覆盖",
    )


class CreateSessionNotebook(AiasysTool):
    name: str = "CreateSessionNotebook"
    description: str = """在当前工作区中创建 Jupyter notebook（.ipynb 文件）。

适用场景：
- 创建新的 notebook 文件
- 在 notebook 中添加代码单元格（code cell）或 Markdown 单元格
- 为本轮实验创建 scratch notebook
- 在执行前先搭好 notebook 文档骨架

注意：此工具创建的是标准 .ipynb JSON 格式文件，不是纯文本文件。
"""
    params: type[BaseModel] = CreateSessionNotebookParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = CreateSessionNotebookParams.model_validate(kwargs)

        workspace_root = resolve_workspace_root_from_context()
        if workspace_root is None:
            return ToolResult(
                content="当前缺少逻辑工作区上下文，无法创建 notebook。",
                is_error=True,
            )

        try:
            targets = resolve_notebook_targets(
                workspace_root=workspace_root,
                notebook_path=params.notebook_path,
            )
        except ValueError as exc:
            return ToolResult(
                content=str(exc),
                is_error=True,
            )

        if targets.workspace_file_path.exists() and not params.overwrite:
            return ToolResult(
                content=f"Notebook 已存在，若要覆盖请显式设置 overwrite=true: {targets.relative_path.as_posix()}",
                is_error=True,
            )

        notebook = default_notebook()
        if params.metadata_patch:
            notebook["metadata"].update(params.metadata_patch)

        cells = [_make_cell_payload(cell) for cell in params.cells]
        if not cells and params.title:
            cells.append(
                _make_cell_payload(
                    NotebookCellInput(
                        cell_type="markdown",
                        source=f"# {params.title}",
                    )
                )
            )
        notebook["cells"] = cells
        notebook = ensure_notebook_shape(notebook)
        serialized = write_notebook(targets.workspace_file_path, notebook)

        return ToolResult(
            content=json.dumps(
                {
                    "status": "success",
                    "operation": "create",
                    "scope": "workspace",
                    "notebook_path": targets.relative_path.as_posix(),
                    "workspace_root": str(workspace_root.resolve()),
                    "written_to": "workspace",
                    "cell_count": len(notebook["cells"]),
                    "cells": summarize_cells(notebook["cells"]),
                    "size": len(serialized.encode("utf-8")),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


class ReadNotebookOutputsParams(BaseModel):
    notebook_path: str = Field(description="要读取输出摘要的 notebook 相对路径，仅允许 .ipynb 文件")
    start_index: int = Field(
        default=0,
        ge=0,
        description="从第几个有输出的 cell 开始返回",
    )
    max_cells: int = Field(
        default=50,
        ge=1,
        le=200,
        description="最多返回多少个带输出的 cell 摘要",
    )
    only_with_outputs: bool = Field(
        default=True,
        description="是否只返回带 outputs 的 cell",
    )


class ReadNotebookOutputs(AiasysTool):
    name: str = "ReadNotebookOutputs"
    description: str = """读取 notebook 最近输出摘要，不返回原始大 base64 内容。

适用场景：
- 执行后快速检查 notebook 结果
- 只关注有哪些 cell 产出了输出 / 报错
- 在决定是否继续下一轮实验前做轻量结果回看
"""
    params: type[BaseModel] = ReadNotebookOutputsParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = ReadNotebookOutputsParams.model_validate(kwargs)

        workspace_root = resolve_workspace_root_from_context()
        if workspace_root is None:
            return ToolResult(
                content="当前缺少逻辑工作区上下文，无法读取 notebook 输出。",
                is_error=True,
            )

        try:
            targets = resolve_notebook_targets(
                workspace_root=workspace_root,
                notebook_path=params.notebook_path,
            )
        except ValueError as exc:
            return ToolResult(
                content=str(exc),
                is_error=True,
            )

        if not targets.read_path.exists():
            return ToolResult(
                content=f"Notebook 文件不存在: {targets.relative_path.as_posix()}",
                is_error=True,
            )

        try:
            notebook = load_notebook(targets.read_path)
        except json.JSONDecodeError as exc:
            return ToolResult(
                content=f"Notebook JSON 无法解析: {exc}",
                is_error=True,
            )

        cell_summaries = summarize_cells(
            notebook["cells"],
            start_index=0,
            max_cells=None,
            include_output_summaries=True,
        )
        if params.only_with_outputs:
            cell_summaries = [
                item for item in cell_summaries if int(item.get("output_count") or 0) > 0
            ]

        sliced = cell_summaries[params.start_index : params.start_index + params.max_cells]
        next_start_index = params.start_index + len(sliced)
        if next_start_index >= len(cell_summaries):
            next_start_index = None

        return ToolResult(
            content=json.dumps(
                {
                    "status": "success",
                    "operation": "read_outputs",
                    "notebook_path": targets.relative_path.as_posix(),
                    "workspace_root": str(workspace_root.resolve()),
                    "storage_scope": "workspace",
                    "resolved_from": "workspace",
                    "exists": True,
                    "cell_count": len(notebook["cells"]),
                    "matching_cell_count": len(cell_summaries),
                    "returned_cell_count": len(sliced),
                    "start_index": params.start_index,
                    "next_start_index": next_start_index,
                    "cells": sliced,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
