"""
AIASys 历史消息压缩机制

自研压缩策略：
- 保留最近 N 条 user/assistant 消息（原样，含图片等多模态内容）
- 其余消息发给 LLM 做总结；总结输入中仅保留 TextPart（白名单过滤）
- 压缩后历史：[user: compaction summary] + [preserved messages]
- 失败时优雅降级（返回原消息列表）
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any

from app.services.agent.runtime_backends.aiasys.llm_clients.base import BaseLlmClient

logger = logging.getLogger(__name__)

# 核心压缩指导 prompt
_COMPACTION_SYSTEM_PROMPT = "You are a helpful assistant that compacts conversation context."

_COMPACTION_USER_PROMPT_TEMPLATE = """The following is a list of messages in an agent conversation. \
Please compact this conversation context according to specific priorities and rules.

**Compression Priorities (in order):**
1. **Current Task State**: What is being worked on RIGHT NOW
2. **Errors & Solutions**: All encountered errors and their resolutions
3. **Code Evolution**: Final working versions only (remove intermediate attempts)
4. **System Context**: Project structure, dependencies, environment setup
5. **Design Decisions**: Architectural choices and their rationale
6. **TODO Items**: Unfinished tasks and known issues

**Compression Rules:**
- MUST KEEP: Error messages, stack traces, working solutions, current task
- MERGE: Similar discussions into single summary points
- REMOVE: Redundant explanations, failed attempts (keep lessons learned), verbose comments
- CONDENSE: Long code blocks → keep signatures + key logic only

**Special Handling:**
- For code: Keep full version if < 20 lines, otherwise keep signature + key logic
- For errors: Keep full error message + final solution
- For discussions: Extract decisions and action items only

**Required Output Structure:**

