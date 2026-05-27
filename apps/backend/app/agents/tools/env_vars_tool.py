"""环境变量管理工具。

提供环境变量的读取、设置和删除能力。
设置/删除操作作用于工作区级别（workspace registry 的 runtime_binding.env_vars），
不会修改全局环境变量。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agents.tools.local_ipython_box import build_sanitized_kernel_env
from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.global_env_vars import resolve_merged_env_vars
from app.services.history import (
    current_runtime_env_vars,
    current_session_id,
    current_user_id,
    current_workspace,
)
from app.services.workspace_registry import get_workspace_registry_service

SENSITIVE_KEY_PATTERNS = (
    "KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASS",
    "AUTH",
    "CREDENTIAL",
    "PRIVATE",
)


def _is_sensitive_key(name: str) -> bool:
    upper = name.upper()
    return any(pattern in upper for pattern in SENSITIVE_KEY_PATTERNS)


def _resolve_workspace_scope(
    ctx: dict[str, Any] | None,
) -> tuple[str, str] | str:
    registry = get_workspace_registry_service()
    context = ctx or {}
    user_id = str(context.get("user_id") or current_user_id.get() or "").strip()
    if not user_id:
        return "当前工具上下文缺少 user_id，无法管理工作区环境变量。"

    explicit_workspace_id = str(context.get("workspace_id") or "").strip()
    if explicit_workspace_id:
        registry.get_workspace(
            user_id,
            explicit_workspace_id,
            include_conversations=False,
        )
        return user_id, explicit_workspace_id

    session_id = str(context.get("session_id") or current_session_id.get() or "").strip()
    if session_id:
        workspace_id = registry.find_workspace_id_by_session_id(user_id, session_id)
        if workspace_id:
            return user_id, workspace_id

    workspace_path = context.get("workspace") or current_workspace.get()
    if workspace_path is not None:
        candidate = Path(str(workspace_path)).name
        if candidate:
            try:
                registry.get_workspace(
                    user_id,
                    candidate,
                    include_conversations=False,
                )
                return user_id, candidate
            except FileNotFoundError:
                pass

    return "当前会话没有绑定可解析的工作区，无法管理工作区环境变量。"


class ListEnvVarsParams(BaseModel):
    """ListEnvVars 参数。"""

    pass


class ListEnvVars(AiasysTool):
    """列出当前会话运行态可用的环境变量名。"""

    name: str = "ListEnvVars"
    description: str = """列出当前会话运行态可用的环境变量名。

返回内容：
- count: 变量名数量
- env_vars: 按字母序排列的环境变量名列表

限制：
- 只返回变量名，不返回变量值
- 包含当前会话注入的自定义环境变量名
- 不适合用来读取密钥值；读取具体变量值请由代码运行环境自行按需访问
"""
    params: type[BaseModel] = ListEnvVarsParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = ListEnvVarsParams.model_validate(kwargs)
        del ctx, params

        custom_env_vars = current_runtime_env_vars.get()
        effective_env = build_sanitized_kernel_env(custom_env_vars=custom_env_vars)
        env_vars = sorted(effective_env.keys())

        return ToolResult(
            content=json.dumps(
                {
                    "status": "success",
                    "count": len(env_vars),
                    "env_vars": env_vars,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


# ---------------------------------------------------------------------------
# GetEnvVar
# ---------------------------------------------------------------------------


class GetEnvVarParams(BaseModel):
    """GetEnvVar 参数。"""

    name: str = Field(description="要读取的环境变量名")


class GetEnvVar(AiasysTool):
    """读取当前会话运行态中某个环境变量的值。"""

    name: str = "GetEnvVar"
    description: str = """读取当前会话运行态中某个环境变量的值。

