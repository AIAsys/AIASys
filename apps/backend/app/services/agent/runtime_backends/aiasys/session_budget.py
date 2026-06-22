"""Session budget 管理 mixin。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.path_utils import as_system_path

logger = logging.getLogger(__name__)


class SessionBudgetMixin:
    """Budget lifecycle 方法，供 AiasysRuntimeSession 混入。"""

    def _load_budget(self) -> Any | None:
        try:
            from app.models.session import SessionMetadata

            meta_path = Path(self._spec.work_dir) / "metadata.json"
            sys_meta_path = as_system_path(str(meta_path))
            if not Path(sys_meta_path).exists():
                return None
            data = json.loads(Path(sys_meta_path).read_text(encoding="utf-8"))
            meta = SessionMetadata(**data)
            return meta.budget
        except Exception:
            return None

    def _load_saved_context_tokens(self) -> int | None:
        """从 metadata.json 顶层读取上次保存的精确 context_tokens。"""
        try:
            from app.models.session import SessionMetadata

            meta_path = Path(self._spec.work_dir) / "metadata.json"
            sys_meta_path = as_system_path(str(meta_path))
            if not Path(sys_meta_path).exists():
                return None
            data = json.loads(Path(sys_meta_path).read_text(encoding="utf-8"))
            meta = SessionMetadata(**data)
            value = getattr(meta, "context_tokens", 0) or 0
            return value if isinstance(value, int) and value > 0 else None
        except Exception:
            return None

    def _append_usage_record(
        self, usage: dict[str, Any] | None, input_tokens: int, output_tokens: int
    ) -> None:
        """追加一条 LLM 调用 token 消耗记录到 usage.jsonl。

        每条记录对应一次完整的 LLM API 调用，存储为 JSONL 行，
        用于后续聚合生成 Token 消耗贡献图等可视化。
        """
        try:
            model = self._resolve_model_id()
            model_config = getattr(self, "_model_config", None)
            provider = getattr(model_config, "provider", None) if model_config is not None else None
            if not provider:
                provider = model

            usage = usage or {}
            record = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "model": model,
                "provider": provider,
                "input": input_tokens,
                "output": output_tokens,
                "cache_read": usage.get("cache_read_input_tokens", 0) or 0,
                "cache_write": usage.get("cache_creation_input_tokens", 0) or 0,
                "reasoning": usage.get("reasoning_tokens", 0) or 0,
            }

            record_path = Path(str(self._spec.work_dir)) / ".aiasys" / "session" / "usage.jsonl"
            record_path.parent.mkdir(parents=True, exist_ok=True)
            with open(as_system_path(str(record_path)), "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            logger.debug("追加 usage record 失败", exc_info=True)

    async def _save_budget(self) -> None:
        if self.budget is None:
            return
        async with self._metadata_lock:
            self._do_save_budget()

    def _do_save_budget(self) -> None:
        try:
            from app.models.session import SessionMetadata

            meta_path = Path(self._spec.work_dir) / "metadata.json"
            sys_meta_path = as_system_path(str(meta_path))
            if not Path(sys_meta_path).exists():
                return
            data = json.loads(Path(sys_meta_path).read_text(encoding="utf-8"))
            meta = SessionMetadata(**data)
            meta.budget = self.budget
            Path(sys_meta_path).write_text(
                meta.model_dump_json(indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.warning("保存 budget 状态失败", exc_info=True)

    async def _save_context_tokens_to_metadata(self) -> None:
        """将当前上下文占用 token 数写入 metadata.json。

        同时写入 metadata 顶层 context_tokens 和 budget.context_tokens，
        保证 budget 关闭时也能恢复精确值，避免 session 重启后回退到严重偏高的启发式估算。
        LLM 返回精确 prompt_tokens 后调用。
        """
        try:
            from app.models.session import SessionMetadata

            async with self._metadata_lock:
                meta_path = Path(self._spec.work_dir) / "metadata.json"
                sys_meta_path = as_system_path(str(meta_path))
                if not Path(sys_meta_path).exists():
                    return
                data = json.loads(Path(sys_meta_path).read_text(encoding="utf-8"))
                meta = SessionMetadata(**data)
                estimated = getattr(self, "_estimated_token_count", 0) or 0
                if isinstance(estimated, int) and estimated > 0:
                    meta.context_tokens = estimated
                    if meta.budget is not None:
                        meta.budget.context_tokens = estimated
                Path(sys_meta_path).write_text(
                    meta.model_dump_json(indent=2),
                    encoding="utf-8",
                )
        except Exception:
            logger.warning("保存 context_tokens 到 metadata 失败", exc_info=True)

    async def _check_session_budget(self, input_tokens: int, output_tokens: int) -> None:
        delta = input_tokens + output_tokens

        if self.budget is not None and self.budget.status == "active":
            async with self._metadata_lock:
                self.budget.tokens_used += delta
                # 优先使用当前 LLM 调用返回的真实 input_tokens；
                # 若未返回，使用 effective_token_count（含 pending 估算）。
                estimated = getattr(self, "_estimated_token_count", 0) or 0
                pending = getattr(self, "_pending_token_estimate", 0) or 0
                effective = max(0, estimated + pending)
                self.budget.context_tokens = input_tokens or effective
                if self.budget.is_exhausted():
                    self.budget.status = "budget_limited"
                    logger.info(
                        "Session budget 耗尽: session=%s tokens_used=%d budget=%s",
                        self.session_id,
                        self.budget.tokens_used,
                        self.budget.token_budget,
                    )
                self._do_save_budget()

    async def _is_session_budget_blocked(self) -> bool:
        """返回当前 session 是否已经达到预算上限。"""
        if self.budget is None:
            return False
        if self.budget.status == "budget_limited":
            return True
        async with self._metadata_lock:
            if self.budget.is_exhausted():
                self.budget.status = "budget_limited"
                self._do_save_budget()
                return True
        return False

    def _session_budget_limited_text(self) -> str:
        if self.budget is None:
            return "当前会话预算已耗尽，本轮不会继续执行。"
        token_budget = self.budget.token_budget
        tokens_used = self.budget.tokens_used
        if token_budget is not None:
            return (
                "当前会话预算已耗尽，本轮不会继续执行。"
                f"已用 {tokens_used} / {token_budget} tokens。"
            )
        return "当前会话预算已耗尽，本轮不会继续执行。"
