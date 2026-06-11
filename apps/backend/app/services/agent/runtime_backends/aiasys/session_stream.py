"""SessionStreamMixin — ReAct prompt 流式循环。

从 AiasysRuntimeSession 中提取，保持核心类精简。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from app.core.tool_result import ToolResult
from app.services.agent.authorization import (
    AuthorizationMode,
    CapabilityAuthorizationRequest,
    CapabilityAuthorizationService,
)
from app.services.agent.message_content import (
    downgrade_message_content_for_history,
    hydrate_message_images,
)

from ..base import AgentRuntimeEvent
from .llm_clients.error_classifier import classify_api_error
from .llm_clients.retry_utils import jittered_backoff
from .session_utils import (
    extract_usage_counts,
    merge_stream_fragment,
    normalize_capabilities,
    read_config_value,
)

logger = logging.getLogger(__name__)


def _serialize_tool_content_for_event(content: str | list[dict[str, Any]]) -> str:
    """把 tool result 的结构化 content 序列化为事件展示字符串。"""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "text":
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
        elif item_type == "image_url":
            image_url = item.get("image_url", {})
            url = image_url.get("url") if isinstance(image_url, dict) else str(image_url)
            parts.append(f"![image]({url})")
    return "".join(parts)


class SessionStreamMixin:
    """提供 prompt() ReAct 流式循环，作为 mixin 混入 AiasysRuntimeSession。"""

    def _prepare_messages_for_current_model(self) -> list[dict[str, Any]]:
        # Tier 1: 每次 LLM 调用前执行零成本 tool 结果清理
        self._run_pre_turn_clearing()
        messages = self._messages_for_model()
        capabilities = normalize_capabilities(
            read_config_value(getattr(self, "_model_config", None), "capabilities")
        )
        if "image_in" in capabilities:
            return hydrate_message_images(
                messages,
                workspace_dir=Path(str(self._spec.work_dir)),
            )

        prepared: list[dict[str, Any]] = []
        for message in messages:
            downgraded_content = downgrade_message_content_for_history(message.get("content"))
            if downgraded_content == message.get("content"):
                prepared.append(message)
                continue

            updated_message = dict(message)
            updated_message["content"] = downgraded_content
            prepared.append(updated_message)
        return prepared

    async def prompt(
        self,
        user_input: str | list[dict[str, Any]],
        *,
        merge_wire_messages: bool = False,
    ) -> AsyncGenerator[AgentRuntimeEvent, None]:
        del merge_wire_messages
        if self._closed:
            raise RuntimeError("Runtime session is already closed")
        if self._is_session_budget_blocked():
            yield AgentRuntimeEvent(
                kind="budget_limited",
                text=self._session_budget_limited_text(),
            )
            yield AgentRuntimeEvent(
                kind="budget_updated",
                text=json.dumps(
                    {
                        "token_budget": self.budget.token_budget if self.budget else None,
                        "tokens_used": self.budget.tokens_used if self.budget else 0,
                        "time_budget_seconds": (
                            self.budget.time_budget_seconds if self.budget else None
                        ),
                        "time_used_seconds": self.budget.time_used_seconds if self.budget else 0,
                        "status": self.budget.status if self.budget else "active",
                    },
                    ensure_ascii=False,
                ),
            )
            return

        self.messages = self._downgrade_historical_image_messages(self.messages)
        normalized_input = self._normalize_user_input(user_input)
        existing_user_message_ids = {
            str(message.get("id"))
            for message in self.messages
            if isinstance(message, dict)
            and message.get("role") == "user"
            and message.get("id") is not None
        }
        for msg in normalized_input:
            msg_id = msg.get("id") if isinstance(msg, dict) else None
            if (
                isinstance(msg_id, str)
                and msg_id in existing_user_message_ids
                and msg.get("role") == "user"
            ):
                continue
            self._append_message(msg)
        self._continuation_count = 0

        # ---- 上下文自动压缩 ----
        await self._maybe_compact_context()

        total_input_tokens = 0
        total_output_tokens = 0

        max_turns = self._spec.config.loop_control.max_steps_per_turn
        for _turn in range(max_turns):
            if self._cancel_event.is_set():
                break

            assistant_parts: list[str] = []
            assistant_reasoning = ""
            aggregated_tool_calls: dict[int, dict[str, Any]] = {}
            latest_finish_reason: str | None = None
            latest_usage: dict[str, Any] | None = None

            stream_error: Exception | None = None
            for retry_attempt in range(4):  # 1 次原始 + 3 次重试
                if self._cancel_event.is_set():
                    break

                # 重试时清空上一轮已收集的片段
                if retry_attempt > 0:
                    assistant_parts = []
                    assistant_reasoning = ""
                    aggregated_tool_calls = {}
                    latest_finish_reason = None
                    latest_usage = None

                try:
                    messages_for_model = self._prepare_messages_for_current_model()
                    async for chunk in self._client.chat_stream(
                        messages_for_model,
                        self._prepare_tools_for_model(),
                        self._resolve_temperature(),
                        self._resolve_max_tokens(),
                        request_options=self._resolve_request_options(),
                    ):
                        if self._cancel_event.is_set():
                            break

                        if chunk.usage is not None:
                            latest_usage = chunk.usage

                        if chunk.finish_reason:
                            latest_finish_reason = chunk.finish_reason

                        delta = chunk.delta
                        if delta.content:
                            assistant_parts.append(delta.content)
                            yield AgentRuntimeEvent(
                                kind="content",
                                content_type="text",
                                text=delta.content,
                            )

                        if delta.reasoning_content:
                            assistant_reasoning = merge_stream_fragment(
                                assistant_reasoning,
                                delta.reasoning_content,
                            )
                            yield AgentRuntimeEvent(
                                kind="content",
                                content_type="think",
                                think=delta.reasoning_content,
                            )

                        for tool_delta in delta.tool_calls or []:
                            if not isinstance(tool_delta, dict):
                                continue
                            index = int(tool_delta.get("index", 0))
                            current = aggregated_tool_calls.setdefault(
                                index,
                                {
                                    "id": None,
                                    "name": "",
                                    "arguments_text": "",
                                },
                            )
                            tool_id = tool_delta.get("id")
                            if isinstance(tool_id, str) and tool_id.strip():
                                current["id"] = tool_id.strip()

                            function = tool_delta.get("function") or {}
                            function_name = function.get("name")
                            if isinstance(function_name, str) and function_name:
                                current["name"] = merge_stream_fragment(
                                    current["name"],
                                    function_name,
                                )

                            arguments_fragment = function.get("arguments")
                            if isinstance(arguments_fragment, str) and arguments_fragment:
                                current["arguments_text"] += arguments_fragment

                    stream_error = None
                    break

                except Exception as exc:
                    model_id = self._resolve_model_id()
                    classified = classify_api_error(
                        exc,
                        provider="",
                        model=model_id,
                        approx_tokens=self._estimated_token_count,
                        num_messages=len(self.messages),
                    )

                    if not classified.retryable or retry_attempt >= 3:
                        stream_error = exc
                        break

                    if classified.should_compress:
                        try:
                            await self._maybe_compact_context()
                        except Exception as compact_exc:
                            logger.warning("重试前上下文压缩失败: %s", compact_exc)

                    delay = jittered_backoff(retry_attempt + 1)
                    logger.warning(
                        "API 错误[%s]，%.1f 秒后第 %d 次重试: %s",
                        classified.reason.value,
                        delay,
                        retry_attempt + 1,
                        classified.message,
                    )
                    await asyncio.sleep(delay)
                    continue

            if self._cancel_event.is_set():
                break

            # 流中断恢复：重试用尽后，若已收集到部分内容则作为 fallback
            if stream_error is not None:
                fallback_content = "".join(assistant_parts)
                if fallback_content or assistant_reasoning or aggregated_tool_calls:
                    logger.warning(
                        "流中断，使用已传输内容作为最终响应: %d 字符",
                        len(fallback_content),
                    )
                    fallback_message: dict[str, Any] = {"role": "assistant"}
                    if fallback_content:
                        fallback_message["content"] = fallback_content
                    if assistant_reasoning:
                        fallback_message["reasoning_content"] = assistant_reasoning
                    self._append_message(fallback_message)
                    yield AgentRuntimeEvent(
                        kind="system_warning",
                        text=f"流式输出中断，使用已传输的 {len(fallback_content)} 字符作为最终响应。",
                    )
                    break
                raise stream_error

            input_tokens, output_tokens = extract_usage_counts(latest_usage)
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens
            self._log_cache_stats(latest_usage)

            # 用 LLM 返回的精确 prompt_tokens 修正估算值，优先于预算检查
            if latest_usage is not None:
                prompt_tokens = latest_usage.get("prompt_tokens")
                if prompt_tokens is None:
                    prompt_tokens = latest_usage.get("input_tokens")
                if isinstance(prompt_tokens, int) and prompt_tokens > 0:
                    self._estimated_token_count = prompt_tokens
                    self._save_context_tokens_to_metadata()

            # Session 级预算检查（在 _estimated_token_count 修正之后）
            if self.budget is not None and self.budget.status == "active":
                self._check_session_budget(input_tokens, output_tokens)

            assistant_content = "".join(assistant_parts) or None
            assistant_reasoning_content = assistant_reasoning or ""
            tool_calls = self._build_openai_tool_calls(aggregated_tool_calls)

            # Fallback: if no structured tool_calls but content has raw tags
            if not tool_calls and assistant_content and self._prepare_tools_for_model():
                raw_text = assistant_content
                if any(
                    tag in raw_text
                    for tag in (
                        "<tool_call>",
                        "<｜tool▁calls▁begin｜>",
                        "<|tool_calls_section_begin|>",
                        "<function=",
                        "[TOOL_CALLS]",
                        "<longcat_tool_call>",
                    )
                ):
                    try:
                        from .tool_call_parsers import get_parser

                        for parser_name in (
                            "hermes",
                            "deepseek_v3",
                            "kimi_k2",
                            "glm45",
                            "qwen3_coder",
                            "mistral",
                            "longcat",
                        ):
                            try:
                                parser = get_parser(parser_name)
                                parsed_content, parsed_calls = parser.parse(raw_text)
                                if parsed_calls:
                                    if parsed_content:
                                        assistant_content = parsed_content
                                    tool_calls = []
                                    for tc in parsed_calls:
                                        args_str = tc["function"]["arguments"]
                                        parsed_args, parse_error = self._safe_parse_arguments(
                                            tc["function"]["name"], args_str
                                        )
                                        tool_calls.append(
                                            {
                                                "id": tc["id"],
                                                "type": "function",
                                                "function": {
                                                    "name": tc["function"]["name"],
                                                    "arguments": args_str,
                                                },
                                                "arguments": parsed_args,
                                                "_parse_error": parse_error,
                                            }
                                        )
                                    break
                            except Exception:
                                continue
                    except Exception:
                        pass

            if tool_calls:
                assistant_message: dict[str, Any] = {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": item["id"],
                            "type": item["type"],
                            "function": item["function"],
                        }
                        for item in tool_calls
                    ],
                }
                if assistant_content is not None:
                    assistant_message["content"] = assistant_content
                if assistant_reasoning_content is not None:
                    assistant_message["reasoning_content"] = assistant_reasoning_content
                self._append_message(assistant_message)

                tool_ctx = self._tool_context()
                for item in tool_calls:
                    yield AgentRuntimeEvent(
                        kind="tool_call",
                        tool_call_id=item["id"],
                        tool_name=item["function"]["name"],
                        arguments=item["arguments"],
                    )

                    # 循环检测
                    loop_warning = self._check_loop_detection(
                        item["function"]["name"],
                        item["arguments"],
                    )
                    if loop_warning:
                        yield AgentRuntimeEvent(
                            kind="system_warning",
                            text=loop_warning,
                        )
                        tool_result = ToolResult(
                            content=loop_warning,
                            is_error=True,
                        )
                        yield AgentRuntimeEvent(
                            kind="tool_result",
                            tool_call_id=item["id"],
                            tool_name=item["function"]["name"],
                            content=_serialize_tool_content_for_event(tool_result.content),
                            is_error=tool_result.is_error,
                        )
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": item["id"],
                            "content": tool_result.content,
                        }
                        self._append_message(tool_msg)
                        continue

                    # 参数解析错误
                    parse_error = item.get("_parse_error")
                    if parse_error:
                        tool_result = ToolResult(content=parse_error, is_error=True)
                        yield AgentRuntimeEvent(
                            kind="tool_result",
                            tool_call_id=item["id"],
                            tool_name=item["function"]["name"],
                            content=_serialize_tool_content_for_event(tool_result.content),
                            is_error=tool_result.is_error,
                        )
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": item["id"],
                            "content": tool_result.content,
                        }
                        self._append_message(tool_msg)
                        continue

                    if not self._is_tool_allowed_in_current_mode(item["function"]["name"]):
                        tool_result = ToolResult(
                            content=(
                                "当前处于 Plan Mode，只允许只读探索、task_list、AskUser "
                                "和 exit_plan_mode。请先提交计划并等待用户批准。"
                            ),
                            is_error=True,
                        )
                        yield AgentRuntimeEvent(
                            kind="tool_result",
                            tool_call_id=item["id"],
                            tool_name=item["function"]["name"],
                            content=_serialize_tool_content_for_event(tool_result.content),
                            is_error=tool_result.is_error,
                        )
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": item["id"],
                            "content": tool_result.content,
                        }
                        self._append_message(tool_msg)
                        continue

                    # 能力授权决策：所有工具调用都经过 CapabilityAuthorizationService
                    resolved_tool_name = self._tool_registry._aliases.get(
                        item["function"]["name"], item["function"]["name"]
                    )
                    tool = self._tool_registry._tools.get(resolved_tool_name)

                    # 读取工具风险元数据
                    tool_risk = getattr(tool, "risk_level", "medium") if tool is not None else "medium"
                    tool_scope = getattr(tool, "effect_scope", "workspace") if tool is not None else "workspace"
                    tool_side_effect = getattr(tool, "side_effect", True) if tool is not None else True

                    # 确定授权模式：spec.authorization_mode 优先，yolo 做兼容映射
                    auth_mode_str = self._spec.authorization_mode
                    if self._spec.yolo and auth_mode_str == "smart":
                        auth_mode_str = "full_auto"

                    # EnableSkill 时尝试读取 Skill 安全元数据
                    skill_security: dict[str, Any] = {}
                    if resolved_tool_name in ("EnableSkill", "DisableSkill"):
                        skill_name = item["arguments"].get("name", "")
                        if skill_name:
                            skill_security = self._get_skill_security(skill_name)

                    auth_request = CapabilityAuthorizationRequest(
                        tool_name=resolved_tool_name or item["function"]["name"],
                        arguments=item["arguments"],
                        risk_level=tool_risk,
                        effect_scope=tool_scope,
                        side_effect=tool_side_effect,
                        authorization_mode=AuthorizationMode(auth_mode_str),
                        is_subagent=self._spec.is_subagent,
                        skill_security=skill_security,
                    )
                    auth_result = CapabilityAuthorizationService.decide(auth_request)

                    if auth_result.decision in ("ask",):
                        # 向后兼容：同时发送 approval_required 和 capability_confirmation
                        yield AgentRuntimeEvent(
                            kind="approval_required",
                            tool_call_id=item["id"],
                            tool_name=item["function"]["name"],
                            arguments=item["arguments"],
                        )
                        yield AgentRuntimeEvent(
                            kind="capability_confirmation",
                            tool_call_id=item["id"],
                            tool_name=item["function"]["name"],
                            arguments=item["arguments"],
                            content=auth_result.confirmation_prompt
                            or f"是否允许执行工具 {item['function']['name']}？",
                        )

                        # 挂起等待用户通过 API 确认 / 拒绝
                        approved, feedback = await self._confirmation_manager.wait_for_confirmation(
                            tool_call_id=item["id"],
                            tool_name=item["function"]["name"],
                            arguments=item["arguments"],
                            prompt=auth_result.confirmation_prompt
                            or f"是否允许执行工具 {item['function']['name']}？",
                            pattern_key=auth_result.pattern_key,
                            subagent_name=getattr(self._spec, "subagent_name", None),
                            agent_id=getattr(self._spec, "agent_id", None),
                        )

                        if not approved:
                            denial_msg = feedback or "操作被拒绝"
                            tool_result = ToolResult(content=denial_msg, is_error=True)
                            yield AgentRuntimeEvent(
                                kind="tool_result",
                                tool_call_id=item["id"],
                                tool_name=item["function"]["name"],
                                content=_serialize_tool_content_for_event(tool_result.content),
                                is_error=tool_result.is_error,
                            )
                            tool_msg = {
                                "role": "tool",
                                "tool_call_id": item["id"],
                                "content": tool_result.content,
                            }
                            self._append_message(tool_msg)
                            continue

                        # 用户批准：继续执行工具（不 continue，走到下面的工具调用逻辑）

                    if auth_result.decision in ("deny", "block"):
                        denial_msg = (
                            auth_result.denial_message
                            or f"工具 {item['function']['name']} 已被系统拦截：{auth_result.reason}"
                        )
                        tool_result = ToolResult(content=denial_msg, is_error=True)
                        yield AgentRuntimeEvent(
                            kind="tool_result",
                            tool_call_id=item["id"],
                            tool_name=item["function"]["name"],
                            content=_serialize_tool_content_for_event(tool_result.content),
                            is_error=tool_result.is_error,
                        )
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": item["id"],
                            "content": tool_result.content,
                        }
                        self._append_message(tool_msg)
                        continue

                    # 构建带 tool_call_id 的 ctx，供 TaskTool 使用
                    item_ctx = {**tool_ctx, "_tool_call_id": item["id"]}

                    async def _collect_tool_events() -> list[Any]:
                        events: list[Any] = []
                        async for stream_event in self._tool_registry.invoke_stream(
                            item["function"]["name"],
                            item["arguments"],
                            ctx=item_ctx,
                        ):
                            events.append(stream_event)
                            if stream_event.kind == "result":
                                break
                        return events

                    try:
                        tool_events = await asyncio.wait_for(_collect_tool_events(), timeout=300)
                        final_tool_result: ToolResult | None = None
                        for stream_event in tool_events:
                            if (
                                stream_event.kind == "event"
                                and stream_event.runtime_event is not None
                            ):
                                from .session_utils import wrap_subagent_event

                                wrapped = wrap_subagent_event(
                                    stream_event.runtime_event,
                                    item["id"],
                                )
                                yield wrapped
                            elif stream_event.kind == "result":
                                final_tool_result = stream_event.tool_result

                        tool_result = final_tool_result or ToolResult(
                            content="无结果", is_error=True
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            "工具执行超时(300秒): session=%s tool=%s",
                            self.session_id,
                            item["function"]["name"],
                        )
                        tool_result = ToolResult(content="工具执行超时（300秒）", is_error=True)
                    except Exception as exc:
                        logger.exception(
                            "工具执行失败: session=%s tool=%s",
                            self.session_id,
                            item["function"]["name"],
                        )
                        tool_result = ToolResult(content=str(exc), is_error=True)

                    yield AgentRuntimeEvent(
                        kind="tool_result",
                        tool_call_id=item["id"],
                        tool_name=item["function"]["name"],
                        content=_serialize_tool_content_for_event(tool_result.content),
                        is_error=tool_result.is_error,
                    )
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": item["id"],
                        "content": tool_result.content,
                    }
                    self._append_message(tool_msg)

                    # 工具执行成功后重置循环计数器
                    if not tool_result.is_error:
                        self._reset_loop_counter(item["function"]["name"])

                continue

            if assistant_content is not None:
                assistant_message = {
                    "role": "assistant",
                    "content": assistant_content,
                }
                if assistant_reasoning_content is not None:
                    assistant_message["reasoning_content"] = assistant_reasoning_content
                self._append_message(assistant_message)

            if latest_finish_reason == "length":
                self._continuation_count += 1
                if self._continuation_count > 3:
                    logger.warning("输出截断续写次数超过上限（3次），停止")
                    yield AgentRuntimeEvent(
                        kind="system_warning",
                        text="输出被截断，续写次数已达上限。",
                    )
                    break

                # 保存已收集的部分 assistant 消息
                partial_message: dict[str, Any] = {"role": "assistant"}
                if assistant_content is not None:
                    partial_message["content"] = assistant_content
                if assistant_reasoning_content is not None:
                    partial_message["reasoning_content"] = assistant_reasoning_content
                if tool_calls:
                    partial_message["tool_calls"] = [
                        {
                            "id": item["id"],
                            "type": item["type"],
                            "function": item["function"],
                        }
                        for item in tool_calls
                    ]
                self._append_message(partial_message)

                # 注入续写提示
                self._append_message(
                    {
                        "role": "user",
                        "content": "[System: Your previous response was truncated due to length limit. Continue exactly where you left off without repeating anything already said.]",
                    }
                )

                logger.info(
                    "检测到 finish_reason=length，触发第 %d 次自动续写",
                    self._continuation_count,
                )
                continue

            if latest_finish_reason != "tool_calls":
                break

        if total_input_tokens or total_output_tokens:
            yield AgentRuntimeEvent(
                kind="token_usage",
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
            )

        # Budget Mode: 推送最终 session budget 状态
        if self.budget is not None:
            yield AgentRuntimeEvent(
                kind="budget_updated",
                text=json.dumps(
                    {
                        "token_budget": self.budget.token_budget,
                        "tokens_used": self.budget.tokens_used,
                        "time_budget_seconds": self.budget.time_budget_seconds,
                        "time_used_seconds": self.budget.time_used_seconds,
                        "status": self.budget.status,
                    },
                    ensure_ascii=False,
                ),
            )

    def _get_skill_security(self, skill_name: str) -> dict[str, Any]:
        """查询 Skill 安全元数据，用于 EnableSkill/DisableSkill 授权决策。"""
        try:
            from pathlib import Path

            from app.skills.manager import get_skill_manager

            workspace_path = Path(str(self._spec.work_dir))
            mgr = get_skill_manager()
            all_skills = mgr.list_all_skills(workspace_path)
            for skill in all_skills:
                if skill.name == skill_name:
                    sec = skill.security
                    return {
                        "source_trust": sec.source_trust,
                        "risk_level": sec.risk_level,
                        "has_scripts": sec.has_scripts,
                        "requires_env": sec.requires_env,
                        "writes_workspace": sec.writes_workspace,
                        "writes_global": sec.writes_global,
                        "uses_shell": sec.uses_shell,
                        "uses_network": sec.uses_network,
                        "installs_dependencies": sec.installs_dependencies,
                        "adds_tools": sec.adds_tools,
                    }
        except Exception:
            logger.debug("查询 Skill 安全元数据失败: %s", skill_name, exc_info=True)
        return {}

    def _log_cache_stats(self, usage: dict[str, Any] | None) -> None:
        """记录 prefix cache hit 统计（Anthropic / OpenRouter 格式）。"""
        if not usage:
            return
        try:
            prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens", 0)
            cached = usage.get("cache_read_input_tokens", 0) or 0
            written = usage.get("cache_creation_input_tokens", 0) or 0
            if prompt_tokens and (cached or written):
                hit_pct = cached / prompt_tokens * 100
                logger.info(
                    "Cache: %d/%d tokens (%.0f%% hit, %d written)",
                    cached,
                    prompt_tokens,
                    hit_pct,
                    written,
                )
        except Exception as exc:
            logger.warning("缓存统计失败: %s", exc, exc_info=True)