返回指定环境变量的当前值。如果变量名匹配敏感 key 模式（含 KEY/SECRET/TOKEN 等），
值会被脱敏显示（仅显示前4位和后4位）。
"""
    params: type[BaseModel] = GetEnvVarParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = GetEnvVarParams.model_validate(kwargs)
        del ctx

        custom_env_vars = current_runtime_env_vars.get()
        effective_env = build_sanitized_kernel_env(custom_env_vars=custom_env_vars)

        if params.name not in effective_env:
            return ToolResult(
                content=json.dumps(
                    {
                        "status": "not_found",
                        "name": params.name,
                        "message": f"环境变量 '{params.name}' 不存在",
                    },
                    ensure_ascii=False,
                ),
                is_error=True,
            )

        raw_value = effective_env[params.name]
        display_value = _mask_sensitive(raw_value) if _is_sensitive_key(params.name) else raw_value

        return ToolResult(
            content=json.dumps(
                {
                    "status": "success",
                    "name": params.name,
                    "value": display_value,
                    "masked": _is_sensitive_key(params.name),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


def _mask_sensitive(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


# ---------------------------------------------------------------------------
# SetEnvVar
# ---------------------------------------------------------------------------


class SetEnvVarParams(BaseModel):
    """SetEnvVar 参数。"""

    name: str = Field(description="要设置的环境变量名")
    value: str = Field(description="要设置的环境变量值")


class SetEnvVar(AiasysTool):
    """设置工作区级别的环境变量。"""

    name: str = "SetEnvVar"
    description: str = """设置工作区级别的环境变量。变量写入当前工作区 runtime_binding.env_vars。

设置后，当前会话的下一次工具调用会使用新值。
注意：只作用于当前工作区，不影响其他工作区或全局环境变量。
"""
    params: type[BaseModel] = SetEnvVarParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = SetEnvVarParams.model_validate(kwargs)

        scope = _resolve_workspace_scope(ctx)
        if isinstance(scope, str):
            return ToolResult(content=scope, is_error=True)
        user_id, workspace_id = scope

        registry = get_workspace_registry_service()
        registry.set_workspace_env_var(
            user_id,
            workspace_id,
            params.name,
            params.value,
        )

        workspace_env_vars = registry.get_workspace_env_vars(user_id, workspace_id)
        current_runtime_env_vars.set(resolve_merged_env_vars(user_id, workspace_env_vars))

        return ToolResult(
            content=json.dumps(
                {
                    "status": "success",
                    "name": params.name,
                    "workspace_id": workspace_id,
                    "message": f"环境变量 '{params.name}' 已设置",
                },
                ensure_ascii=False,
                indent=2,
            )
        )


# ---------------------------------------------------------------------------
# DeleteEnvVar
# ---------------------------------------------------------------------------


class DeleteEnvVarParams(BaseModel):
    """DeleteEnvVar 参数。"""

    name: str = Field(description="要删除的环境变量名")


class DeleteEnvVar(AiasysTool):
    """删除工作区级别的环境变量。"""

    name: str = "DeleteEnvVar"
    description: str = """删除工作区级别的环境变量（从当前工作区 runtime_binding.env_vars 中移除）。

注意：只能删除工作区级别的环境变量，无法删除全局环境变量或系统环境变量。
"""
    params: type[BaseModel] = DeleteEnvVarParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = DeleteEnvVarParams.model_validate(kwargs)

        scope = _resolve_workspace_scope(ctx)
        if isinstance(scope, str):
            return ToolResult(content=scope, is_error=True)
        user_id, workspace_id = scope

        registry = get_workspace_registry_service()
        deleted = registry.delete_workspace_env_var(
            user_id,
            workspace_id,
            params.name,
        )
        if not deleted:
            return ToolResult(
                content=json.dumps(
                    {
                        "status": "not_found",
                        "name": params.name,
                        "message": f"工作区环境变量 '{params.name}' 不存在",
                    },
                    ensure_ascii=False,
                ),
                is_error=True,
            )

        workspace_env_vars = registry.get_workspace_env_vars(user_id, workspace_id)
        current_runtime_env_vars.set(resolve_merged_env_vars(user_id, workspace_env_vars))

        return ToolResult(
            content=json.dumps(
                {
                    "status": "success",
                    "name": params.name,
                    "workspace_id": workspace_id,
                    "message": f"环境变量 '{params.name}' 已删除",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
