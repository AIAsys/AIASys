"""
Notebook 文件编辑工具。

面向逻辑工作区根目录中的 `.ipynb` 文件，提供 notebook / cell 级别的
结构化读写能力，避免 Agent 通过原始 JSON 字符串误改 notebook 结构。
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.tools.notebook_utils import (
    apply_patches,
    deep_merge,
    ensure_notebook_shape,
    find_cell_index,
    load_notebook,
    resolve_notebook_targets,
    resolve_session_root_from_context,
    resolve_workspace_root_from_context,
    sanitize_notebook_for_agent,
    source_to_text,
    summarize_cells,
    write_notebook,
)
from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult


class NotebookOperation(str, Enum):
    """Notebook 读写操作类型。"""

    READ = "read"
    REPLACE = "replace"
    UPSERT_CELL = "upsert_cell"
    DELETE_CELL = "delete_cell"
    UPDATE_METADATA = "update_metadata"
    CLEAR_CELL_OUTPUTS = "clear_cell_outputs"
    PATCH_CELL = "patch_cell"


class NotebookCellInput(BaseModel):
    """Notebook cell 输入。"""

    cell_type: Literal["code", "markdown", "raw"] = Field(
        description="cell 类型：code / markdown / raw"
    )
    source: str | list[str] = Field(
        default="",
        description="cell 内容，允许字符串或字符串数组",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="cell 元数据",
    )
    outputs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="code cell 输出列表；markdown/raw 默认忽略",
    )
    execution_count: int | None = Field(
        default=None,
        description="code cell 的 execution_count",
    )
    cell_id: str | None = Field(
        default=None,
        description="可选 cell id；为空时自动生成",
    )


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


class ReadNotebook(AiasysTool):
    """读取逻辑工作区中的 notebook 文件摘要。"""

    name: str = "ReadNotebook"
    description: str = (
        "读取逻辑工作区中的 `.ipynb` notebook 文件，返回 cell 摘要。"
        "支持分页读取避免上下文爆炸，可选返回完整 notebook JSON。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "notebook_path": {
                "type": "string",
                "description": "逻辑工作区中的 notebook 相对路径，仅允许 .ipynb 文件",
            },
            "include_full_notebook": {
                "type": "boolean",
                "description": "是否返回完整 notebook JSON",
            },
            "start_index": {
                "type": "integer",
                "description": "从哪个 cell 下标开始返回摘要",
            },
            "max_cells": {
                "type": "integer",
                "description": "最多返回多少个 cell 摘要，避免上下文爆炸",
            },
            "include_output_summaries": {
                "type": "boolean",
                "description": "是否返回安全输出摘要（不会包含 base64 原文）",
            },
        },
        "required": ["notebook_path"],
    }

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        notebook_path = str(kwargs.get("notebook_path") or "").strip()
        include_full_notebook = bool(kwargs.get("include_full_notebook", False))
        start_index = int(kwargs.get("start_index", 0))
        max_cells = int(kwargs.get("max_cells", 50))
        include_output_summaries = bool(kwargs.get("include_output_summaries", True))

        workspace_root = resolve_workspace_root_from_context()
        if workspace_root is None:
            return ToolResult(
                content="当前缺少逻辑工作区上下文，无法读取 notebook 文件。",
                is_error=True,
            )

        try:
            targets = resolve_notebook_targets(
                workspace_root=workspace_root,
                notebook_path=notebook_path,
            )
        except ValueError as exc:
            return ToolResult(
                content=str(exc),
                is_error=True,
            )

        workspace_root_resolved = workspace_root.resolve()
        file_path = targets.read_path

        if not file_path.exists():
            return ToolResult(
                content=json.dumps(
                    {
                        "status": "missing",
                        "operation": "read",
                        "notebook_path": targets.relative_path.as_posix(),
                        "workspace_root": str(workspace_root_resolved),
                        "storage_scope": "workspace",
                        "exists": False,
                        "cell_count": 0,
                        "returned_cell_count": 0,
                        "start_index": max(0, start_index),
                        "next_start_index": None,
                        "cells": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )

        try:
            notebook = load_notebook(file_path)
        except json.JSONDecodeError as exc:
            return ToolResult(
                content=f"Notebook JSON 无法解析: {exc}",
                is_error=True,
            )

        response: dict[str, Any] = {
            "status": "success",
            "operation": "read",
            "notebook_path": targets.relative_path.as_posix(),
            "workspace_root": str(workspace_root_resolved),
            "storage_scope": "workspace",
            "resolved_from": "workspace",
            "exists": True,
            "cell_count": len(notebook["cells"]),
            "returned_cell_count": 0,
            "start_index": max(0, start_index),
            "next_start_index": None,
            "cells": [],
            "metadata": notebook["metadata"],
            "nbformat": notebook["nbformat"],
            "nbformat_minor": notebook["nbformat_minor"],
        }
        response["cells"] = summarize_cells(
            notebook["cells"],
            start_index=max(0, start_index),
            max_cells=max(1, max_cells),
            include_output_summaries=include_output_summaries,
        )
        response["returned_cell_count"] = len(response["cells"])
        next_start = response["start_index"] + response["returned_cell_count"]
        response["next_start_index"] = next_start if next_start < len(notebook["cells"]) else None
        if include_full_notebook:
            response["notebook"] = sanitize_notebook_for_agent(notebook)
            response["notebook_sanitized"] = True
        return ToolResult(content=json.dumps(response, ensure_ascii=False, indent=2))


class EditNotebookParams(BaseModel):
    """EditNotebookFile 参数。"""

    operation: NotebookOperation = Field(description="Notebook 读写操作类型")
    notebook_path: str = Field(description="逻辑工作区中的 notebook 相对路径，仅允许 .ipynb 文件")
    include_full_notebook: bool = Field(
        default=False,
        description="read 时是否返回完整 notebook JSON",
    )
    start_index: int = Field(
        default=0,
        ge=0,
        description="read 时从哪个 cell 下标开始返回摘要",
    )
    max_cells: int = Field(
        default=50,
        ge=1,
        le=200,
        description="read 时最多返回多少个 cell 摘要，避免上下文爆炸",
    )
    include_output_summaries: bool = Field(
        default=True,
        description="read 时是否返回安全输出摘要（不会包含 base64 原文）",
    )
    create_if_missing: bool = Field(
        default=True,
        description="文件不存在时是否允许自动创建",
    )
    notebook: dict[str, Any] | None = Field(
        default=None,
        description="replace 时要写入的完整 notebook 内容",
    )
    cell: NotebookCellInput | None = Field(
        default=None,
        description="upsert_cell 时要写入的 cell 内容",
    )
    cell_id: str | None = Field(
        default=None,
        description="目标 cell id；delete / clear / upsert update 可用",
    )
    cell_index: int | None = Field(
        default=None,
        description="目标 cell 下标；delete / clear / upsert update 可用",
    )
    insert_index: int | None = Field(
        default=None,
        description="upsert_cell 创建新 cell 时的插入下标；为空时默认追加到末尾",
    )
    metadata_patch: dict[str, Any] | None = Field(
        default=None,
        description="update_metadata 时要 merge 的 notebook metadata",
    )
    patches: list[dict[str, str]] | None = Field(
        default=None,
        description="patch_cell 时的 find/replace 列表；每个元素包含 find 和 replace 字段",
    )


class EditNotebookFile(AiasysTool):
    """编辑逻辑工作区中的 notebook 文件。

    支持 read、replace、upsert_cell、delete_cell、update_metadata、clear_cell_outputs、patch_cell 操作。
    """

    name: str = "EditNotebookFile"
    description: str = """编辑逻辑工作区中的 `.ipynb` notebook 文件。

