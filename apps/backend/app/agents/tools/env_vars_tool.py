"""环境变量管理工具。

提供工作区级别环境变量的完整管理能力：列出、读取、设置、删除。
所有操作作用于 workspace registry 的 runtime_binding.env_vars，
跨会话持久化，不会修改系统环境变量。
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
            # 路径存在但不是注册 workspace（例如 session 目录），自动创建 workspace
            p = Path(str(workspace_path))
            if p.exists() and p.is_dir():
                try:
                    registry.create_workspace(
                        user_id=user_id,
                        title=candidate,
                        workspace_id=candidate,
                    )
                except ValueError as exc:
                    if "工作区已存在" in str(exc):
                        pass  # 已存在，继续
                    else:
                        raise
                return user_id, candidate

    return "当前会话没有绑定可解析的工作区，无法管理工作区环境变量。"


# ---------------------------------------------------------------------------
# ListEnvVars
# ---------------------------------------------------------------------------


class ListEnvVarsParams(BaseModel):
    """ListEnvVars 参数。"""

    pass


class ListEnvVars(AiasysTool):
    """列出当前工作区可用的环境变量名。"""

    name: str = "ListEnvVars"
    risk_level: str = "readonly"
    effect_scope: str = "session"
    side_effect: bool = False
    description: str = """列出当前工作区已配置的环境变量名。

适用场景：
- 用户问"工作区设置了哪些环境变量"时
- 需要查看当前工作区配置了哪些变量名（不包含值）

返回内容：
- count: 变量名数量
- env_vars: 按字母序排列的环境变量名列表

为什么用 ListEnvVars 而不是 Shell `env`：
- 只返回工作区级别的变量，不会混入系统环境变量，结果精准
- 返回结构化 JSON，方便后续处理
- Shell `env` 会列出上百个系统变量，需要额外过滤和解析

限制：
- 只返回变量名，不返回变量值
- 读取具体变量值请用 GetEnvVar
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

        hint = ""
        if env_vars:
            hint = (
                "用户已要求删除/移除环境变量时，请立即调用 DeleteEnvVar(name='<变量名>')。\n"
                "如果只是查看列表，已获得结果，请直接整理回复用户，不要再调用其他工具。\n\n"
            )
        else:
            hint = "当前工作区没有环境变量。\n\n"
        return ToolResult(
            content=hint + json.dumps(
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
    """读取当前工作区中某个环境变量的值。"""

    name: str = "GetEnvVar"
    risk_level: str = "readonly"
    effect_scope: str = "session"
    side_effect: bool = False
    description: str = """读取当前工作区中某个环境变量的值。

适用场景：
- 查询某个环境变量的当前值
- 验证环境变量是否已正确设置

为什么用 GetEnvVar 而不是 Shell `echo $VAR`：
- 返回结构化 JSON，包含变量名、值、是否脱敏等完整信息
- 自动检测敏感变量名（含 KEY/SECRET/TOKEN 等）并脱敏显示，降低泄露风险
- 读取的是工作区持久化环境变量，不只是当前 Shell 进程的临时值

返回指定环境变量的当前值。如果变量名匹配敏感 key 模式，值会被脱敏显示（仅显示前4位和后4位）。
"""
    params: type[BaseModel] = GetEnvVarParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        if "key" in kwargs and "name" not in kwargs:
            kwargs["name"] = kwargs.pop("key")
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
    risk_level: str = "high"
    effect_scope: str = "workspace"
    side_effect: bool = True
    description: str = """设置/修改当前工作区的环境变量。变量写入当前工作区 runtime_binding.env_vars。

适用场景：
- 为当前工作区设置新的环境变量
- 修改已有环境变量的值
- 配置 API Key、数据库连接串等任务专属配置

为什么用 SetEnvVar 而不是 Shell `export`：
- **持久化**：设置后写入工作区，跨会话可用。Shell export 只在当前进程生效，Shell 关闭后丢失
- **隔离性**：只作用于当前工作区，不影响其他工作区或全局环境变量
- **安全性**：设置后自动同步到当前会话运行环境，下一次工具调用和代码执行都会使用新值

设置后，当前会话的下一次工具调用和代码执行会使用新值。
注意：只作用于当前工作区，不影响其他工作区或全局环境变量。
"""
    params: type[BaseModel] = SetEnvVarParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        # Agent 有时会传 key 而不是 name，做容错映射
        if "key" in kwargs and "name" not in kwargs:
            kwargs["name"] = kwargs.pop("key")
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
    risk_level: str = "high"
    effect_scope: str = "workspace"
    side_effect: bool = True
    description: str = """删除/移除当前工作区的环境变量（从工作区注册表中永久删除）。

适用场景：
- 用户说"删除环境变量""移除变量""这个变量不用了"时
- ListEnvVars 确认目标变量后，必须立即调用本工具完成删除

正确做法 vs 错误做法：
- 正确：用户说"删掉 API_KEY" → 调用 DeleteEnvVar(name="API_KEY")
- 错误：用户说"删掉 API_KEY" → 只调用 ListEnvVars 查看，或尝试 Shell `unset`

为什么用 DeleteEnvVar 而不是 Shell `unset`：
- **永久删除**：从工作区注册表中永久删除，跨会话生效
- Shell `unset` / `export VAR=` 只在当前 Shell 进程生效，关闭 Shell 后变量仍然存在

注意：只能删除工作区级别的环境变量，无法删除全局环境变量或系统环境变量。
"""
    params: type[BaseModel] = DeleteEnvVarParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        if "key" in kwargs and "name" not in kwargs:
            kwargs["name"] = kwargs.pop("key")
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
