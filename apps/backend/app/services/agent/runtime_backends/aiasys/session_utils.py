"""session.py 的模块级辅助函数。"""

from __future__ import annotations

import ast
import json
import logging
from typing import Any

from ..base import AgentRuntimeEvent

logger = logging.getLogger(__name__)

_THINKING_BUDGET_BY_EFFORT = {
    "minimal": 1024,
    "low": 2048,
    "medium": 4096,
    "high": 8192,
    "xhigh": 16384,
}


def merge_stream_fragment(current: str, fragment: str) -> str:
    if not fragment:
        return current
    if not current:
        return fragment
    if fragment.startswith(current):
        return fragment
    if current.endswith(fragment):
        return current
    return current + fragment


def safe_parse_json(raw_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_text or "{}")
    except json.JSONDecodeError:
        logger.warning("解析 tool arguments 失败: %s", (raw_text or "")[:200])
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {"value": parsed}


def extract_usage_counts(usage: Any) -> tuple[int, int]:
    if not isinstance(usage, dict):
        return 0, 0

    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    if prompt_tokens is None:
        prompt_tokens = usage.get("input_tokens", 0)
    if completion_tokens is None:
        completion_tokens = usage.get("output_tokens", 0)

    return int(prompt_tokens or 0), int(completion_tokens or 0)


def extract_reasoning_content(delta: dict[str, Any]) -> str:
    raw_reasoning = delta.get("reasoning_content")
    if isinstance(raw_reasoning, str):
        return raw_reasoning
    if isinstance(raw_reasoning, list):
        parts: list[str] = []
        for item in raw_reasoning:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)
    if isinstance(raw_reasoning, dict):
        text = raw_reasoning.get("text")
        if isinstance(text, str):
            return text
    return ""


def read_config_value(config: Any, field_name: str) -> Any:
    if isinstance(config, dict):
        return config.get(field_name)
    return getattr(config, field_name, None)


def normalize_capabilities(raw_capabilities: Any) -> set[str]:
    if raw_capabilities is None:
        return set()
    if isinstance(raw_capabilities, str):
        try:
            parsed = ast.literal_eval(raw_capabilities)
        except (SyntaxError, ValueError):
            parsed = raw_capabilities
        return normalize_capabilities(parsed)
    if isinstance(raw_capabilities, (list, set, tuple)):
        return {
            str(capability).strip() for capability in raw_capabilities if str(capability).strip()
        }
    return {str(raw_capabilities).strip()} if str(raw_capabilities).strip() else set()


def normalize_thinking_effort(raw_effort: Any) -> str | None:
    if raw_effort is None:
        return None
    effort = str(raw_effort).strip().lower()
    if not effort or effort == "none":
        return None
    if effort in _THINKING_BUDGET_BY_EFFORT:
        return effort
    if effort == "max":
        return "xhigh"
    return None


def wrap_subagent_event(
    sub_event: AgentRuntimeEvent,
    parent_tool_call_id: str,
) -> AgentRuntimeEvent:
    """将子 Agent 的 AgentRuntimeEvent 包装为 Host 事件流中的 subagent 事件。"""
    kind = sub_event.kind

    if kind == "content" and sub_event.content_type == "text":
        return AgentRuntimeEvent(
            kind="subagent_content",
            content_type="text",
            text=sub_event.text,
            task_tool_call_id=parent_tool_call_id,
            parent_tool_call_id=parent_tool_call_id,
            agent_id=sub_event.agent_id,
            subagent_type=sub_event.subagent_type,
            subagent_name=sub_event.subagent_name,
        )

    if kind == "content" and sub_event.content_type == "think":
        return AgentRuntimeEvent(
            kind="subagent_content",
            content_type="think",
            think=sub_event.think,
            task_tool_call_id=parent_tool_call_id,
            parent_tool_call_id=parent_tool_call_id,
            agent_id=sub_event.agent_id,
            subagent_type=sub_event.subagent_type,
            subagent_name=sub_event.subagent_name,
        )

    if kind == "tool_call":
        return AgentRuntimeEvent(
            kind="subagent_tool_call",
            tool_call_id=sub_event.tool_call_id,
            tool_name=sub_event.tool_name,
            arguments=sub_event.arguments,
            task_tool_call_id=parent_tool_call_id,
            parent_tool_call_id=parent_tool_call_id,
            agent_id=sub_event.agent_id,
            subagent_type=sub_event.subagent_type,
            subagent_name=sub_event.subagent_name,
        )

    if kind == "tool_result":
        return AgentRuntimeEvent(
            kind="subagent_tool_result",
            tool_call_id=sub_event.tool_call_id,
            tool_name=sub_event.tool_name,
            content=sub_event.content,
            is_error=sub_event.is_error,
            task_tool_call_id=parent_tool_call_id,
            parent_tool_call_id=parent_tool_call_id,
            agent_id=sub_event.agent_id,
            subagent_type=sub_event.subagent_type,
            subagent_name=sub_event.subagent_name,
        )

    if kind == "worker_lifecycle":
        return AgentRuntimeEvent(
            kind="worker_lifecycle",
            scope="subagent",
            status=sub_event.status,
            reason=sub_event.reason,
            task_tool_call_id=parent_tool_call_id,
            parent_tool_call_id=parent_tool_call_id,
            agent_id=sub_event.agent_id,
            subagent_type=sub_event.subagent_type,
            subagent_name=sub_event.subagent_name,
        )

    if kind == "token_usage":
        return AgentRuntimeEvent(
            kind="token_usage",
            input_tokens=sub_event.input_tokens,
            output_tokens=sub_event.output_tokens,
            task_tool_call_id=parent_tool_call_id,
            parent_tool_call_id=parent_tool_call_id,
        )

    if kind == "ask_user_request":
        return AgentRuntimeEvent(
            kind="ask_user_request",
            content=sub_event.content,
            task_tool_call_id=parent_tool_call_id,
            parent_tool_call_id=parent_tool_call_id,
        )

    # 其他类型透传为 data
    return AgentRuntimeEvent(
        kind="data",
        content=str(sub_event),
        task_tool_call_id=parent_tool_call_id,
        parent_tool_call_id=parent_tool_call_id,
    )
