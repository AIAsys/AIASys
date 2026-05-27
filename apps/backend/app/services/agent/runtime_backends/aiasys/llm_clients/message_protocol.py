from __future__ import annotations

import json
from typing import Any, Literal, NotRequired, TypedDict

from app.services.agent.message_content import (
    extract_message_text,
    message_content_to_anthropic_input,
    message_content_to_openai_input,
    message_content_to_responses_input,
)

InternalMessageRole = Literal["system", "user", "assistant", "tool"]


class InternalToolFunction(TypedDict, total=False):
    name: str
    arguments: str | dict[str, Any]


class InternalToolCall(TypedDict, total=False):
    id: str
    type: str
    function: InternalToolFunction


class InternalMessage(TypedDict):
    role: InternalMessageRole
    id: NotRequired[str]
    content: NotRequired[Any]
    tool_call_id: NotRequired[str]
    tool_calls: NotRequired[list[InternalToolCall]]
    reasoning_content: NotRequired[Any]


def normalize_internal_message(message: dict[str, Any]) -> InternalMessage:
    role = _coerce_role(message.get("role"))
    normalized: InternalMessage = {
        "role": role,
        "content": message.get("content", ""),
    }

    message_id = message.get("id")
    if isinstance(message_id, str) and message_id.strip():
        normalized["id"] = message_id.strip()

    tool_call_id = message.get("tool_call_id")
    if isinstance(tool_call_id, str) and tool_call_id.strip():
        normalized["tool_call_id"] = tool_call_id.strip()

    tool_calls = _normalize_tool_calls(message.get("tool_calls"))
    if tool_calls:
        normalized["tool_calls"] = tool_calls

    if "reasoning_content" in message:
        normalized["reasoning_content"] = message.get("reasoning_content")

    return normalized


def normalize_internal_messages(messages: list[dict[str, Any]]) -> list[InternalMessage]:
    return [normalize_internal_message(message) for message in messages]


def to_openai_chat_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted_messages: list[dict[str, Any]] = []
    for message in normalize_internal_messages(messages):
        role = message["role"]
        content = message.get("content", "")

        if role == "tool":
            converted_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": message.get("tool_call_id", ""),
                    "content": extract_message_text(content),
                }
            )
            continue

        converted: dict[str, Any] = {
            "role": role,
            "content": message_content_to_openai_input(content),
        }
        if role == "assistant" and message.get("tool_calls"):
            converted["tool_calls"] = [
                _to_openai_tool_call_payload(tool_call) for tool_call in message["tool_calls"]
            ]
        if "reasoning_content" in message:
            converted["reasoning_content"] = message["reasoning_content"]
        converted_messages.append(converted)

    return converted_messages


def to_anthropic_messages(
    messages: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    system_parts: list[str] = []
    anthropic_messages: list[dict[str, Any]] = []

    for message in normalize_internal_messages(messages):
        role = message["role"]
        content = message.get("content", "")

        if role == "system":
            text = extract_message_text(content).strip()
            if text:
                system_parts.append(text)
            continue

        if role == "tool":
            anthropic_messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": message.get("tool_call_id", ""),
                            "content": extract_message_text(content),
                        }
                    ],
                }
            )
            continue

        if role == "assistant" and message.get("tool_calls"):
            anthropic_messages.append(
                {
                    "role": "assistant",
                    "content": _build_anthropic_assistant_blocks(message),
                }
            )
            continue

        if role == "assistant":
            content_blocks: list[dict[str, Any]] = []
            reasoning = message.get("reasoning_content")
            if reasoning:
                content_blocks.append({"type": "thinking", "thinking": reasoning, "signature": ""})
            converted = message_content_to_anthropic_input(content)
            if isinstance(converted, str):
                if converted:
                    content_blocks.append({"type": "text", "text": converted})
            else:
                content_blocks.extend(converted)
            anthropic_messages.append({"role": "assistant", "content": content_blocks})
            continue

        anthropic_messages.append(
            {
                "role": role if role in ("user", "assistant") else "user",
                "content": message_content_to_anthropic_input(content),
            }
        )

    system_prompt = "\n\n".join(system_parts).strip() or None
    return system_prompt, anthropic_messages


