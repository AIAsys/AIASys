"""
AIASys 原生子 Agent 动态创建工具 (CreateSubagentTool)。

支持两种作用域：
- workspace（默认）：工作区内跨会话复用
- global：跨工作区复用，需要运行上下文授权
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.agent.subagent_catalog import (
    is_system_subagent_name,
    is_valid_subagent_name,
    normalize_subagent_tool_paths,
    save_subagent,
)
from app.services.runtime_tooling import is_subagent_orchestration_tool_name

logger = logging.getLogger(__name__)

_CREATE_PARAMETERS = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "子 Agent 标识名（英文，唯一，如 custom_coder、data_cleaner）",
        },
        "description": {
            "type": "string",
            "description": "一句话描述，用于 UI 展示和 Task 工具选择",
        },
        "system_prompt": {
            "type": "string",
            "description": "子 Agent 的系统提示词（完整的角色定义和指令）",
        },
        "tools": {
            "type": "array",
            "items": {"type": "string"},
            "description": "可用工具路径列表（可选，默认继承 Host 工具集）",
        },
        "model": {
            "type": "string",
            "description": "模型 ID（可选，默认继承 Host 配置）",
        },
        "scope": {
            "type": "string",
            "description": "作用域。'global'=我的默认，跨工作区继承；'workspace'=当前工作区配置，跨会话复用",
            "enum": ["global", "workspace"],
            "default": "workspace",
        },
    },
    "required": ["name", "description", "system_prompt"],
}


class CreateSubagentTool(AiasysTool):
    """动态创建子 Agent 配置。

    LLM 调用此工具后，新创建的子 Agent 立即可通过 Task/Agent 工具调用。
    """

    name = "CreateSubagent"
    description = (
        "动态创建一个新的自定义子 Agent（角色）配置。"
        "系统预设角色（data_analyst、coder、researcher、reviewer、worker）可直接通过 Task 工具调用，无需创建。"
        "默认创建到当前工作区（scope='workspace'），立即可用。"
        "写入我的默认需要当前运行上下文显式授权。"
        "参数: name(标识名), description(描述), system_prompt(系统提示词), "
        "tools(工具列表,可选), model(模型,可选), scope(作用域,默认workspace)"
    )
    parameters = _CREATE_PARAMETERS

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        ctx = ctx or {}
        name = str(kwargs.get("name") or "").strip()
        description = str(kwargs.get("description") or "").strip()
        system_prompt = str(kwargs.get("system_prompt") or "").strip()
        tools = kwargs.get("tools")
        model = str(kwargs.get("model") or "").strip() or None
        scope = str(kwargs.get("scope") or "workspace").strip().lower()
        if scope not in ("global", "workspace"):
            return ToolResult(
                content=f"不支持的 scope '{scope}'，仅支持 'global'/'workspace'", is_error=True
            )
        allowed_scopes = ctx.get("allowed_create_subagent_scopes")
        if not isinstance(allowed_scopes, list):
            allowed_scope_set = {"workspace"}
        else:
            allowed_scope_set = {
                str(item or "").strip().lower()
                for item in allowed_scopes
                if str(item or "").strip()
            } or {"workspace"}
        if scope not in allowed_scope_set:
            return ToolResult(
                content=f"当前会话未授权创建 {scope} 作用域的子 Agent。",
                is_error=True,
            )

        # 校验必填
        if not name:
            return ToolResult(content="缺少 name 参数", is_error=True)
        if not description:
            return ToolResult(content="缺少 description 参数", is_error=True)
        if not system_prompt:
            return ToolResult(content="缺少 system_prompt 参数", is_error=True)

        # 校验 name 格式
        if not is_valid_subagent_name(name):
            return ToolResult(
                content=f"子 Agent 名称 '{name}' 格式无效。要求：英文字母开头，仅包含字母、数字、下划线、连字符，长度不超过64。",
                is_error=True,
            )

        # 校验不与系统预设冲突
        if is_system_subagent_name(name):
            return ToolResult(
                content=f"子 Agent 名称 '{name}' 与系统预设角色冲突，请使用其他名称。",
                is_error=True,
            )

        user_id = str(ctx.get("user_id") or "")
        session_id = str(ctx.get("session_id") or "")
        host_agent_config = ctx.get("agent_config") or {}

        if not user_id or not session_id:
            return ToolResult(content="无法确定当前会话上下文", is_error=True)

        # 构建 manifest
        manifest: dict[str, Any] = {
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
        }
        if model:
            manifest["model"] = model
        if isinstance(tools, list) and tools:
            blocked_tools = [
                str(tool or "").strip()
                for tool in tools
                if is_subagent_orchestration_tool_name(str(tool or "").strip())
            ]
            if blocked_tools:
                return ToolResult(
                    content=(
                        "子 Agent 工具集中不能包含协作节点调度或创建工具："
                        + ", ".join(blocked_tools)
                    ),
                    is_error=True,
                )
            normalized_tools, invalid_tools = normalize_subagent_tool_paths(tools)
            if invalid_tools:
                return ToolResult(
                    content=(
                        "以下工具在当前运行时不可用，无法创建子 Agent：" + ", ".join(invalid_tools)
                    ),
                    is_error=True,
                )
            if normalized_tools:
                manifest["tools"] = normalized_tools

        # 获取 workspace_id（单工作区兼容：默认等于 user_id）
        workspace_id = user_id
        try:
            from app.services.workspace_registry import get_workspace_registry_service

            workspace_registry = get_workspace_registry_service()
            resolved = workspace_registry.find_workspace_id_by_session_id(user_id, session_id)
            if resolved:
                workspace_id = resolved
        except Exception:
            pass

        # 保存
        try:
            save_subagent(
                user_id=user_id,
                name=name,
                manifest=dict(manifest),
                scope=scope,
                session_id=session_id,
                workspace_id=workspace_id,
            )
        except Exception as exc:
            logger.exception("保存子 Agent 配置失败: name=%s", name)
            return ToolResult(
                content=f"保存子 Agent 配置失败: {exc}",
                is_error=True,
            )

        # 实时注入当前 Host 的 agent_config，使后续 Task 立即可调用
        subagents = host_agent_config.setdefault("subagents", {})
        if isinstance(subagents, dict):
            subagents[name] = {
                "description": description,
                "agent_manifest": manifest,
            }
            logger.info(
                "子 Agent 已实时注入 Host manifest: name=%s session=%s",
                name,
                session_id,
            )

        scope_label = {
            "global": "全局级（跨所有工作区共享）",
            "workspace": "工作区级（跨会话复用）",
        }.get(scope, scope)
        return ToolResult(
            content=(
                f"子 Agent '{name}' 创建成功（{scope_label}）。\n"
                f"描述: {description}\n"
                f"可用工具: {', '.join(manifest.get('tools', [])) or '继承 Host 工具集'}\n"
                f"现在可以通过 Task 或 Agent 工具调用此子 Agent。"
            ),
        )
