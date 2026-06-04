"""
AIASys 子 Agent 更新工具 (UpdateSubagentTool)。

支持更新全局基线、工作区级专家配置。
更新全局基线专家时，会在当前工作区创建同名覆盖版本。
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.agent.subagent_catalog import (
    load_subagent,
    normalize_subagent_tool_paths,
    save_subagent,
)

logger = logging.getLogger(__name__)

_UPDATE_PARAMETERS = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "要更新的子 Agent 标识名",
        },
        "scope": {
            "type": "string",
            "description": "作用域。'global'/'workspace'。更新 global 基线时会创建 workspace 级覆盖",
            "enum": ["global", "workspace"],
            "default": "workspace",
        },
        "description": {
            "type": "string",
            "description": "新的描述（可选，不填则保持原值）",
        },
        "system_prompt": {
            "type": "string",
            "description": "新的系统提示词（可选，不填则保持原值）",
        },
        "tools": {
            "type": "array",
            "items": {"type": "string"},
            "description": "新的可用工具路径列表（可选，不填则保持原值）",
        },
        "model": {
            "type": "string",
            "description": "新的模型 ID（可选，不填则保持原值）",
        },
    },
    "required": ["name"],
}


def _get_global_subagent_manifest(name: str) -> dict[str, Any] | None:
    """从系统预设 baseline 中获取 global 专家的完整配置。"""
    from app.services.agent.system_presets import _LOCAL_BASELINES

    for baseline in _LOCAL_BASELINES.values():
        if name not in baseline.subagents:
            continue
        binding = baseline.subagents[name]
        sub_baseline = _LOCAL_BASELINES.get(binding.baseline_id)
        if sub_baseline is None:
            continue

        manifest: dict[str, Any] = {
            "name": name,
            "description": binding.description,
        }
        try:
            prompt_text = sub_baseline.prompt_template_path.read_text(encoding="utf-8")
            manifest["system_prompt"] = prompt_text
        except Exception:
            manifest["system_prompt"] = ""
        if sub_baseline.model:
            manifest["model"] = sub_baseline.model
        if sub_baseline.tools:
            manifest["tools"] = list(sub_baseline.tools)
        return manifest

    return None


class UpdateSubagentTool(AiasysTool):
    """更新子 Agent（专家）配置。"""

    name = "UpdateSubagent"
    description = (
        "更新现有子 Agent（专家）的配置。"
        "支持更新全局基线、工作区级专家。"
        "更新全局基线专家时，会在工作区级创建同名覆盖版本。"
        "参数: name(必填), scope, description, system_prompt, tools, model"
    )
    parameters = _UPDATE_PARAMETERS

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

        # 加载现有配置
        existing = load_subagent(user_id, name, workspace_id=workspace_id)

        if existing is None and scope == "global":
            existing = _get_global_subagent_manifest(name)

        if existing is None:
            return ToolResult(
                content=f"专家 '{name}' 不存在",
                is_error=True,
            )

        # 构建新 manifest（只更新提供的字段）
        manifest = dict(existing)
        if "description" in kwargs:
            manifest["description"] = str(kwargs["description"] or "")
        if "system_prompt" in kwargs:
            manifest["system_prompt"] = str(kwargs["system_prompt"] or "")
        if "tools" in kwargs:
            tools = kwargs["tools"]
            if isinstance(tools, list):
                normalized_tools, invalid_tools = normalize_subagent_tool_paths(tools)
                if invalid_tools:
                    return ToolResult(
                        content=(
                            "以下工具在当前运行时不可用，无法更新专家配置："
                            + ", ".join(invalid_tools)
                        ),
                        is_error=True,
                    )
                if normalized_tools:
                    manifest["tools"] = normalized_tools
                else:
                    manifest.pop("tools", None)
            else:
                manifest.pop("tools", None)
        if "model" in kwargs:
            model_val = str(kwargs["model"] or "").strip()
            if model_val:
                manifest["model"] = model_val
            else:
                manifest.pop("model", None)

        try:
            target_scope = "workspace" if scope == "global" else scope
            save_kwargs: dict[str, Any] = {
                "user_id": user_id,
                "name": name,
                "manifest": dict(manifest),
                "scope": target_scope,
            }
            if target_scope == "workspace":
                save_kwargs["workspace_id"] = workspace_id
            save_subagent(**save_kwargs)
        except Exception as exc:
            logger.exception("更新子 Agent 配置失败: name=%s", name)
            return ToolResult(
                content=f"更新子 Agent 配置失败: {exc}",
                is_error=True,
            )

        scope_label = {
            "global": "全局基线（已创建工作区覆盖）",
            "workspace": "工作区",
        }.get(scope, scope)
        return ToolResult(content=f"专家 '{name}' 已更新（{scope_label}）。")