<current_focus>
[What we're working on now]
</current_focus>

<environment>
- [Key setup/config points]
- ...more...
</environment>

<completed_tasks>
- [Task]: [Brief outcome]
- ...more...
</completed_tasks>

<active_issues>
- [Issue]: [Status/Next steps]
- ...more...
</active_issues>

<code_state>

<file>
[filename]

**Summary:**
[What this code file does]

**Key elements:**
- [Important functions/classes]
- ...more...

**Latest version:**
[Critical code snippets in this file]
</file>

...more files...
</code_state>

<important_context>
- [Any crucial information not covered above]
- ...more...
</important_context>

Here are the messages to compact:

{messages_text}
"""


# ---------------------------------------------------------------------------
# Tier 1: Tool Result Clearing（零成本压缩）
# ---------------------------------------------------------------------------


def _estimate_message_text_length(msg: dict[str, Any]) -> int:
    """估算单条消息的文本长度（字符数）。"""
    content = msg.get("content")
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    total += len(text)
        return total
    return 0


def clear_old_tool_results(
    messages: list[dict[str, Any]],
    *,
    keep_recent_turns: int = 2,
) -> tuple[list[dict[str, Any]], int, int]:
    """将超出保留窗口的旧 tool 结果替换为轻量占位符。

    从后往前数，保留最近 `keep_recent_turns` 个 user/assistant 轮次内的
    所有 tool 消息（含 tool_calls 的 assistant 消息和对应的 tool 结果）。
    更旧的 tool 结果做零成本替换，不调用 LLM。

    Returns:
        (cleared_messages, cleared_count, saved_chars)
    """
    if keep_recent_turns <= 0:
        # 不保留任何完整 tool 上下文，全部替换
        cleared: list[dict[str, Any]] = []
        cleared_count = 0
        saved_chars = 0
        for msg in messages:
            role = msg.get("role")
            if role == "tool":
                new_msg = dict(msg)
                tool_call_id = new_msg.get("tool_call_id", "unknown")
                original_len = _estimate_message_text_length(new_msg)
                new_msg["content"] = f"[已清理: tool 结果 {tool_call_id}]"
                cleared.append(new_msg)
                cleared_count += 1
                saved_chars += max(0, original_len - len(new_msg["content"]))
            elif role == "assistant" and msg.get("tool_calls"):
                # 清理 assistant tool_calls 中大的 arguments
                new_msg = dict(msg)
                tool_calls = list(new_msg.get("tool_calls") or [])
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    func = tc.get("function") or {}
                    args = func.get("arguments", "")
                    if isinstance(args, str) and len(args) > 200:
                        func = dict(func)
                        func["arguments"] = f"[已清理参数，共 {len(args)} 字符]"
                        tc = dict(tc)
                        tc["function"] = func
                new_msg["tool_calls"] = tool_calls
                cleared.append(new_msg)
            else:
                cleared.append(msg)
        return cleared, cleared_count, saved_chars

    # 从后往前定位保留窗口的边界
    history = list(messages)
    preserve_start_index = len(history)
    n_preserved_turns = 0

    for index in range(len(history) - 1, -1, -1):
        if history[index].get("role") in {"user", "assistant"}:
            n_preserved_turns += 1
            if n_preserved_turns == keep_recent_turns:
                preserve_start_index = index
                break

    if n_preserved_turns < keep_recent_turns:
        # 消息总数不足 keep_recent_turns 轮，全部保留
        return messages, 0, 0

    # 保留窗口内（preserve_start_index 及之后）的消息原样保留
    # 窗口之前的 tool 消息做替换
    cleared: list[dict[str, Any]] = []
    cleared_count = 0
    saved_chars = 0
    for idx, msg in enumerate(history):
        role = msg.get("role")
        if idx < preserve_start_index and role == "tool":
            new_msg = dict(msg)
            tool_call_id = new_msg.get("tool_call_id", "unknown")
            original_len = _estimate_message_text_length(new_msg)
            new_msg["content"] = f"[已清理: tool 结果 {tool_call_id}]"
            cleared.append(new_msg)
            cleared_count += 1
            saved_chars += max(0, original_len - len(new_msg["content"]))
        elif idx < preserve_start_index and role == "assistant" and msg.get("tool_calls"):
            new_msg = dict(msg)
            tool_calls = list(new_msg.get("tool_calls") or [])
            new_tool_calls: list[dict[str, Any]] = []
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    new_tool_calls.append(tc)
                    continue
                tc_copy = dict(tc)
                func = tc_copy.get("function") or {}
                args = func.get("arguments", "")
                if isinstance(args, str) and len(args) > 200:
                    func = dict(func)
                    func["arguments"] = f"[已清理参数，共 {len(args)} 字符]"
                    tc_copy["function"] = func
                new_tool_calls.append(tc_copy)
            new_msg["tool_calls"] = new_tool_calls
            cleared.append(new_msg)
        else:
            cleared.append(msg)

    return cleared, cleared_count, saved_chars


def estimate_text_tokens(messages: list[dict[str, Any]]) -> int:
    """从消息文本内容估算 token 数（字符除以 4 的启发式方法）。

    对英文略有低估，对 CJK 文本略有高估，但作为触发阈值已足够保守。
    实际值会在下一次 LLM 调用时由 usage 修正。
    """
    total_chars = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            # 多模态消息列表——仅累加 text 部分
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text")
                    if isinstance(text, str):
                        total_chars += len(text)
    return max(0, total_chars // 4)


def should_auto_compact(
    token_count: int,
    max_context_size: int,
    *,
    trigger_ratio: float = 0.85,
    reserved_context_size: int = 0,
) -> bool:
    """判断是否应该自动触发压缩。

    满足任一条件即触发：
    - 比例触发：token_count >= max_context_size * trigger_ratio
    - 预留触发：token_count + reserved_context_size >= max_context_size
    """
    if max_context_size <= 0:
        return False
    return token_count >= max_context_size * trigger_ratio or (
        reserved_context_size > 0 and token_count + reserved_context_size >= max_context_size
    )


# 双层压缩第一层：snip 截断阈值与比例
_DEFAULT_SNIP_MAX_CHARS = 2000
_SNIP_HEAD_RATIO = 0.5
_SNIP_TAIL_RATIO = 0.25


def _snip_text(content: str, max_chars: int = _DEFAULT_SNIP_MAX_CHARS) -> str:
    """对过长文本进行 snip 截断，保留头部和尾部关键信息。

    保留头部 50% + 尾部 25%，中间替换为占位说明。
    用于双层压缩第一层：在送入 LLM 总结前，对 tool 返回等大量数据做无损截断。
    """
    if len(content) <= max_chars:
        return content
    head_len = int(max_chars * _SNIP_HEAD_RATIO)
    tail_len = int(max_chars * _SNIP_TAIL_RATIO)
    snipped_len = len(content) - head_len - tail_len
    return (
        content[:head_len]
        + f"\n\n[...{snipped_len} characters snipped...]\n\n"
        + content[-tail_len:]
    )


def snip_messages_for_compaction(
    messages: list[dict[str, Any]], max_chars: int = _DEFAULT_SNIP_MAX_CHARS
) -> list[dict[str, Any]]:
    """对消息列表中的过长内容进行 snip 截断（双层压缩第一层）。

    主要针对 tool 返回的大量数据，防止单条消息撑满 LLM 总结输入窗口。
    对多模态 content list 中的长文本也做 snip。
    """
    snipped: list[dict[str, Any]] = []
    for msg in messages:
        new_msg = dict(msg)
        content = new_msg.get("content")

        if isinstance(content, str):
            new_msg["content"] = _snip_text(content, max_chars)
        elif isinstance(content, list):
            new_parts: list[dict[str, Any]] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text", "")
                    if len(text) > max_chars:
                        new_part = dict(part)
                        new_part["text"] = _snip_text(text, max_chars)
                        new_parts.append(new_part)
                    else:
                        new_parts.append(part)
                else:
                    new_parts.append(part)
            new_msg["content"] = new_parts

        snipped.append(new_msg)
    return snipped


def _snip_tool_message(msg: dict[str, Any], max_chars: int) -> dict[str, Any]:
    """对保留窗口内过长的 tool 消息做截断。

    只截断 role='tool' 且 content 为字符串的消息，不影响其他类型。
    """
    if msg.get("role") != "tool":
        return msg
    content = msg.get("content")
    if not isinstance(content, str) or len(content) <= max_chars:
        return msg
    new_msg = dict(msg)
    new_msg["content"] = _snip_text(content, max_chars)
    return new_msg


def _strip_multimodal_content(msg: dict[str, Any]) -> dict[str, Any]:
    """清理消息中的多模态内容，仅保留文本部分。

    用于保留消息的轻量清理：不改变消息角色和结构，只去掉图片/音频/视频等
    非文本 payload，避免 base64 数据长期占用上下文体积。
    """
    sanitized = dict(msg)
    content = sanitized.get("content")

    if isinstance(content, list):
        # 多模态 content list——只保留 text 类型
        text_parts: list[dict[str, Any]] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    text_parts.append(part)
        if text_parts:
            sanitized["content"] = text_parts
        else:
            sanitized["content"] = f"[{msg.get('role', 'unknown')} message with non-text content]"

    return sanitized


def filter_messages_for_compaction(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """过滤消息列表，仅保留适合送入 LLM 做总结的文本内容（白名单策略）。

    - 图片、音频、视频等非文本内容仅保留 type="text" 部分
    - 过滤掉 reasoning_content / think blocks（不进入总结输入）
    - 非文本部分替换为占位说明
    - tool 消息保留其 snip 后的文本内容（与 assistant tool_calls 成对进入总结）
    """
    filtered: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")

        new_msg: dict[str, Any] = {"role": role}

        if isinstance(content, str):
            new_msg["content"] = content
        elif isinstance(content, list):
            # 多模态内容列表——白名单：仅保留 text
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text")
                    if isinstance(text, str):
                        text_parts.append(text)
            if text_parts:
                new_msg["content"] = "\n".join(text_parts)
            else:
                # 无可提取文本内容，用占位符
                new_msg["content"] = f"[{role} message with non-text content]"
        elif content is None and role == "assistant" and msg.get("tool_calls"):
            # assistant 消息只有 tool_calls 没有 content
            new_msg["content"] = "[assistant made tool calls]"
        else:
            new_msg["content"] = str(content) if content is not None else ""

        # 不保留 reasoning_content（过滤 ThinkPart）
        filtered.append(new_msg)

    return filtered


def _format_messages_for_summary(messages: list[dict[str, Any]]) -> str:
    """将消息列表格式化为适合 LLM 总结的文本。"""
    parts: list[str] = []
    for i, msg in enumerate(messages):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        parts.append(f"## Message {i + 1}\nRole: {role}\nContent:\n{content}\n")
    return "\n".join(parts)


# 压缩验证 Probe：启发式检查关键信息是否丢失
_ERROR_KEYWORDS = {
    "error", "exception", "failed", "traceback", "assertionerror",
    "runtimeerror", "valueerror", "typeerror", "keyerror", "indexerror",
    "syntaxerror", "importerror", "modulenotfounderror", "oserror",
}


def _verify_compaction_heuristic(
    original_messages: list[dict[str, Any]],
    summary: str,
) -> tuple[bool, list[str]]:
    """启发式验证压缩摘要是否丢失了关键信息。

    Returns:
        (is_valid, list of issue descriptions)
    """
    import re

    issues: list[str] = []
    original_text = _format_messages_for_summary(original_messages).lower()
    summary_lower = summary.lower()

    # 检查错误关键词
    missing_errors = [
        kw for kw in _ERROR_KEYWORDS
        if kw in original_text and kw not in summary_lower
    ]
    if missing_errors:
        issues.append(f"摘要可能遗漏错误信息（关键词: {', '.join(missing_errors[:3])}）")

    # 检查代码文件引用（简单模式匹配常见代码文件扩展名）
    file_pattern = re.compile(r'[\w/\\.-]+\.(py|js|ts|tsx|jsx|java|go|rs|cpp|c|h|md|json|yaml|yml|toml)')
    original_files = set(file_pattern.findall(original_text))
    summary_files = set(file_pattern.findall(summary_lower))
    missing_files = original_files - summary_files
    if missing_files:
        issues.append(f"摘要可能遗漏文件引用: {', '.join(sorted(missing_files)[:5])}")

    # 检查 TODO / FIXME / BUG / HACK 等标记
    marker_pattern = re.compile(r'\b(todo|fixme|bug|hack|xxx|note)\b', re.IGNORECASE)
    original_markers = set(marker_pattern.findall(original_text))
    summary_markers = set(marker_pattern.findall(summary_lower))
    missing_markers = original_markers - summary_markers
    if missing_markers:
        issues.append(f"摘要可能遗漏标记: {', '.join(sorted(missing_markers))}")

    return len(issues) == 0, issues


def _is_retryable_error(exc: BaseException) -> bool:
    """判断异常是否值得重试。

    重试规则：
    - 连接错误、超时
    - HTTP 429 (Rate Limit)
    - HTTP 500/502/503/504 (Server Error)
    """
    import urllib.error

    if isinstance(exc, (urllib.error.URLError, ConnectionError, TimeoutError)):
        return True

    # 处理 openai / httpx 的异常（通过 duck typing 检测）
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code in (429, 500, 502, 503, 504)

    # 某些 SDK 把状态码放在 response.status_code
    response = getattr(exc, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            return status_code in (429, 500, 502, 503, 504)

    return False


async def _call_llm_with_retry(
    client: BaseLlmClient,
    messages: list[dict[str, Any]],
    max_tokens: int,
    max_retries: int = 3,
) -> tuple[str, int | None]:
    """调用 LLM 生成摘要，带指数退避重试。

    Returns:
        (summary_text, usage_output_tokens)

    Raises:
        最后一次异常（如果所有重试都失败）。
    """
    summary_text = ""
    usage_output_tokens: int | None = None

    for attempt in range(max_retries):
        summary_text = ""
        usage_output_tokens = None
        try:
            async for chunk in client.chat_stream(
                messages,
                tools=None,
                temperature=0.3,
                max_tokens=max_tokens,
            ):
                if chunk.delta.content:
                    summary_text += chunk.delta.content
                if chunk.usage is not None:
                    output = chunk.usage.get("completion_tokens")
                    if output is None:
                        output = chunk.usage.get("output_tokens")
                    if isinstance(output, int):
                        usage_output_tokens = output
            return summary_text, usage_output_tokens
        except Exception as exc:
            if attempt == max_retries - 1 or not _is_retryable_error(exc):
                raise
            delay = min(0.3 * (2**attempt) + random.uniform(0, 0.5), 5.0)
            logger.warning(
                "Compaction LLM call failed (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                max_retries,
                delay,
                exc,
            )
            await asyncio.sleep(delay)

    # Should never reach here, but satisfy type checker
    return summary_text, usage_output_tokens


@dataclass
class CompactionResult:
    """压缩结果。"""

    messages: list[dict[str, Any]]
    """压缩后的完整消息列表。"""
    summary: str
    """生成的摘要文本。"""
    compacted_count: int
    """被压缩（替换为摘要）的消息数量。"""
    preserved_count: int
    """被保留的原样消息数量。"""
    usage_output_tokens: int | None = None
    """LLM 生成摘要时的输出 token 数（如有）。"""

    def estimated_token_count(self) -> int:
        """估算压缩后消息列表的 token 数。

        当 usage 可用时，摘要部分使用精确值，保留部分使用字符估算。
        当 usage 不可用时，全部使用字符估算。
        """
        if self.usage_output_tokens is not None and len(self.messages) > 0:
            preserved_tokens = estimate_text_tokens(self.messages[1:])
            return self.usage_output_tokens + preserved_tokens
        return estimate_text_tokens(self.messages)


class SimpleCompaction:
    """简单的历史消息压缩器。

    策略：
    - 保留最近 N 条 user/assistant 消息（原样，含多模态内容）
    - 其余消息发给 LLM 生成结构化摘要
    - 压缩后历史：[user: compaction notice + summary] + [preserved messages]
    - 总结输入中仅保留 TextPart（白名单过滤）
    """

    def __init__(
        self,
        max_preserved_messages: int = 2,
        max_summary_tokens: int = 2000,
        max_snip_chars: int = _DEFAULT_SNIP_MAX_CHARS,
    ) -> None:
        self.max_preserved_messages = max_preserved_messages
        self.max_summary_tokens = max_summary_tokens
        self.max_snip_chars = max_snip_chars

    def _select_preserved(
        self, messages: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """选择要保留的消息和要压缩的消息。

        从后往前数，保留最近 N 条 user/assistant 消息。
        返回 (to_compact, to_preserve)。
        """
        if not messages or self.max_preserved_messages <= 0:
            return messages, []

        history = list(messages)
        preserve_start_index = len(history)
        n_preserved = 0

        for index in range(len(history) - 1, -1, -1):
            if history[index].get("role") in {"user", "assistant"}:
                n_preserved += 1
                if n_preserved == self.max_preserved_messages:
                    preserve_start_index = index
                    break

        if n_preserved < self.max_preserved_messages:
            # 消息总数不足 N 条 user/assistant，不压缩
            return [], messages

        to_compact = history[:preserve_start_index]
        to_preserve = history[preserve_start_index:]
        return to_compact, to_preserve

    async def compact(
        self,
        messages: list[dict[str, Any]],
        client: BaseLlmClient,
        *,
        custom_instruction: str = "",
        enable_verification: bool = False,
    ) -> CompactionResult:
        """执行压缩。

        Args:
            messages: 完整消息列表。
            client: LLM client，用于生成摘要。
            custom_instruction: 可选的用户自定义压缩指令。

        Returns:
            CompactionResult: 压缩后的消息列表。如果无需压缩（消息不足），返回原列表。
        """
        to_compact, to_preserve = self._select_preserved(messages)

        if not to_compact:
            return CompactionResult(
                messages=list(messages),
                summary="",
                compacted_count=0,
                preserved_count=len(messages),
            )

        # 双层压缩第一层：snip 截断长内容（尤其是 tool 返回的大量数据）
        snipped = snip_messages_for_compaction(to_compact, max_chars=self.max_snip_chars)
        # 第二层：白名单过滤非文本内容（图片、think blocks 等）
        filtered = filter_messages_for_compaction(snipped)

        # 构建总结输入
        messages_text = _format_messages_for_summary(filtered)
        user_prompt = _COMPACTION_USER_PROMPT_TEMPLATE.format(messages_text=messages_text)
        if custom_instruction:
            user_prompt += (
                "\n\n**User's Custom Compaction Instruction:**\n"
                "The user has specifically requested the following focus during compaction. "
                "You MUST prioritize this instruction above the default compression priorities:\n"
                f"{custom_instruction}"
            )

        summary_messages = [
            {"role": "system", "content": _COMPACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        # 调用 LLM 生成摘要（流式聚合 + 指数退避重试）
        try:
            summary_text, usage_output_tokens = await _call_llm_with_retry(
                client,
                summary_messages,
                max_tokens=self.max_summary_tokens,
                max_retries=3,
            )
        except Exception as exc:
            logger.warning("LLM 摘要生成失败（重试耗尽），跳过压缩: %s", exc)
            return CompactionResult(
                messages=list(messages),
                summary="",
                compacted_count=0,
                preserved_count=len(messages),
            )

        # 构建压缩后的消息列表
        # 摘要放在 user 角色消息中
        compacted_messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    "Previous context has been compacted. "
                    "Here is the compaction output:\n\n" + summary_text
                ),
            }
        ]
        # 保留消息也清理多模态内容（图片/音频/视频等），避免 base64 长期膨胀
        sanitized_preserve = [_strip_multimodal_content(m) for m in to_preserve]
        # 对保留窗口内过长的 tool 消息做截断
        if self.max_snip_chars > 0:
            sanitized_preserve = [
                _snip_tool_message(m, self.max_snip_chars) for m in sanitized_preserve
            ]
        compacted_messages.extend(sanitized_preserve)

        # 可选：验证 Probe
        if enable_verification and summary_text:
            is_valid, issues = _verify_compaction_heuristic(to_compact, summary_text)
            if not is_valid:
                logger.warning(
                    "压缩摘要验证发现潜在问题: %s",
                    "; ".join(issues),
                )
            else:
                logger.debug("压缩摘要验证通过")

        logger.info(
            "Context compacted: %d messages -> summary + %d preserved",
            len(to_compact),
            len(to_preserve),
        )

        return CompactionResult(
            messages=compacted_messages,
            summary=summary_text,
            compacted_count=len(to_compact),
            preserved_count=len(to_preserve),
            usage_output_tokens=usage_output_tokens,
        )
