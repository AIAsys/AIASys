from __future__ import annotations

import logging
import re
from collections.abc import AsyncGenerator
from copy import deepcopy
from typing import Any

logger = logging.getLogger(__name__)

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.agent.runtime_backends.base import AgentRuntimeEvent, ToolStreamEvent

_FIRST_CAP_RE = re.compile(r"(.)([A-Z][a-z]+)")
_ALL_CAP_RE = re.compile(r"([a-z0-9])([A-Z])")

# 始终可用的核心工具（不被 defer）。按 short name 匹配。
NON_DEFERRED_TOOL_NAMES: set[str] = {
    # 文件操作
    "ReadFile",
    "WriteFile",
    "StrReplaceFile",
    # Shell
    "Shell",
    # 任务调度
    "TaskTool",
    "AgentTool",
    "CreateSubagentTool",
    # 会话内任务与规划
    "task_create",
    "task_update",
    "task_list",
    "enter_plan_mode",
    "exit_plan_mode",
    # 用户交互
    "AskUser",
    # 工具搜索（自身）
    "tool_search",
    # Monitor
    "SpawnMonitorTool",
    "ManageMonitorTool",
    # Memory
    "MemoryTool",
    # Skill 加载
    "ListSkills",
    "LoadSkill",
    "SearchStoreSkills",
    "EnableSkill",
    "DisableSkill",
    # 工作区运行环境
    "RuntimeEnvironment",
}


def _to_snake_case(value: str) -> str:
    step1 = _FIRST_CAP_RE.sub(r"\1_\2", value)
    return _ALL_CAP_RE.sub(r"\1_\2", step1).replace("-", "_").lower()


