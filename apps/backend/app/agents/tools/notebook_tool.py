"""
Notebook 生命周期管理聚合工具。

将 notebook 的创建、读取、编辑、执行、结果查看统一到一个入口，
减少 Agent 上下文工具数量，遵循 Hermes 统一聚合工具风格。

保留的独立工具：
- ListSessionNotebooks：列目录（语义不同）
- LocalIPythonBox：底层执行引擎
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult


def _parse_json_string(value: Any) -> Any:
    """如果值是 JSON 字符串，尝试解析为 Python 对象。"""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    return value


class NotebookAction(str, Enum):
    """Notebook 管理操作类型。"""

    CREATE = "create"
    READ = "read"
    READ_OUTPUTS = "read_outputs"
    RUN = "run"
    PATCH = "patch"
    EDIT = "edit"


class NotebookEditOperation(str, Enum):
    """edit action 支持的子操作类型。"""

    UPSERT_CELL = "upsert_cell"
    DELETE_CELL = "delete_cell"
    PATCH_CELL = "patch_cell"
    CLEAR_OUTPUTS = "clear_outputs"
    UPDATE_METADATA = "update_metadata"
    REPLACE = "replace"


class NotebookRunScope(str, Enum):
    """Notebook 执行范围。"""

    CELL = "cell"
    RANGE = "range"
    ALL = "all"


class ManageNotebookParams(BaseModel):
    """ManageNotebook 参数。"""

    action: NotebookAction = Field(
        description="操作类型：create（创建）、read（读取内容）、read_outputs（读取输出摘要）、run（执行 code cell）、edit（编辑 notebook）"
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        # action 别名
        action = values.get("action")
        if isinstance(action, str):
            alias_map = {
                "run_cell": "run",
                "execute": "run",
                "exec": "run",
                "create_notebook": "create",
                "new": "create",
                "add_cell": "edit",
                "delete_cell": "edit",
                "remove_cell": "edit",
            }
            normalized = alias_map.get(action.lower(), action)
            if normalized != action:
                values["action"] = normalized
        # path → notebook_path 别名
        if "path" in values and "notebook_path" not in values:
            values["notebook_path"] = values.pop("path")
        # cells / patches / cell / notebook / metadata_patch JSON 字符串解析
        for key in ("cells", "patches", "cell", "notebook", "metadata_patch"):
            if key in values:
                values[key] = _parse_json_string(values[key])
        return values

    # 所有操作共有的核心参数
    notebook_path: str = Field(description="逻辑工作区中的 notebook 相对路径，仅允许 .ipynb 文件")

    # --- create 专用参数 ---
    title: str | None = Field(
        default=None,
        description="create 时可选标题；若未提供 cells，会自动生成一个 markdown 标题 cell",
    )
    cells: list[dict[str, Any]] = Field(
        default_factory=list,
        description="create 时初始化写入的 notebook cells；为空时仅创建空 notebook 或标题 cell",
    )
    metadata_patch: dict[str, Any] = Field(
        default_factory=dict,
        description="create 时要 merge 到 notebook metadata 的补丁",
    )
    overwrite: bool = Field(
        default=False,
        description="create 时目标 notebook 已存在是否允许覆盖",
    )

    # --- read / read_outputs 共用参数 ---
    start_index: int = Field(
        default=0,
        ge=0,
        description="read / read_outputs 时从第几个 cell 开始返回",
    )
    max_cells: int = Field(
        default=50,
        ge=1,
        le=200,
        description="read / read_outputs 时最多返回多少个 cell 摘要",
    )
    include_output_summaries: bool = Field(
        default=True,
        description="read 时是否返回安全输出摘要（不会包含 base64 原文）",
    )
    include_full_notebook: bool = Field(
        default=False,
        description="read 时是否返回完整 notebook JSON",
    )
    only_with_outputs: bool = Field(
        default=True,
        description="read_outputs 时是否只返回带 outputs 的 cell",
    )

    # --- edit / patch 专用参数 ---
    edit_operation: NotebookEditOperation | None = Field(
        default=None,
        description="edit 时的子操作类型：upsert_cell / delete_cell / patch_cell / clear_outputs / update_metadata / replace",
    )
    cell: dict[str, Any] | None = Field(
        default=None,
        description="edit(upsert_cell) 时要写入的 cell 内容字典，含 cell_type/source/metadata 等字段",
    )
    cell_id: str | None = Field(
        default=None,
        description="edit / run / patch 时目标 cell id，优先于 cell_index",
    )
    cell_index: int | None = Field(
        default=None,
        description="edit / run / patch 时目标 cell 下标",
    )
    insert_index: int | None = Field(
        default=None,
        description="edit(upsert_cell) 创建新 cell 时的插入下标；为空时默认追加到末尾",
    )
    patches: list[dict[str, str]] = Field(
        default_factory=list,
        description="edit(patch_cell) / patch 时使用的 find/replace 列表",
    )
    create_if_missing: bool = Field(
        default=True,
        description="edit 时文件不存在是否允许自动创建",
    )
    notebook: dict[str, Any] | None = Field(
        default=None,
        description="edit(replace) 时要写入的完整 notebook 内容",
    )

    # --- run 专用参数 ---
    scope: NotebookRunScope = Field(
        default=NotebookRunScope.ALL,
        description="run 时执行范围：cell / range / all",
    )
    run_start_index: int | None = Field(
        default=None,
        description="run 时 scope=range 的起始 cell 下标（含）",
    )
    end_index: int | None = Field(
        default=None,
        description="run 时 scope=range 的结束 cell 下标（含）",
    )
    restart_runtime: bool = Field(
        default=False,
        description="run 时执行前是否重启当前会话 runtime",
    )
    clear_previous_outputs: bool = Field(
        default=True,
        description="run 时执行前是否清空目标 code cell 旧 outputs",
    )
    stop_on_error: bool = Field(
        default=True,
        description="run 时遇到失败后是否停止后续 cell",
    )
    persist_outputs: bool = Field(
        default=True,
        description="run 时执行后是否把输出写回 notebook",
    )


class ManageNotebook(AiasysTool):
    """
    管理 notebook 生命周期：创建、读取、编辑、执行、查看结果。

    目标是把 notebook 工作流统一到一个入口，减少 Agent 上下文工具数量。
    """

    name: str = "ManageNotebook"
    description: str = """管理当前工作区中的 Jupyter notebook（.ipynb）文件：创建、读取、编辑、执行、查看结果。

