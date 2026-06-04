"""Session context compaction mixin。

从 session.py 提取的 _maybe_compact_context 与 _resolve_max_context_size。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.services.agent.compaction import SimpleCompaction, estimate_text_tokens
from app.services.agent.runtime_backends.aiasys.llm_clients import create_llm_client

logger = logging.getLogger(__name__)


def _read_config_value(config: Any, field_name: str) -> Any:
    if isinstance(config, dict):
        return config.get(field_name)
    return getattr(config, field_name, None)


class SessionCompactionMixin:
    """上下文压缩方法，供 AiasysRuntimeSession 混入。"""

    async def _maybe_compact_context(self) -> None:
        loop_control = self._spec.config.loop_control
        max_context_size = self._resolve_max_context_size()
        if max_context_size <= 0:
            return

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
            result = await compactor.compact(chat_messages, compaction_client)
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

            self.messages = system_messages + compacted_messages
            self._estimated_token_count = result.estimated_token_count()
            if restored_task_context:
                self._estimated_token_count += estimate_text_tokens(
                    [{"role": "user", "content": restored_task_context}]
                )
            # 压缩前 _estimated_token_count 包含 system messages（通过 _append_message
            # 累加或 LLM usage 精确值），压缩后必须保持语义一致。
            self._estimated_token_count += estimate_text_tokens(system_messages)
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

    def _resolve_max_context_size(self) -> int:
        model_config = self._model_config
        if model_config is None:
            return 0
        max_context = _read_config_value(model_config, "max_context_size")
        if isinstance(max_context, int) and max_context > 0:
            return max_context
        return 0