def _resolve_pointer(schema: dict[str, Any], ref: str) -> Any:
    current: Any = schema
    for raw_part in ref.removeprefix("#/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict):
            raise KeyError(ref)
        current = current[part]
    return current


def _inline_local_refs(schema: dict[str, Any]) -> dict[str, Any]:
    root = deepcopy(schema)

    def _resolve(node: Any, seen: set[str]) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/"):
                if ref in seen:
                    return {}
                target = deepcopy(_resolve_pointer(root, ref))
                resolved_target = _resolve(target, seen | {ref})
                sibling_items = {
                    key: _resolve(value, seen) for key, value in node.items() if key != "$ref"
                }
                if isinstance(resolved_target, dict):
                    resolved_target.update(sibling_items)
                return resolved_target

            return {key: _resolve(value, seen) for key, value in node.items() if key != "$defs"}

        if isinstance(node, list):
            return [_resolve(item, seen) for item in node]

        return node

    resolved = _resolve(root, set())
    if isinstance(resolved, dict):
        resolved.pop("$defs", None)
    return resolved


class ToolRegistry:
    """AIASys-native tool 注册表。"""

    def __init__(self) -> None:
        self._tools: dict[str, AiasysTool] = {}
        self._aliases: dict[str, str] = {}

    def register(self, tool: AiasysTool) -> None:
        name = str(tool.name or "").strip()
        if not name:
            raise ValueError("Tool name is required")

        is_mcp = getattr(tool, "is_mcp", False) or name.startswith("mcp_")

        if name in self._tools:
            existing = self._tools[name]
            existing_is_mcp = getattr(existing, "is_mcp", False) or existing.name.startswith("mcp_")
            # MCP 工具与内置工具冲突：自动加前缀重命名
            if is_mcp and not existing_is_mcp:
                new_name = f"mcp_{name}"
                logger.warning(
                    "MCP 工具 '%s' 与内置工具冲突，已重命名为 '%s'",
                    name,
                    new_name,
                )
                tool.name = new_name
                name = new_name
            else:
                raise ValueError(f"Tool {name!r} is already registered")

        self._tools[name] = tool
        for alias in {name.lower(), _to_snake_case(name)}:
            if not alias or alias == name:
                continue
            existing = self._aliases.get(alias)
            if existing and existing != name:
                logger.warning(
                    "Tool alias conflict: %r already points to %r, skipping %r",
                    alias,
                    existing,
                    name,
                )
                continue
            self._aliases[alias] = name

    def get_openai_schema(self) -> list[dict[str, Any]]:
        """返回 OpenAI 格式的工具 schema 列表。

        排序策略：内置工具在前，MCP 工具在后，各自按名称字母序。
        避免 MCP 工具穿插破坏 prompt cache 前缀稳定性。
        """
        builtin_schemas: list[dict[str, Any]] = []
        mcp_schemas: list[dict[str, Any]] = []
        for tool in self._tools.values():
            raw_parameters = getattr(tool, "parameters", None)
            if not raw_parameters:
                raw_parameters = tool.__class__.parameter_schema()
            entry = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": _inline_local_refs(raw_parameters),
                },
            }
            # MCP 工具判断：以 mcp_ 前缀或来源标记
            if tool.name.startswith("mcp_") or getattr(tool, "is_mcp", False):
                mcp_schemas.append(entry)
            else:
                builtin_schemas.append(entry)
        # 各自按名称排序，确保顺序稳定
        builtin_schemas.sort(key=lambda x: x["function"]["name"])
        mcp_schemas.sort(key=lambda x: x["function"]["name"])
        return builtin_schemas + mcp_schemas

    def get_openai_schema_filtered(self, allowed_names: set[str]) -> list[dict[str, Any]]:
        """按工具运行时名称过滤 OpenAI schema。"""
        allowed = {str(name or "").strip() for name in allowed_names if str(name or "").strip()}
        return [
            schema
            for schema in self.get_openai_schema()
            if schema.get("function", {}).get("name") in allowed
        ]

    def _is_non_deferred(self, tool: AiasysTool) -> bool:
        """判断工具是否属于 non-deferred 白名单（始终发送给 LLM）。"""
        name = str(tool.name or "")
        short = name.split(":")[-1].split(".")[-1]
        class_name = type(tool).__name__
        return (
            short in NON_DEFERRED_TOOL_NAMES
            or name in NON_DEFERRED_TOOL_NAMES
            or class_name in NON_DEFERRED_TOOL_NAMES
        )

    def get_openai_schemas_split(
        self,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """返回 (non_deferred_schemas, deferred_schemas)。

        non_deferred: 白名单中的核心工具，始终发送。
        deferred: 其余工具，由策略决定如何渐进式暴露（defer_loading 或 tool_search）。
        """
        non_deferred: list[dict[str, Any]] = []
        deferred: list[dict[str, Any]] = []
        for tool in self._tools.values():
            raw_parameters = getattr(tool, "parameters", None)
            if not raw_parameters:
                raw_parameters = tool.__class__.parameter_schema()
            entry = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": _inline_local_refs(raw_parameters),
                },
            }
            if self._is_non_deferred(tool):
                non_deferred.append(entry)
            else:
                deferred.append(entry)
        non_deferred.sort(key=lambda x: x["function"]["name"])
        deferred.sort(key=lambda x: x["function"]["name"])
        return non_deferred, deferred

    def get_openai_schemas_split_filtered(
        self,
        allowed_names: set[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """按工具运行时名称过滤 split schema。"""
        allowed = {str(name or "").strip() for name in allowed_names if str(name or "").strip()}
        non_deferred, deferred = self.get_openai_schemas_split()
        return (
            [
                schema
                for schema in non_deferred
                if schema.get("function", {}).get("name") in allowed
            ],
            [schema for schema in deferred if schema.get("function", {}).get("name") in allowed],
        )

    def _resolve_tool(self, name: str) -> AiasysTool:
        tool_name = self._aliases.get(name, name)
        tool = self._tools.get(tool_name)
        if tool is None:
            raise KeyError(f"Tool {name!r} is not registered")
        return tool

    def get_tool(self, name: str) -> AiasysTool | None:
        try:
            return self._resolve_tool(name)
        except KeyError:
            return None

    async def invoke(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        ctx: dict[str, Any] | None = None,
    ) -> ToolResult:
        if not isinstance(arguments, dict):
            raise TypeError("Tool arguments must be a dict")

        tool = self._resolve_tool(name)
        return ToolResult.from_value(await tool.invoke(ctx, **arguments))

    async def invoke_stream(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        ctx: dict[str, Any] | None = None,
    ) -> AsyncGenerator[ToolStreamEvent, None]:
        """流式调用工具。

        若工具实现了 invoke_stream() 且产生多个事件，则逐个 yield ToolStreamEvent。
        若工具只实现了 invoke() 或未产生流式事件，则包装为单次 result 事件 yield。
        """
        if not isinstance(arguments, dict):
            raise TypeError("Tool arguments must be a dict")

        tool = self._resolve_tool(name)

        # 检查工具是否实现了自定义的 invoke_stream
        # 默认实现（在 AiasysTool 基类中）只 yield 单次结果
        stream_gen = tool.invoke_stream(ctx, **arguments)
        result_yielded = False
        event_yielded = False

        async for item in stream_gen:
            # item 是 ToolResult
            # 检查是否包含流式中间事件标记
            artifacts = item.artifacts or []
            streaming_events: list[Any] = []
            for a in artifacts:
                if not isinstance(a, dict):
                    continue
                ev = a.get("_streaming_event")
                if ev is None:
                    continue
                if isinstance(ev, AgentRuntimeEvent):
                    streaming_events.append(ev)
                elif isinstance(ev, dict):
                    try:
                        streaming_events.append(AgentRuntimeEvent(**ev))
                    except Exception:
                        logger.warning("无法解析 _streaming_event: %s", ev)

            if streaming_events:
                event_yielded = True
                for runtime_event in streaming_events:
                    yield ToolStreamEvent(
                        kind="event",
                        runtime_event=runtime_event,
                    )
            else:
                # 正常的最终结果（或无标记的单次结果）
                yield ToolStreamEvent(
                    kind="result",
                    tool_result=ToolResult.from_value(item),
                )
                result_yielded = True

        if not result_yielded and not event_yielded:
            # 如果流式调用没有 yield 任何结果（不应该发生），
            # 兜底用 invoke() 获取结果
            fallback = await tool.invoke(ctx, **arguments)
            yield ToolStreamEvent(
                kind="result",
                tool_result=ToolResult.from_value(fallback),
            )