参数说明：
- `action`（必填）：操作类型，必须是以下之一：
  - `"create"`：创建新 notebook
  - `"read"`：读取 notebook 内容摘要（cell 列表、源码、输出等）
  - `"read_outputs"`：读取 notebook 输出摘要（只看有输出的 cell）
  - `"run"`：执行 notebook 中的 code cell
  - `"edit"`：编辑 notebook（添加/删除/修改 cell、更新 metadata 等）
- `notebook_path`（必填）：notebook 的相对路径，如 `"analysis.ipynb"`

各 action 的用法：

**create** —— 创建新 notebook 文件
- 可选 `title`：自动生成一个 markdown 标题 cell
- 可选 `cells`：初始化时写入的 cell 列表，每个 cell 是 {"cell_type": "code"|"markdown", "source": "..."}
- 可选 `overwrite`：已存在时是否覆盖

**read** —— 读取 notebook 内容
- 可选 `start_index`：从第几个 cell 开始读取（默认 0）
- 可选 `max_cells`：最多返回多少个 cell（默认 50）
- 可选 `include_output_summaries`：是否包含输出摘要（默认 true）
- 可选 `include_full_notebook`：是否返回完整 notebook JSON（默认 false）

**read_outputs** —— 只看有输出的 cell
- 可选 `start_index`：从第几个有输出的 cell 开始
- 可选 `max_cells`：最多返回多少个
- 可选 `only_with_outputs`：是否只返回有输出的 cell（默认 true）

