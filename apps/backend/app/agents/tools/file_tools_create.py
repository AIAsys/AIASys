"""CreateFile Agent 工具。

为 Agent 提供类型感知的文件创建能力，通过 FileInitializerRegistry
统一处理所有文件类型的初始化逻辑。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agents.tools.file_tools_base import _resolve_file_path
from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.file_history import file_history_service
from app.services.file_initializer import get_file_initializer_registry

logger = logging.getLogger(__name__)


class CreateFileParams(BaseModel):
    """CreateFile 参数。"""

    path: str = Field(description="文件路径，相对于当前工作区。支持 /workspace/ 和 /global/ 前缀。")
    file_type: str | None = Field(
        default=None,
        description=(
            "文件类型标识。可选值：text（普通文本）、canvas（Canvas 画布）、"
            "knowledge_base（知识库）、knowledge_graph（知识图谱）。"
            "不传则从文件后缀自动推断。"
        ),
    )
    content: str = Field(
        default="",
        description="文件内容。text 类型直接写入，canvas 类型默认写入空骨架。",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="类型相关参数。knowledge_base 可传 name/description；"
        "knowledge_graph 可传 graph_id/name/description。",
    )
    overwrite: bool = Field(
        default=False,
        description="目标文件已存在时是否允许覆盖。",
    )


class CreateFile(AiasysTool):
    """创建文件，支持多种文件类型。

    与 WriteFile 的区别：
    - WriteFile：低层级工具，裸写字节，不感知文件类型语义
    - CreateFile：类型感知工具，自动执行初始化（如知识库创建 SQLite 表结构）
    """

    name: str = "CreateFile"
    description: str = """在当前工作区或全局工作区中创建文件。

支持的文件类型：
- text：普通文本文件（.md、.py、.json 等），写入 content
- canvas：Canvas 画布文件（.canvas），默认写入空 JSON 骨架
- knowledge_base：知识库（.kb.db），自动初始化 SQLite 结构和元数据
- knowledge_graph：知识图谱（.graph.db），自动初始化 5 张表和元数据

参数：
- path: 文件路径，支持 /workspace/ 或 /global/ 前缀
- file_type: 文件类型（可选，不传则从后缀推断）
- content: 文件内容（text/canvas 类型使用）
- params: 类型相关参数
- overwrite: 是否覆盖已存在的文件
"""
    params: type[BaseModel] = CreateFileParams
    parameters: dict[str, Any] = CreateFileParams.model_json_schema()

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        _ = ctx
        params = CreateFileParams.model_validate(kwargs)

        # 路径校验（复用 WriteFile 的路径解析，支持 /workspace/ 和 /global/ 前缀）
        raw_path = params.path.strip().replace("\\", "/")
        if not raw_path:
            return ToolResult(content="文件路径不能为空", is_error=True)

        try:
            file_path = _resolve_file_path(raw_path)
        except ValueError as exc:
            return ToolResult(content=str(exc), is_error=True)

        # 获取用于显示的规范化路径
        is_global = raw_path.startswith("/global/")
        if is_global:
            normalized_path = raw_path[len("/global/") :]
        elif raw_path.startswith("/workspace/"):
            normalized_path = raw_path[len("/workspace/") :]
        else:
            normalized_path = raw_path
        normalized = Path(normalized_path)

        if file_path.exists() and not params.overwrite:
            return ToolResult(
                content=f"文件已存在: {normalized.as_posix()}。使用 overwrite=true 覆盖。",
                is_error=True,
            )

        # 确定文件类型
        registry = get_file_initializer_registry()
        file_type = params.file_type
        if file_type:
            try:
                initializer = registry.get(file_type)
            except KeyError:
                available = [i.file_type for i in registry.list_all()]
                return ToolResult(
                    content=f"未知文件类型: {file_type}。可用类型: {', '.join(available)}",
                    is_error=True,
                )
        else:
            initializer = registry.guess_from_path(normalized.as_posix())
            if initializer is None:
                initializer = registry.get("text")

        # 合并参数
        init_params: dict[str, Any] = dict(params.params)
        if params.content:
            init_params["content"] = params.content
        if file_type in ("knowledge_base", "knowledge_graph") and "name" not in init_params:
            name = normalized.stem
            if name.endswith(".kb") or name.endswith(".graph"):
                name = name.rsplit(".", 1)[0]
            init_params["name"] = name

        # 注入 user_id，供 KnowledgeBaseInitializer 使用
        init_params["user_id"] = ctx.get("user_id") if ctx else "system"

        # 校验参数
        try:
            initializer.validate_params(init_params)
        except ValueError as exc:
            return ToolResult(content=str(exc), is_error=True)

        # 创建父目录
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            return ToolResult(content=f"创建父目录失败: {exc}", is_error=True)

        # 记录文件历史
        try:
            file_history_root = file_path.parent.parent if is_global else file_path.parent
            file_history_service.record_file_before_change(
                file_history_root,
                normalized.as_posix(),
                operation="before_overwrite",
                source="agent_tool",
                source_detail="CreateFile",
            )
        except Exception:
            pass  # 历史记录失败不阻塞创建

        # 执行初始化
        try:
            result = initializer.initialize(file_path, init_params)
        except Exception as exc:
            logger.error("CreateFile 初始化失败: %s", exc, exc_info=True)
            return ToolResult(content=f"文件创建失败: {exc}", is_error=True)

        display_prefix = "/global" if is_global else "/workspace"
        display_path = f"{display_prefix}/{normalized.as_posix()}"
        return ToolResult(
            content="\n".join(
                [
                    f"文件创建成功: {display_path}",
                    f"类型: {initializer.display_name}",
                    f"大小: {result.size} 字节",
                ]
            ),
        )