支持操作：
- `read`：读取 notebook 摘要，可分页，可选返回清洗后的完整 notebook
- `replace`：完整替换 notebook 内容
- `upsert_cell`：按 cell_id / cell_index 更新现有 cell，或创建新 cell
- `delete_cell`：删除指定 cell
- `update_metadata`：深度合并 notebook metadata
- `clear_cell_outputs`：清空指定 code cell 的 outputs 和 execution_count
- `patch_cell`：对指定 cell 的 source 做局部 find/replace 修改

限制：
- 只允许编辑当前逻辑工作区中的 `.ipynb` 文件
- 不允许越界路径或 `.session` 内部路径
"""
    params: type[BaseModel] = EditNotebookParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = EditNotebookParams.model_validate(kwargs)

        if params.operation == NotebookOperation.READ:
            return await ReadNotebook().invoke(
                ctx,
                notebook_path=params.notebook_path,
                include_full_notebook=params.include_full_notebook,
                start_index=params.start_index,
                max_cells=params.max_cells,
                include_output_summaries=params.include_output_summaries,
            )

        workspace_root = resolve_workspace_root_from_context()
        if workspace_root is None:
            return ToolResult(
                content="当前缺少逻辑工作区上下文，无法编辑 notebook 文件。",
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

        workspace_root_resolved = workspace_root.resolve()
        file_path = targets.read_path

        try:
            notebook = load_notebook(file_path)
        except json.JSONDecodeError as exc:
            return ToolResult(
                content=f"Notebook JSON 无法解析: {exc}",
                is_error=True,
            )

        if not file_path.exists() and not params.create_if_missing:
            return ToolResult(
                content=f"Notebook 文件不存在且不允许创建: {targets.relative_path.as_posix()}",
                is_error=True,
            )

        if params.operation == NotebookOperation.REPLACE:
            if not isinstance(params.notebook, dict):
                return ToolResult(
                    content="replace 操作必须提供完整 notebook 字典。",
                    is_error=True,
                )
            notebook = ensure_notebook_shape(params.notebook)

        elif params.operation == NotebookOperation.UPDATE_METADATA:
            if not isinstance(params.metadata_patch, dict):
                return ToolResult(
                    content="update_metadata 操作必须提供 metadata_patch。",
                    is_error=True,
                )
            notebook["metadata"] = deep_merge(notebook["metadata"], params.metadata_patch)

        elif params.operation == NotebookOperation.UPSERT_CELL:
            if params.cell is None:
                return ToolResult(
                    content="upsert_cell 操作必须提供 cell。",
                    is_error=True,
                )
            target_index = find_cell_index(
                notebook,
                cell_id=params.cell_id or params.cell.cell_id,
                cell_index=params.cell_index,
            )
            payload = _make_cell_payload(params.cell)
            if target_index is None:
                insert_index = (
                    len(notebook["cells"])
                    if params.insert_index is None
                    else max(0, min(params.insert_index, len(notebook["cells"])))
                )
                notebook["cells"].insert(insert_index, payload)
            else:
                existing = notebook["cells"][target_index]
                notebook["cells"][target_index] = deep_merge(existing, payload)

        elif params.operation == NotebookOperation.DELETE_CELL:
            target_index = find_cell_index(
                notebook,
                cell_id=params.cell_id,
                cell_index=params.cell_index,
            )
            if target_index is None:
                return ToolResult(
                    content="未找到要删除的 cell。",
                    is_error=True,
                )
            notebook["cells"].pop(target_index)

        elif params.operation == NotebookOperation.CLEAR_CELL_OUTPUTS:
            target_index = find_cell_index(
                notebook,
                cell_id=params.cell_id,
                cell_index=params.cell_index,
            )
            if target_index is None:
                return ToolResult(
                    content="未找到要清空输出的 cell。",
                    is_error=True,
                )
            cell = notebook["cells"][target_index]
            if cell.get("cell_type") != "code":
                return ToolResult(
                    content="只有 code cell 支持清空 outputs。",
                    is_error=True,
                )
            cell["outputs"] = []
            cell["execution_count"] = None

        elif params.operation == NotebookOperation.PATCH_CELL:
            if not params.patches:
                return ToolResult(
                    content="patch_cell 操作必须提供 patches 列表。",
                    is_error=True,
                )
            target_index = find_cell_index(
                notebook,
                cell_id=params.cell_id,
                cell_index=params.cell_index,
            )
            if target_index is None:
                return ToolResult(
                    content="未找到要 patch 的 cell。",
                    is_error=True,
                )
            cell = notebook["cells"][target_index]
            original_source = source_to_text(cell.get("source", ""))
            try:
                patched_source = apply_patches(original_source, params.patches)
            except ValueError as exc:
                return ToolResult(
                    content=f"patch 应用失败: {exc}",
                    is_error=True,
                )
            cell["source"] = patched_source

        notebook = ensure_notebook_shape(notebook)
        serialized = write_notebook(targets.write_path, notebook)

        return ToolResult(
            content=json.dumps(
                {
                    "status": "success",
                    "operation": params.operation.value,
                    "notebook_path": targets.relative_path.as_posix(),
                    "workspace_root": str(workspace_root_resolved),
                    "storage_scope": "workspace",
                    "written_to": "workspace",
                    "exists": True,
                    "cell_count": len(notebook["cells"]),
                    "cells": summarize_cells(notebook["cells"]),
                    "size": len(serialized.encode("utf-8")),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
