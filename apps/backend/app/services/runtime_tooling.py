"""
运行时工具可用性探测与工具名规范化。

这层故意不放在 ``app.services.agent`` 包下面，避免仅为了工具探测或
canonicalization 就触发整个 agent runtime/service import 链。
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

# AIASys 原生 TaskTool / AgentTool 路径
NATIVE_TASK_TOOL_PATH = "app.services.agent.runtime_backends.aiasys.tools.task_tool:TaskTool"
NATIVE_AGENT_TOOL_PATH = "app.services.agent.runtime_backends.aiasys.tools.task_tool:AgentTool"
NATIVE_CREATE_SUBAGENT_TOOL_PATH = (
    "app.services.agent.runtime_backends.aiasys.tools.create_subagent_tool:CreateSubagentTool"
)
READ_MEDIA_TOOL_PATH = "app.agents.tools.read_media_tool:ReadMediaFile"

_RUNTIME_TOOL_ALIASES: dict[str, str] = {
    # AgentTool 与 TaskTool 是同一实现的不同名称，统一映射到 TaskTool
    NATIVE_AGENT_TOOL_PATH: NATIVE_TASK_TOOL_PATH,
}
_SUBAGENT_DISPATCH_TOOL_EVENT_NAMES = {"Task", "Agent"}
_SUBAGENT_DISPATCH_TOOL_PATHS = {
    NATIVE_TASK_TOOL_PATH,
    NATIVE_AGENT_TOOL_PATH,
}
_SUBAGENT_ORCHESTRATION_TOOL_EVENT_NAMES = {
    *_SUBAGENT_DISPATCH_TOOL_EVENT_NAMES,
    "CreateSubagent",
}
_SUBAGENT_ORCHESTRATION_TOOL_PATHS = {
    *_SUBAGENT_DISPATCH_TOOL_PATHS,
    NATIVE_CREATE_SUBAGENT_TOOL_PATH,
}


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeToolAvailability:
    """单个工具在当前运行时中的可用性探测结果。"""

    tool_name: str
    available: bool
    reason: str
    module_name: str | None = None
    class_name: str | None = None
    detail: str | None = None


def canonicalize_runtime_tool_name(tool_name: str) -> str:
    """把等价工具名映射到当前 runtime 实际支持的 canonical 名称。"""
    normalized = tool_name.strip()
    return _RUNTIME_TOOL_ALIASES.get(normalized, normalized)


def project_runtime_tool_event_name(tool_name: str | None) -> str | None:
    """把当前 runtime 的原始工具名投影回 AIASys 稳定事件语义。"""
    if tool_name == "Agent":
        return "Task"
    return tool_name


def is_subagent_dispatch_tool_name(tool_name: str | None) -> bool:
    """判断一个工具名是否表示子代理/子任务委派能力。"""
    if not tool_name:
        return False
    if tool_name in _SUBAGENT_DISPATCH_TOOL_EVENT_NAMES:
        return True
    canonical = canonicalize_runtime_tool_name(tool_name)
    if canonical in _SUBAGENT_DISPATCH_TOOL_PATHS:
        return True
    return False


def is_subagent_orchestration_tool_name(tool_name: str | None) -> bool:
    """判断一个工具名是否表示协作节点调度或创建能力。"""
    if not tool_name:
        return False
    if tool_name in _SUBAGENT_ORCHESTRATION_TOOL_EVENT_NAMES:
        return True
    canonical = canonicalize_runtime_tool_name(tool_name)
    if canonical in _SUBAGENT_ORCHESTRATION_TOOL_PATHS:
        return True
    return False


def extract_subagent_display_name(
    tool_name: str | None,
    arguments: dict[str, Any],
) -> str | None:
    """从委派工具参数里提取适合作为 UI 标签的子任务名称。

    同时支持 Task/Agent（调用子 Agent）和 CreateSubagent（创建子 Agent）。
    """
    if not is_subagent_dispatch_tool_name(tool_name) and tool_name != "CreateSubagent":
        return None

    for key in ("subagent_name", "description", "resume", "subagent_type", "name"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def probe_runtime_tool(tool_name: str) -> RuntimeToolAvailability:
    """探测工具标识在当前 Python 运行时中是否真的可导入。"""
    requested_tool_name = tool_name.strip()
    canonical_tool_name = canonicalize_runtime_tool_name(requested_tool_name)

    if ":" not in canonical_tool_name:
        return RuntimeToolAvailability(
            tool_name=requested_tool_name,
            available=False,
            reason="invalid_tool_format",
            detail="工具标识必须为 module:Symbol 格式。",
        )

    module_name, class_name = canonical_tool_name.rsplit(":", 1)
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        return RuntimeToolAvailability(
            tool_name=requested_tool_name,
            available=False,
            reason="module_import_error",
            module_name=module_name,
            class_name=class_name,
            detail=str(exc),
        )

    if getattr(module, class_name, None) is None:
        return RuntimeToolAvailability(
            tool_name=requested_tool_name,
            available=False,
            reason="symbol_missing",
            module_name=module_name,
            class_name=class_name,
            detail=f"{module_name} 中未导出 {class_name}",
        )

    return RuntimeToolAvailability(
        tool_name=requested_tool_name,
        available=True,
        reason="available",
        module_name=module_name,
        class_name=class_name,
        detail=(
            f"canonicalized_to={canonical_tool_name}"
            if canonical_tool_name != requested_tool_name
            else None
        ),
    )


__all__ = [
    "NATIVE_AGENT_TOOL_PATH",
    "NATIVE_CREATE_SUBAGENT_TOOL_PATH",
    "NATIVE_TASK_TOOL_PATH",
    "READ_MEDIA_TOOL_PATH",
    "RuntimeToolAvailability",
    "canonicalize_runtime_tool_name",
    "project_runtime_tool_event_name",
    "is_subagent_dispatch_tool_name",
    "is_subagent_orchestration_tool_name",
    "extract_subagent_display_name",
    "probe_runtime_tool",
]
