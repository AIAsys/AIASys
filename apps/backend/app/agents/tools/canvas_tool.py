"""Canvas Agent 工具集。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.models.canvas import CanvasBatchOperation, CanvasFile
from app.services.canvas_file_service import get_canvas_file_service
from app.services.history import current_global_workspace, current_workspace

logger = logging.getLogger(__name__)


CanvasScope = Literal["workspace", "global"]


def _resolve_current_workspace_dir() -> Path | None:
    workspace = current_workspace.get()
    if workspace is None:
        return None
    return Path(workspace)


def _resolve_current_global_workspace_dir() -> Path | None:
    global_workspace = current_global_workspace.get()
    if global_workspace is None:
        return None
    return Path(global_workspace)


def _resolve_root(scope: CanvasScope) -> Path:
    if scope == "global":
        root = _resolve_current_global_workspace_dir()
        if root is None:
            raise ValueError("当前上下文未设置全局工作区，无法访问 /global/ Canvas")
        return root.resolve()

    root = _resolve_current_workspace_dir()
    if root is None:
        raise ValueError("当前上下文未设置工作区，无法访问 Canvas")
    return root.resolve()


def _normalize_canvas_path(path_str: str) -> tuple[CanvasScope, str]:
    normalized = str(path_str or "").replace("\\", "/").strip()
    if not normalized:
        raise ValueError("Canvas 路径不能为空")

    scope: CanvasScope = "workspace"
    if normalized.startswith("/workspace/"):
        scope = "workspace"
        normalized = normalized[len("/workspace/") :]
    elif normalized.startswith("/global/"):
        scope = "global"
        normalized = normalized[len("/global/") :]
    elif normalized.startswith("/"):
        raise ValueError("Canvas 路径只支持 /workspace/ 或 /global/ 前缀")

    relative = Path(normalized)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Canvas 路径 `{path_str}` 包含非法路径片段")
    if not normalized.endswith(".canvas"):
        raise ValueError("Canvas 文件必须使用 .canvas 后缀")
    return scope, relative.as_posix()


def _display_path(scope: CanvasScope, relative_path: str) -> str:
    return f"/{'global' if scope == 'global' else 'workspace'}/{relative_path}"


def _canvas_summary(canvas: CanvasFile) -> list[str]:
    return [
        f"节点数: {len(canvas.nodes)}",
        f"边数: {len(canvas.edges)}",
    ]


class CanvasPathParams(BaseModel):
    """Canvas 路径参数。"""

    canvas_path: str = Field(
        description="Canvas 文件路径，支持相对路径、/workspace/... 或 /global/..."
    )


class WriteCanvasParams(CanvasPathParams):
    """写入 Canvas 参数。"""

    canvas: CanvasFile = Field(description="完整 JSON Canvas 内容")


class BatchCanvasOperationsParams(CanvasPathParams):
    """批量修改 Canvas 参数。"""

    operations: list[CanvasBatchOperation] = Field(description="批量操作列表", min_length=1)


class ReadCanvas(AiasysTool):
    """读取 JSON Canvas 文件。"""

    name: str = "ReadCanvas"
    description: str = """
读取 JSON Canvas 文件。

参数：
- canvas_path: Canvas 文件路径，支持相对路径、/workspace/... 或 /global/...。

返回完整 canvas JSON，包含 nodes 和 edges。AIASys 只解释 JSON Canvas 核心字段，未知扩展字段会透传。
"""
    params: type[BaseModel] = CanvasPathParams
    parameters: dict[str, Any] = CanvasPathParams.model_json_schema()

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        del ctx
        params = CanvasPathParams.model_validate(kwargs)
        try:
            scope, relative_path = _normalize_canvas_path(params.canvas_path)
            canvas = get_canvas_file_service().read_canvas(_resolve_root(scope), relative_path)
            return ToolResult(
                content="\n".join(
                    [
                        f"Canvas: {_display_path(scope, relative_path)}",
                        *_canvas_summary(canvas),
                    ]
                ),
                artifacts=[
                    {
                        "canvas": {
                            "scope": scope,
                            "relative_path": relative_path,
                            "display_path": _display_path(scope, relative_path),
                            "document": canvas.model_dump(mode="json", exclude_none=True),
                        }
                    }
                ],
            )
        except Exception as exc:
            logger.error("读取 Canvas 失败: %s", exc, exc_info=True)
            return ToolResult(content=f"读取 Canvas 失败: {exc}", is_error=True)


class WriteCanvas(AiasysTool):
    """覆盖写入 JSON Canvas 文件。"""

    name: str = "WriteCanvas"
    description: str = """
覆盖写入 JSON Canvas 文件。

参数：
- canvas_path: Canvas 文件路径，支持相对路径、/workspace/... 或 /global/...。
- canvas: 完整 JSON Canvas 内容。

写入时会校验节点和边的一致性。非法边会被规范化过滤。
"""
    params: type[BaseModel] = WriteCanvasParams
    parameters: dict[str, Any] = WriteCanvasParams.model_json_schema()

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        del ctx
        params = WriteCanvasParams.model_validate(kwargs)
        try:
            scope, relative_path = _normalize_canvas_path(params.canvas_path)
            canvas = get_canvas_file_service().write_canvas(
                _resolve_root(scope),
                relative_path,
                params.canvas,
            )
            return ToolResult(
                content="\n".join(
                    [
                        f"Canvas 已写入: {_display_path(scope, relative_path)}",
                        *_canvas_summary(canvas),
                    ]
                ),
                artifacts=[
                    {
                        "canvas": {
                            "scope": scope,
                            "relative_path": relative_path,
                            "display_path": _display_path(scope, relative_path),
                            "document": canvas.model_dump(mode="json", exclude_none=True),
                        }
                    }
                ],
            )
        except Exception as exc:
            logger.error("写入 Canvas 失败: %s", exc, exc_info=True)
            return ToolResult(content=f"写入 Canvas 失败: {exc}", is_error=True)


class BatchCanvasOperations(AiasysTool):
    """批量修改 JSON Canvas 文件。"""

    name: str = "BatchCanvasOperations"
    description: str = """
批量修改 JSON Canvas 文件。

参数：
- canvas_path: Canvas 文件路径，支持相对路径、/workspace/... 或 /global/...。
- operations: 操作列表，支持 add_node、update_node、remove_node、add_edge、update_edge、remove_edge。

适合让 Agent 一次性增删改多个节点和边，避免反复读写同一个 .canvas 文件。
"""
    params: type[BaseModel] = BatchCanvasOperationsParams
    parameters: dict[str, Any] = BatchCanvasOperationsParams.model_json_schema()

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        del ctx
        params = BatchCanvasOperationsParams.model_validate(kwargs)
        try:
            scope, relative_path = _normalize_canvas_path(params.canvas_path)
            canvas = get_canvas_file_service().batch_operations(
                _resolve_root(scope),
                relative_path,
                params.operations,
            )
            return ToolResult(
                content="\n".join(
                    [
                        f"Canvas 已批量更新: {_display_path(scope, relative_path)}",
                        f"操作数: {len(params.operations)}",
                        *_canvas_summary(canvas),
                    ]
                ),
                artifacts=[
                    {
                        "canvas": {
                            "scope": scope,
                            "relative_path": relative_path,
                            "display_path": _display_path(scope, relative_path),
                            "document": canvas.model_dump(mode="json", exclude_none=True),
                        }
                    }
                ],
            )
        except Exception as exc:
            logger.error("批量修改 Canvas 失败: %s", exc, exc_info=True)
            return ToolResult(content=f"批量修改 Canvas 失败: {exc}", is_error=True)
