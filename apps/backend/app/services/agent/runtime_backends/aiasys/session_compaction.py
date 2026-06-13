"""Session context compaction mixin。

从 session.py 提取的 _maybe_compact_context 与 _resolve_max_context_size。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from collections.abc import AsyncGenerator

from app.services.agent.compaction import (
    CompactionResult,
    SimpleCompaction,
    clear_old_tool_results,
    estimate_text_tokens,
)
from app.services.agent.runtime_backends.aiasys.llm_clients import create_llm_client
from app.services.agent.runtime_backends.base import AgentRuntimeEvent

logger = logging.getLogger(__name__)


def _read_config_value(config: Any, field_name: str) -> Any:
    if isinstance(config, dict):
        return config.get(field_name)
    return getattr(config, field_name, None)


class SessionCompactionMixin:
    """上下文压缩方法，供 AiasysRuntimeSession 混入。"""

    def __init__(self):
        self._last_compaction_event: dict[str, Any] | None = None

    def _run_pre_turn_clearing(self) -> tuple[int, int]:
        """Tier 1: 每次 LLM 调用前执行零成本 tool 结果清理。

        直接修改 self.messages，返回 (cleared_count, saved_chars)。
        幂等：对已经清理过的占位符不会重复处理。
        """
        loop_control = self._spec.config.loop_control
        if not loop_control.enable_pre_turn_clearing:
            return 0, 0

        cleared_messages, cleared_count, saved_chars = clear_old_tool_results(
            self.messages,
            keep_recent_turns=loop_control.keep_tool_context_turns,
        )
        if cleared_count > 0:
            self.messages = cleared_messages
            logger.info(
                "Tier 1 tool clearing: %d tool messages cleared, ~%d chars saved",
                cleared_count,
                saved_chars,
            )
        return cleared_count, saved_chars

    async def _maybe_compact_context(
        self, *, force: bool = False
    ) -> AsyncGenerator[AgentRuntimeEvent, None]:
        loop_control = self._spec.config.loop_control
        max_context_size = self._resolve_max_context_size()
        if max_context_size <= 0:
            return

        # Tier 1: pre-turn clearing（零成本，幂等）
        # 在阈值判断前先清理，避免旧 tool 结果干扰触发决策
        self._run_pre_turn_clearing()

        system_messages: list[dict[str, Any]] = []
        chat_messages: list[dict[str, Any]] = []
        for msg in self.messages:
            if msg.get("role") == "system":
                system_messages.append(msg)
            else:
                chat_messages.append(msg)

        if not chat_messages:
            return

        # 触发条件基于 effective_token_count，它包含 _estimated_token_count
        # 和自上次 usage 修正以来追加消息的 pending 估算，比单纯估算更准确。
        # system messages 虽不参与压缩，但也占用上下文窗口，因此保留在计数中。
        estimated = getattr(self, "_estimated_token_count", 0) or 0
        pending = getattr(self, "_pending_token_estimate", 0) or 0
        token_count = max(0, estimated + pending)

        trigger_reason = ""
        if token_count >= max_context_size * loop_control.compaction_trigger_ratio:
            trigger_reason += "ratio"
        if (
            loop_control.reserved_context_size > 0
            and token_count + loop_control.reserved_context_size >= max_context_size
        ):
            trigger_reason += ("+" if trigger_reason else "") + "reserved"

        if not trigger_reason and not force:
            return

        before_count = len(chat_messages)
        before_tokens = token_count
        start_time = time.perf_counter()

        # Tier 2+3: LLM-based compaction
        compactor = SimpleCompaction(
            max_preserved_messages=loop_control.max_preserved_messages,
            max_preserved_tokens=loop_control.max_preserved_tokens,
            max_summary_tokens=loop_control.max_summary_tokens,
            max_snip_chars=loop_control.tool_snip_max_chars,
        )

        compaction_client = self._client
        compaction_model_id = self._spec.config.task_models.get("compaction")
        if compaction_model_id:
            available_models = set(self._spec.config.models.keys())
            if compaction_model_id not in available_models:
                logger.warning(
                    "task_models.compaction 配置的模型 '%s' 不存在，可用模型: %s",
                    compaction_model_id,
                    available_models,
                )
            else:
                model_cfg = self._spec.config.models.get(compaction_model_id)
                if model_cfg and model_cfg.provider:
                    provider_cfg = self._spec.config.providers.get(model_cfg.provider)
                    if provider_cfg:
                        try:
                            compaction_client = create_llm_client(
                                provider_cfg, model_cfg.model or compaction_model_id
                            )
                            logger.info(
                                "压缩使用专用模型: %s (%s)",
                                compaction_model_id,
                                model_cfg.model or compaction_model_id,
                            )
                        except Exception as exc:
                            logger.warning(
                                "创建压缩专用模型 client 失败，fallback 到主模型: %s", exc
                            )
                            compaction_client = self._client

        # 通知前端压缩开始
        yield AgentRuntimeEvent(kind="compaction", phase="begin")

        result: CompactionResult | None = None
        try:
            result = await compactor.compact(
                chat_messages,
                compaction_client,
                enable_verification=loop_control.enable_compaction_verification,
            )
            # 压缩未产生任何结果且当前已非常接近上限，尝试兜底裁剪后再压一次
            if (
                result.compacted_count == 0
                and token_count >= max_context_size * 0.95
            ):
                trimmed = self._fallback_trim_head(
                    chat_messages,
                    target_tokens=int(max_context_size * 0.8),
                )
                if len(trimmed) < len(chat_messages):
                    result = await compactor.compact(
                        trimmed,
                        compaction_client,
                        enable_verification=loop_control.enable_compaction_verification,
                    )
        except Exception as exc:
            logger.warning("上下文压缩失败: %s", exc)
            # 尝试兜底裁剪后再压一次
            trimmed = self._fallback_trim_head(
                chat_messages,
                target_tokens=int(max_context_size * 0.8),
            )
            if len(trimmed) < len(chat_messages):
                try:
                    result = await compactor.compact(
                        trimmed,
                        compaction_client,
                        enable_verification=loop_control.enable_compaction_verification,
                    )
                except Exception as exc2:
                    logger.warning("兜底裁剪后压缩仍失败: %s", exc2)
        finally:
            if compaction_client is not self._client:
                try:
                    await compaction_client.aclose()
                except Exception:
                    pass

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        if result is None:
            return

        apply_compaction = False
        after_tokens_est = 0
        compacted_messages: list[dict[str, Any]] = []
        summary_tokens = 0

        if result.compacted_count > 0:
            restored_task_context: str | None = None
            try:
                from pathlib import Path

                from app.services.session import SessionTaskPlanStore

                restored_task_context = SessionTaskPlanStore(
                    Path(str(self._spec.work_dir))
                ).build_active_task_context()
            except Exception:
                logger.debug("构建压缩后的活跃 task 上下文失败，已跳过", exc_info=True)

            compacted_messages = list(result.messages)
            if restored_task_context:
                compacted_messages.insert(
                    1 if compacted_messages else 0,
                    {"role": "user", "content": restored_task_context},
                )

            # 插入压缩提示
            after_tokens_est = result.estimated_token_count()
            if restored_task_context:
                after_tokens_est += estimate_text_tokens(
                    [{"role": "user", "content": restored_task_context}]
                )
            after_tokens_est += estimate_text_tokens(system_messages)

            # 补上 _context_messages（memory + AGENTS.md）的 token，
            # 这些内容每次调用都通过 _messages_for_model() 动态拼入。
            if self._context_messages:
                after_tokens_est += estimate_text_tokens(self._context_messages)

            # 反增检测：当待压缩内容足够大时，要求压缩后比压缩前至少低 5%，
            # 否则视为无效压缩。小上下文下摘要本身可能长于原文，不做强制要求。
            min_before_tokens = max(1000, loop_control.max_summary_tokens * 2)
            INCREASE_THRESHOLD = 0.95
            if before_tokens < min_before_tokens or after_tokens_est < before_tokens * INCREASE_THRESHOLD:
                apply_compaction = True
            else:
                logger.warning(
                    "上下文压缩被跳过：压缩后估算 token 数未显著减少 "
                    "(before=%d, after=%d)，放弃本次压缩以避免无效循环",
                    before_tokens,
                    after_tokens_est,
                )
                summary_tokens = result.usage_output_tokens or 0

        if apply_compaction:
            self._insert_compaction_notice(
                tier_used="llm_summary",
                compacted_count=result.compacted_count,
                tokens_before=before_tokens,
                tokens_after=after_tokens_est,
            )

            self.messages = system_messages + compacted_messages
            self._estimated_token_count = after_tokens_est
            # 压缩后的消息列表已是新的基准，清零 pending 估算。
            if hasattr(self, "_reset_pending_token_estimate"):
                self._reset_pending_token_estimate()
            else:
                self._pending_token_estimate = 0
            after_count = len(self.messages)
            after_tokens = self._estimated_token_count
            summary_tokens = result.usage_output_tokens or 0

            logger.info(
                "COMPACTION_METRICS "
                "trigger=%s before_msgs=%d before_tokens=%d "
                "after_msgs=%d after_tokens=%d summary_tokens=%d "
                "elapsed_ms=%d success=true",
                trigger_reason,
                before_count,
                before_tokens,
                after_count,
                after_tokens,
                summary_tokens,
                elapsed_ms,
            )
            logger.info(
                "Session %s context compacted: %d -> %d messages, estimated_tokens=%d",
                self.session_id,
                before_count,
                after_count,
                after_tokens,
            )

            self._last_compaction_event = {
                "tier_used": "llm_summary",
                "compacted_count": result.compacted_count,
                "preserved_count": result.preserved_count,
                "tokens_before": before_tokens,
                "tokens_after": after_tokens,
                "saved_tokens": before_tokens - after_tokens,
                "summary_tokens": summary_tokens,
                "elapsed_ms": elapsed_ms,
            }
            self._persist_compaction_summary(
                summary=result.summary,
                compacted_count=result.compacted_count,
                preserved_count=result.preserved_count,
                tokens_before=before_tokens,
                tokens_after=after_tokens,
            )
            self._invalidate_system_prompt_snapshot()

            # 通知前端压缩完成
            yield AgentRuntimeEvent(
                kind="compaction",
                phase="done",
                tokens_before=before_tokens,
                tokens_after=after_tokens,
                saved_tokens=max(0, before_tokens - after_tokens),
                summary_tokens=summary_tokens,
            )
        else:
            logger.info(
                "COMPACTION_METRICS "
                "trigger=%s before_msgs=%d before_tokens=%d "
                "after_msgs=%d after_tokens=%d summary_tokens=0 "
                "elapsed_ms=%d success=no_action",
                trigger_reason,
                before_count,
                before_tokens,
                before_count,
                before_tokens,
                elapsed_ms,
            )
            self._last_compaction_event = {
                "tier_used": "none",
                "compacted_count": 0,
                "preserved_count": before_count,
                "tokens_before": before_tokens,
                "tokens_after": before_tokens,
                "saved_tokens": 0,
                "elapsed_ms": elapsed_ms,
            }

            # 即使没有实际压缩，也通知前端结束 loading
            yield AgentRuntimeEvent(
                kind="compaction",
                phase="done",
                tokens_before=before_tokens,
                tokens_after=before_tokens,
                saved_tokens=0,
                summary_tokens=0,
            )

    def _insert_compaction_notice(
        self,
        *,
        tier_used: str,
        compacted_count: int,
        tokens_before: int,
        tokens_after: int,
    ) -> None:
        """在消息列表中插入一条压缩提示系统消息。"""
        saved = max(0, tokens_before - tokens_after)
        if tier_used == "tool_clear":
            notice = (
                f"[上下文已压缩] 清理了 {compacted_count} 条旧 tool 结果，"
                f"上下文从约 {tokens_before} tokens 降至约 {tokens_after} tokens"
                f"（节省约 {saved} tokens）。"
            )
        else:
            notice = (
                f"[上下文已压缩] 前 {compacted_count} 轮对话已总结为结构化摘要，"
                f"上下文从约 {tokens_before} tokens 降至约 {tokens_after} tokens"
                f"（节省约 {saved} tokens）。"
            )
        # 作为 system 消息插入，紧跟在 leading system 消息之后
        leading_system_count = 0
        for msg in self.messages:
            if msg.get("role") == "system":
                leading_system_count += 1
            else:
                break
        self.messages.insert(
            leading_system_count,
            {"role": "system", "content": notice},
        )

    def _persist_compaction_summary(
        self,
        summary: str,
        compacted_count: int,
        preserved_count: int,
        tokens_before: int,
        tokens_after: int,
    ) -> None:
        """将压缩摘要写入 session 目录，供用户查阅和调试。"""
        try:
            work_dir = Path(str(self._spec.work_dir))
            summary_dir = work_dir / ".aiasys" / "session" / "compaction_summaries"
            summary_dir.mkdir(parents=True, exist_ok=True)
            path = summary_dir / f"{int(time.time())}.md"
            path.write_text(
                f"# 上下文压缩摘要 ({datetime.now().isoformat()})\n\n"
                f"- 会话: {self.session_id}\n"
                f"- 压缩消息数: {compacted_count}\n"
                f"- 保留消息数: {preserved_count}\n"
                f"- 压缩前 tokens: {tokens_before}\n"
                f"- 压缩后 tokens: {tokens_after}\n"
                f"- 节省 tokens: {tokens_before - tokens_after}\n\n"
                f"---\n\n{summary}\n",
                encoding="utf-8",
            )
            logger.info("压缩摘要已持久化: %s", path)
        except Exception:
            logger.debug("压缩摘要持久化失败，已跳过", exc_info=True)

    def _fallback_trim_head(
        self,
        messages: list[dict[str, Any]],
        target_tokens: int,
        min_turns: int = 2,
    ) -> list[dict[str, Any]]:
        """兜底裁剪：当 LLM 压缩失败时，从历史最开头删除旧消息。

        保留最近至少 min_turns 个 user/assistant 轮次，删除其余开头的非 system 消息，
        直到总 token 估算不超过 target_tokens。不会删除 system 消息。
        """
        if not messages:
            return messages

        # 从后往前定位最近 min_turns 个 user/assistant 轮次的起始索引
        preserve_start_index = 0
        n_preserved = 0
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].get("role") in {"user", "assistant"}:
                n_preserved += 1
                if n_preserved == min_turns:
                    preserve_start_index = index
                    break

        # 从开头删除消息，直到满足 target_tokens
        trimmed = list(messages)
        while (
            len(trimmed) > preserve_start_index
            and estimate_text_tokens(trimmed) > target_tokens
        ):
            # 删除第一条非 system 消息；若第一条是 system，则删除第二条
            removed_index = 0
            if trimmed[0].get("role") == "system" and len(trimmed) > 1:
                removed_index = 1
            trimmed.pop(removed_index)

        if len(trimmed) < len(messages):
            logger.info(
                "上下文压缩 fallback trim: %d -> %d 条消息",
                len(messages),
                len(trimmed),
            )
        return trimmed

    def _resolve_max_context_size(self) -> int:
        """返回用于触发压缩判断的有效上下文窗口大小。

        对模型标称窗口应用 effective_context_window_percent 折扣，
        为系统提示、工具 schema 和模型输出留出余量。
        """
        model_config = self._model_config
        if model_config is None:
            return 0
        max_context = _read_config_value(model_config, "max_context_size")
        if not isinstance(max_context, int) or max_context <= 0:
            return 0
        loop_control = self._spec.config.loop_control
        percent = getattr(loop_control, "effective_context_window_percent", 95.0)
        if not isinstance(percent, (int, float)) or not (50.0 <= percent <= 100.0):
            percent = 95.0
        return int(max_context * percent / 100)
