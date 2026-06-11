"""Session context compaction mixin。

从 session.py 提取的 _maybe_compact_context 与 _resolve_max_context_size。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.agent.compaction import (
    SimpleCompaction,
    clear_old_tool_results,
    estimate_text_tokens,
)
from app.services.agent.runtime_backends.aiasys.llm_clients import create_llm_client

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

    async def _maybe_compact_context(self) -> None:
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

        # 触发条件只基于 chat_messages（system messages 不参与压缩），
        # _estimated_token_count 若包含 system 需扣除其估算值。
        token_count = estimate_text_tokens(chat_messages)
        if self._estimated_token_count > 0:
            system_tokens = estimate_text_tokens(system_messages)
            token_count = max(
                token_count,
                self._estimated_token_count - system_tokens,
            )

        trigger_reason = ""
        if token_count >= max_context_size * loop_control.compaction_trigger_ratio:
            trigger_reason += "ratio"
        if (
            loop_control.reserved_context_size > 0
            and token_count + loop_control.reserved_context_size >= max_context_size
        ):
            trigger_reason += ("+" if trigger_reason else "") + "reserved"

        if not trigger_reason:
            return

        before_count = len(chat_messages)
        before_tokens = token_count
        start_time = time.perf_counter()

        # Tier 2+3: LLM-based compaction
        compactor = SimpleCompaction(
            max_preserved_messages=loop_control.max_preserved_messages,
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

        try:
            result = await compactor.compact(
                chat_messages,
                compaction_client,
                enable_verification=loop_control.enable_compaction_verification,
            )
        except Exception as exc:
            logger.warning("上下文压缩失败，跳过: %s", exc)
            return
        finally:
            if compaction_client is not self._client:
                try:
                    await compaction_client.aclose()
                except Exception:
                    pass

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

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

            self._insert_compaction_notice(
                tier_used="llm_summary",
                compacted_count=result.compacted_count,
                tokens_before=before_tokens,
                tokens_after=after_tokens_est,
            )

            self.messages = system_messages + compacted_messages
            self._estimated_token_count = after_tokens_est
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

    def _resolve_max_context_size(self) -> int:
        model_config = self._model_config
        if model_config is None:
            return 0
        max_context = _read_config_value(model_config, "max_context_size")
        if isinstance(max_context, int) and max_context > 0:
            return max_context
        return 0
