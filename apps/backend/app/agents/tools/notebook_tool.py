"""
Notebook 生命周期管理聚合工具。

将创建 notebook、读取输出摘要、执行 notebook 三种操作统一到一个入口，
减少 Agent 上下文工具数量，遵循 Hermes 统一聚合工具风格。

保留的独立工具：
- EditNotebookFile：文件级编辑（已是聚合模式）
- ListSessionNotebooks：列目录（语义不同）
- LocalIPythonBox：底层执行引擎
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult


class NotebookAction(str, Enum):
    """Notebook 管理操作类型。"""

    CREATE = "create"
    READ_OUTPUTS = "read_outputs"
    RUN = "run"
    PATCH = "patch"


class NotebookRunScope(str, Enum):
    """Notebook 执行范围。"""

    CELL = "cell"
    RANGE = "range"
    ALL = "all"


class ManageNotebookParams(BaseModel):
    """ManageNotebook 参数。"""

    action: NotebookAction = Field(
        description="操作类型：create（创建）、read_outputs（读取输出摘要）、run（执行）、patch（局部编辑 cell）"
    )
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
    # --- read_outputs 专用参数 ---
    start_index: int = Field(
        default=0,
        ge=0,
        description="read_outputs 时从第几个有输出的 cell 开始返回",
    )
    max_cells: int = Field(
        default=50,
        ge=1,
        le=200,
        description="read_outputs 时最多返回多少个带输出的 cell 摘要",
    )
    only_with_outputs: bool = Field(
        default=True,
        description="read_outputs 时是否只返回带 outputs 的 cell",
    )
    # --- patch 专用参数 ---
    cell_id: str | None = Field(
        default=None,
        description="patch 时目标 cell id，优先于 cell_index",
    )
    cell_index: int | None = Field(
        default=None,
        description="patch 时目标 cell 下标",
    )
    patches: list[dict[str, str]] = Field(
        default_factory=list,
        description="patch 时使用的 find/replace 列表",
    )
    # --- run 专用参数 ---
    scope: NotebookRunScope = Field(
        default=NotebookRunScope.ALL,
        description="run 时执行范围：cell / range / all",
    )
    cell_id: str | None = Field(
        default=None,
        description="run 时 scope=cell 的目标 cell id，优先于 cell_index",
    )
    cell_index: int | None = Field(
        default=None,
        description="run 时 scope=cell 的目标 cell 下标",
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
    管理 notebook 生命周期：创建、读取输出摘要、执行。

    目标是把 notebook 工作流的核心三步（创建 -> 执行 -> 查看结果）
    统一到一个入口，减少 Agent 上下文工具数量。
    """

    name: str = "ManageNotebook"
    description: str = """管理当前逻辑工作区中的 `.ipynb` notebook 文件。

支持操作：
- `create`：创建新 notebook（可带初始 cells 和标题）
- `read_outputs`：读取 notebook 最近输出摘要（不返回原始大 base64）
- `run`：按 notebook 语义执行 code cell，默认把安全输出写回 notebook

限制：
- 只允许操作当前逻辑工作区中的 `.ipynb` 文件
- 不允许越界路径或 `.session` 内部路径
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

        return ToolResult(
            content=f"未知的 notebook 操作: {params.action.value}",
            is_error=True,
        )