def to_anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for tool in tools:
        function = tool.get("function", {})
        entry = {
            "name": function.get("name", ""),
            "description": function.get("description", ""),
            "input_schema": function.get("parameters", {"type": "object"}),
        }
        if tool.get("defer_loading") is True or function.get("defer_loading") is True:
            entry["defer_loading"] = True
        result.append(entry)
    return result


def to_responses_input_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted_messages: list[dict[str, Any]] = []

    for message in normalize_internal_messages(messages):
        role = message["role"]
        content = message.get("content", "")

        if role == "system":
            converted_messages.append(
                {
                    "role": "system",
                    "content": extract_message_text(content),
                }
            )
            continue

        if role == "tool":
            converted_messages.append(
                {
                    "role": "tool",
                    "content": extract_message_text(content),
                    "tool_call_id": message.get("tool_call_id", ""),
                }
            )
            continue

        if role == "assistant" and message.get("tool_calls"):
            assistant_text = extract_message_text(content)
            if assistant_text:
                converted_messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_text,
                    }
                )
            continue

        converted_messages.append(
            {
                "role": role,
                "content": (
                    message_content_to_responses_input(content)
                    if role == "user"
                    else extract_message_text(content)
                ),
            }
        )

    return converted_messages


def _coerce_role(raw_role: Any) -> InternalMessageRole:
    if raw_role in {"system", "assistant", "tool"}:
        return raw_role
    return "user"


def _normalize_tool_calls(raw_tool_calls: Any) -> list[InternalToolCall]:
    if not isinstance(raw_tool_calls, list):
        return []

    normalized: list[InternalToolCall] = []
    for raw_tool_call in raw_tool_calls:
        if not isinstance(raw_tool_call, dict):
            continue
        function = raw_tool_call.get("function") or {}
        if not isinstance(function, dict):
            function = {}
        normalized.append(
            {
                "id": str(raw_tool_call.get("id") or ""),
                "type": str(raw_tool_call.get("type") or "function"),
                "function": {
                    "name": str(function.get("name") or ""),
                    "arguments": _tool_arguments_as_text(function.get("arguments")),
                },
            }
        )

    return normalized


def _tool_arguments_as_text(raw_arguments: Any) -> str:
    if isinstance(raw_arguments, str):
        return raw_arguments
    if raw_arguments in (None, "", {}, []):
        return "{}"
    return json.dumps(raw_arguments, ensure_ascii=False)


def _parse_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
    if isinstance(raw_arguments, str):
        if not raw_arguments.strip():
            return {}
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError:
            return {}
    else:
        parsed = raw_arguments

    if isinstance(parsed, dict):
        return parsed
    if parsed in (None, "", [], ()):
        return {}
    return {"value": parsed}


def _to_openai_tool_call_payload(tool_call: InternalToolCall) -> dict[str, Any]:
    function = tool_call.get("function", {})
    return {
        "id": tool_call.get("id", ""),
        "type": tool_call.get("type", "function"),
        "function": {
            "name": function.get("name", ""),
            "arguments": _tool_arguments_as_text(function.get("arguments")),
        },
    }


def _build_anthropic_assistant_blocks(
    message: InternalMessage,
) -> list[dict[str, Any]]:
    content_blocks: list[dict[str, Any]] = []

    reasoning = message.get("reasoning_content")
    if reasoning:
        content_blocks.append({"type": "thinking", "thinking": reasoning, "signature": ""})

    content = message.get("content", "")
    if content:
        converted_content = message_content_to_anthropic_input(content)
        if isinstance(converted_content, str):
            if converted_content:
                content_blocks.append({"type": "text", "text": converted_content})
        else:
            content_blocks.extend(converted_content)

    for tool_call in message.get("tool_calls", []):
        function = tool_call.get("function", {})
        content_blocks.append(
            {
                "type": "tool_use",
                "id": tool_call.get("id", ""),
                "name": function.get("name", ""),
                "input": _parse_tool_arguments(function.get("arguments")),
            }
        )

    return content_blocks
