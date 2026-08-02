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
InternalMessageOrigin = Literal[
    "user",
    "assistant",
    "tool",
    "system",
    "compaction_summary",
    "system_notice",
    "contextual_user",
    "forked",
]


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
    # Anthropic thinking 块的 signature。原样携带、原样回灌，
    # 绝不伪造空值——空签名会被 Claude 校验拒绝。
    # 注：Responses 协议的 reasoning.encrypted_content 目前未接入本字段
    # （codex_client 未捕获、to_responses_input_messages 未投影），
    # 该链路的加密推理透传属待办，勿据本字段名推断其已支持。
    reasoning_signature: NotRequired[str]
    # Anthropic redacted_thinking 块的 data。与 reasoning_signature 分开承载：
    # 它回灌时是独立的 {"type":"redacted_thinking","data":...} 块，
    # 不是 thinking 块的签名；混用会类型错位并互相覆盖。
    reasoning_redacted_data: NotRequired[str]
    origin: NotRequired[InternalMessageOrigin]
    turn_n: NotRequired[int]


def normalize_internal_message(message: dict[str, Any]) -> InternalMessage:
    role = _coerce_role(message.get("role"))
    content = message.get("content")
    if content is None:
        content = ""
    normalized: InternalMessage = {
        "role": role,
        "content": content,
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

    reasoning_signature = message.get("reasoning_signature")
    if isinstance(reasoning_signature, str) and reasoning_signature.strip():
        normalized["reasoning_signature"] = reasoning_signature.strip()

    reasoning_redacted_data = message.get("reasoning_redacted_data")
    if isinstance(reasoning_redacted_data, str) and reasoning_redacted_data.strip():
        normalized["reasoning_redacted_data"] = reasoning_redacted_data.strip()

    origin = message.get("origin")
    if origin in (
        "user",
        "assistant",
        "tool",
        "system",
        "compaction_summary",
        "system_notice",
        "contextual_user",
        "forked",
    ):
        normalized["origin"] = origin

    turn_n = message.get("turn_n")
    if isinstance(turn_n, int):
        normalized["turn_n"] = turn_n

    return normalized


def normalize_internal_messages(messages: list[dict[str, Any]]) -> list[InternalMessage]:
    return [normalize_internal_message(message) for message in messages]


def to_openai_chat_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted_messages: list[dict[str, Any]] = []
    for message in normalize_internal_messages(messages):
        role = message["role"]
        content = message.get("content", "")

        if role == "tool":
            converted_content = message_content_to_openai_input(content)
            converted_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": message.get("tool_call_id", ""),
                    "content": converted_content,
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


def _build_anthropic_thinking_blocks(
    message: InternalMessage,
    is_native_anthropic: bool,
) -> list[dict[str, Any]]:
    """构造该消息的推理相关块（thinking / redacted_thinking），按协议顺序返回。

    两类块独立存在，同一轮可同时出现，必须各自投影：

    thinking 块按签名三态：
    - 有签名 → 带真实 signature 回填（signed，Claude 官方唯一接受的形态）
    - 无签名 + Anthropic 兼容后端（Kimi 等）→ 保留 thinking 但不带 signature 键，
      避免丢 thinking 导致多步工具调用断裂
    - 无签名 + Claude 官方 → 丢弃该块，绝不伪造空签名

    redacted_thinking 块：内容不可读，data 必须原样回灌，否则后续轮次被拒。
    它不依赖 reasoning_content 是否存在——只有 redacted 没有可读 thinking 是
    合法形态，此时仍须发出该块。
    """
    blocks: list[dict[str, Any]] = []

    reasoning = message.get("reasoning_content")
    if reasoning:
        signature = message.get("reasoning_signature")
        if isinstance(signature, str) and signature.strip():
            blocks.append(
                {
                    "type": "thinking",
                    "thinking": reasoning,
                    "signature": signature.strip(),
                }
            )
        elif not is_native_anthropic:
            blocks.append({"type": "thinking", "thinking": reasoning})

    redacted_data = message.get("reasoning_redacted_data")
    if isinstance(redacted_data, str) and redacted_data.strip():
        blocks.append({"type": "redacted_thinking", "data": redacted_data.strip()})

    return blocks


def to_anthropic_messages(
    messages: list[dict[str, Any]],
    is_native_anthropic: bool = True,
) -> tuple[str | None, list[dict[str, Any]]]:
    """投影为 Anthropic Messages API 格式。

    is_native_anthropic 区分「Claude 官方端点」与「Anthropic 兼容后端」，
    仅影响无签名 thinking 块的取舍。默认 True（对 Claude 官方保守安全）。
    """
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
            converted_content = message_content_to_anthropic_input(content)
            anthropic_messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": message.get("tool_call_id", ""),
                            "content": converted_content,
                        }
                    ],
                }
            )
            continue

        if role == "assistant" and message.get("tool_calls"):
            anthropic_messages.append(
                {
                    "role": "assistant",
                    "content": _build_anthropic_assistant_blocks(
                        message,
                        is_native_anthropic=is_native_anthropic,
                    ),
                }
            )
            continue

        if role == "assistant":
            content_blocks: list[dict[str, Any]] = []
            content_blocks.extend(_build_anthropic_thinking_blocks(message, is_native_anthropic))
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
    is_native_anthropic: bool = True,
) -> list[dict[str, Any]]:
    content_blocks: list[dict[str, Any]] = []

    content_blocks.extend(_build_anthropic_thinking_blocks(message, is_native_anthropic))

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
