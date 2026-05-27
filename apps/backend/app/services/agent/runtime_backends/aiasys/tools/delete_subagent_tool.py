"""
AIASys 子 Agent 删除工具 (DeleteSubagentTool)。

支持删除全局、工作区级专家。
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.agent.subagent_catalog import (
    delete_subagent,
)

logger = logging.getLogger(__name__)

_DELETE_PARAMETERS = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "要删除的子 Agent 标识名",
        },
        "scope": {
            "type": "string",
            "description": "作用域。'global'/'workspace'",
            "enum": ["global", "workspace"],
            "default": "workspace",
        },
    },
    "required": ["name"],
}


class DeleteSubagentTool(AiasysTool):
    """删除子 Agent（专家）。"""

    name = "DeleteSubagent"
    description = "删除子 Agent（专家）。" "支持删除全局、工作区级专家。" "参数: name(必填), scope"
    parameters = _DELETE_PARAMETERS

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        ctx = ctx or {}
        user_id = str(ctx.get("user_id") or "")
        session_id = str(ctx.get("session_id") or "")
        name = str(kwargs.get("name") or "").strip()
        scope = str(kwargs.get("scope") or "workspace").strip().lower()

        if not user_id or not session_id:
            return ToolResult(content="无法确定当前会话上下文", is_error=True)
        if not name:
            return ToolResult(content="缺少 name 参数", is_error=True)
        if scope not in ("global", "workspace"):
            return ToolResult(
                content=f"不支持的 scope '{scope}'，仅支持 global/workspace",
                is_error=True,
            )

        # 解析 workspace_id
        workspace_id = user_id
        try:
            from app.services.workspace_registry import get_workspace_registry_service

            registry = get_workspace_registry_service()
            resolved = registry.find_workspace_id_by_session_id(user_id, session_id)
            if resolved:
                workspace_id = resolved
        except Exception:
            pass

        # workspace 或 global：直接删除
        deleted = delete_subagent(
            user_id=user_id,
            name=name,
            scope=scope,
            workspace_id=workspace_id,
        )

        if deleted:
            return ToolResult(content=f"专家 '{name}' 已删除（{scope}）。")
        return ToolResult(content=f"专家 '{name}' 不存在或已删除（{scope}）。")