**run** —— 执行 code cell
- 可选 `scope`：执行范围，all（全部）/ cell（单个）/ range（范围）
- 可选 `cell_id` / `cell_index`：scope=cell 时的目标
- 可选 `run_start_index` / `end_index`：scope=range 时的范围
- 可选 `restart_runtime`：执行前是否重启 runtime
- 可选 `clear_previous_outputs`：执行前是否清空旧输出（默认 true）
- 可选 `stop_on_error`：遇到错误是否停止（默认 true）
- 可选 `persist_outputs`：执行后是否写回 notebook（默认 true）

**edit** —— 编辑 notebook 内容
- 必填 `edit_operation`：子操作类型
  - `"upsert_cell"`：添加新 cell 或更新现有 cell
    - 提供 `cell`：{"cell_type": "code"|"markdown", "source": "..."}
    - 可选 `cell_id` / `cell_index`：目标 cell；不存在时创建新 cell
    - 可选 `insert_index`：新 cell 插入位置（默认追加到末尾）
  - `"delete_cell"`：删除指定 cell
    - 提供 `cell_id` 或 `cell_index`
  - `"patch_cell"`：对 cell source 做局部 find/replace
    - 提供 `cell_id` 或 `cell_index`
    - 提供 `patches`：[{"old": "...", "new": "..."}]
  - `"clear_outputs"`：清空 code cell 的输出
    - 提供 `cell_id` 或 `cell_index`
  - `"update_metadata"`：更新 notebook metadata
    - 提供 `metadata_patch`：{"kernelspec": {"name": "python3"}}
  - `"replace"`：完整替换整个 notebook
    - 提供 `notebook`：完整的 notebook JSON 字典

限制：
- 只允许操作当前工作区中的 `.ipynb` 文件
- 不允许越界路径或 `.aiasys` 内部路径

