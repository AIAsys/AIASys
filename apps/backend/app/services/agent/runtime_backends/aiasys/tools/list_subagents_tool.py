"""
AIASys 子 Agent 目录查询工具 (ListSubagentsTool)。

列出当前可派发的协作专家（我的默认 + 当前工作区）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.agent.subagent_catalog import (
    is_subagent_dispatch_enabled,
    list_subagents,
)

logger = logging.getLogger(__name__)

_LIST_PARAMETERS = {
    "type": "object",
    "properties": {
        "scope": {
            "type": "string",
            "description": "过滤作用域。'all'=全部启用专家；'global'=仅全局；'workspace'=仅工作区",
            "enum": ["all", "global", "workspace"],
            "default": "all",
        },
        "keyword": {
            "type": "string",
            "description": "搜索关键词。匹配角色名称和描述，不区分大小写。留空则列出全部。",
            "default": "",
        },
    },
}


class ListSubagentsTool(AiasysTool):
    """查询当前可派发的协作专家目录。"""

    name = "ListSubagents"
    description = "列出当前可派发的协作专家目录。" "参数: scope(过滤作用域, 可选)"
    parameters = _LIST_PARAMETERS

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        ctx = ctx or {}
        user_id = str(ctx.get("user_id") or "")
        session_id = str(ctx.get("session_id") or "")

        if not user_id or not session_id:
            return ToolResult(content="无法确定当前会话上下文", is_error=True)

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

        # 加载所有专家
        catalog = list_subagents(user_id, workspace_id=workspace_id)

        # 组装结果
        results: list[dict[str, Any]] = []
        for category in ("global", "workspace"):
            for item in catalog.get(category, []):
                name = item.get("name", "")
                dispatch_enabled = is_subagent_dispatch_enabled(
                    user_id=user_id,
                    role_id=str(name),
                    workspace_id=workspace_id,
                )
                if not dispatch_enabled:
                    continue
                results.append(
                    {
                        "name": name,
                        "scope": category,
                        "description": item.get("description", ""),
                        "model": item.get("model"),
                        "status": item.get("status", "active"),
                        "source": item.get("source", "custom"),
                    }
                )

        # 按 scope 过滤
        target_scope = str(kwargs.get("scope") or "all").strip().lower()
        if target_scope != "all":
            if target_scope not in {"global", "workspace"}:
                return ToolResult(
                    content=f"不支持的 scope '{target_scope}'，仅支持 all/global/workspace",
                    is_error=True,
                )
            results = [r for r in results if r["scope"] == target_scope]

        # 按关键词搜索（匹配名称和描述，不区分大小写）
        keyword = str(kwargs.get("keyword") or "").strip().lower()
        if keyword:
            results = [
                r
                for r in results
                if keyword in r["name"].lower() or keyword in (r.get("description") or "").lower()
            ]

        if not results:
            if keyword:
                return ToolResult(content=f"未找到匹配 '{keyword}' 的专家。")
            return ToolResult(content="当前没有可派发的协作专家。")

        # 格式化为可读文本
        lines: list[str] = []
        lines.append(f"共 {len(results)} 个可派发的协作专家：\n")
        for item in results:
            scope_tag = {"global": "[我的默认]", "workspace": "[当前工作区]"}.get(
                item["scope"], "[未知]"
            )
            lines.append(f"- {item['name']} {scope_tag}")
            if item.get("description"):
                lines.append(f"  描述: {item['description']}")
            if item.get("model"):
                lines.append(f"  模型: {item['model']}")
            lines.append("")

        return ToolResult(content="\n".join(lines))