为什么用 ManageNotebook 而不是 WriteFile + Shell + RunCode：
- **创建 notebook**：自动生成规范 nbformat 格式（nbformat 4.5、metadata、cell id），Jupyter 可以直接打开。用 WriteFile 手写 JSON 容易缺少必需字段，导致格式错误
- **读取 notebook**：返回结构化 cell 摘要，支持分页，自动过滤 base64 大输出。Shell cat 返回原始 JSON 难以阅读
- **编辑 notebook**：支持 cell 级别的增删改，不是整文件重写。WriteFile 重写可能丢失格式或误删其他 cell
- **执行 notebook**：每个 notebook 使用独立的 IPython kernel，变量状态按 notebook 隔离。RunCode 在全局环境中执行，变量会互相污染
- **执行结果**：自动写回 notebook 的 outputs 字段，后续可以直接读取。RunCode 的结果不会自动保存到 .ipynb
- **并发安全**：自动加锁防止多个请求同时执行同一个 notebook
"""
    params: type[BaseModel] = ManageNotebookParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = ManageNotebookParams.model_validate(kwargs)

        if params.action == NotebookAction.CREATE:
            from app.agents.tools.notebook_file_tool import NotebookCellInput
            from app.agents.tools.notebook_session_tool import (
                CreateSessionNotebook,
            )

            tool = CreateSessionNotebook()
            tool_kwargs: dict[str, Any] = {
                "notebook_path": params.notebook_path,
                "overwrite": params.overwrite,
                "metadata_patch": params.metadata_patch,
            }
            if params.title is not None:
                tool_kwargs["title"] = params.title
            if params.cells:
                tool_kwargs["cells"] = [
                    NotebookCellInput.model_validate(cell) for cell in params.cells
                ]
            return await tool.invoke(ctx, **tool_kwargs)

        if params.action == NotebookAction.READ:
            from app.agents.tools.notebook_file_tool import ReadNotebook

            tool = ReadNotebook()
            return await tool.invoke(
                ctx,
                notebook_path=params.notebook_path,
                start_index=params.start_index,
                max_cells=params.max_cells,
                include_output_summaries=params.include_output_summaries,
                include_full_notebook=params.include_full_notebook,
            )

        if params.action == NotebookAction.READ_OUTPUTS:
            from app.agents.tools.notebook_session_tool import ReadNotebookOutputs

            tool = ReadNotebookOutputs()
            return await tool.invoke(
                ctx,
                notebook_path=params.notebook_path,
                start_index=params.start_index,
                max_cells=params.max_cells,
                only_with_outputs=params.only_with_outputs,
            )

        if params.action == NotebookAction.RUN:
            from app.agents.tools.notebook_runtime_tool import RunNotebook

            tool = RunNotebook()
            tool_kwargs: dict[str, Any] = {
                "notebook_path": params.notebook_path,
                "scope": params.scope.value,
                "restart_runtime": params.restart_runtime,
                "clear_previous_outputs": params.clear_previous_outputs,
                "stop_on_error": params.stop_on_error,
                "persist_outputs": params.persist_outputs,
            }
            if params.cell_id is not None:
                tool_kwargs["cell_id"] = params.cell_id
            if params.cell_index is not None:
                tool_kwargs["cell_index"] = params.cell_index
            if params.run_start_index is not None:
                tool_kwargs["start_index"] = params.run_start_index
            if params.end_index is not None:
                tool_kwargs["end_index"] = params.end_index
            return await tool.invoke(ctx, **tool_kwargs)

        if params.action == NotebookAction.PATCH:
            from app.agents.tools.notebook_file_tool import EditNotebookFile

            tool = EditNotebookFile()
            return await tool.invoke(
                ctx,
                operation="patch_cell",
                notebook_path=params.notebook_path,
                cell_id=params.cell_id,
                cell_index=params.cell_index,
                patches=params.patches,
            )

        if params.action == NotebookAction.EDIT:
            from app.agents.tools.notebook_file_tool import EditNotebookFile

            if params.edit_operation is None:
                return ToolResult(
                    content="edit action 必须提供 edit_operation 参数",
                    is_error=True,
                )

            tool = EditNotebookFile()
            edit_op = params.edit_operation.value

            # 构建透传参数
            tool_kwargs: dict[str, Any] = {
                "operation": edit_op,
                "notebook_path": params.notebook_path,
            }

            # 根据子操作类型添加对应参数
            if edit_op == "upsert_cell":
                if params.cell is not None:
                    tool_kwargs["cell"] = params.cell
                if params.cell_id is not None:
                    tool_kwargs["cell_id"] = params.cell_id
                if params.cell_index is not None:
                    tool_kwargs["cell_index"] = params.cell_index
                if params.insert_index is not None:
                    tool_kwargs["insert_index"] = params.insert_index
                tool_kwargs["create_if_missing"] = params.create_if_missing

            elif edit_op == "delete_cell":
                if params.cell_id is not None:
                    tool_kwargs["cell_id"] = params.cell_id
                if params.cell_index is not None:
                    tool_kwargs["cell_index"] = params.cell_index

            elif edit_op == "patch_cell":
                if params.cell_id is not None:
                    tool_kwargs["cell_id"] = params.cell_id
                if params.cell_index is not None:
                    tool_kwargs["cell_index"] = params.cell_index
                if params.patches:
                    tool_kwargs["patches"] = params.patches

            elif edit_op == "clear_outputs":
                if params.cell_id is not None:
                    tool_kwargs["cell_id"] = params.cell_id
                if params.cell_index is not None:
                    tool_kwargs["cell_index"] = params.cell_index

            elif edit_op == "update_metadata":
                if params.metadata_patch:
                    tool_kwargs["metadata_patch"] = params.metadata_patch

            elif edit_op == "replace":
                if params.notebook is not None:
                    tool_kwargs["notebook"] = params.notebook
                tool_kwargs["create_if_missing"] = params.create_if_missing

            return await tool.invoke(ctx, **tool_kwargs)

        return ToolResult(
            content=f"未知的 notebook 操作: {params.action.value}",
            is_error=True,
        )
