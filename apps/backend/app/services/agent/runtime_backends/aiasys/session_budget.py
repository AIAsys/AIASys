"""Session budget 管理 mixin。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SessionBudgetMixin:
    """Budget lifecycle 方法，供 AiasysRuntimeSession 混入。"""

    def _load_budget(self) -> Any | None:
        try:
            from app.models.session import SessionMetadata

            meta_path = Path(self._spec.work_dir) / "metadata.json"
            if not meta_path.exists():
                return None
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            meta = SessionMetadata(**data)
            return meta.budget
        except Exception:
            return None

    def _save_budget(self) -> None:
        if self.budget is None:
            return
        with self._metadata_lock:
            self._do_save_budget()

    def _do_save_budget(self) -> None:
        try:
            from app.models.session import SessionMetadata

            meta_path = Path(self._spec.work_dir) / "metadata.json"
            if not meta_path.exists():
                return
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            meta = SessionMetadata(**data)
            meta.budget = self.budget
            meta_path.write_text(
                meta.model_dump_json(indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.warning("保存 budget 状态失败", exc_info=True)

    def _save_context_tokens_to_metadata(self) -> None:
        """将当前上下文占用 token 数独立写入 metadata.json。

        与预算是否开启无关。LLM 返回精确 prompt_tokens 后调用，
        确保 session 关闭后 API 查询不回退到启发式估算。
        """
        try:
            from app.models.session import SessionBudget, SessionMetadata

            meta_path = Path(self._spec.work_dir) / "metadata.json"
            if not meta_path.exists():
                return
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            meta = SessionMetadata(**data)
            if meta.budget is None:
                meta.budget = SessionBudget()
            estimated = getattr(self, "_estimated_token_count", 0) or 0
            if isinstance(estimated, int) and estimated > 0:
                meta.budget.context_tokens = estimated
            meta_path.write_text(
                meta.model_dump_json(indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.warning("保存 context_tokens 到 metadata 失败", exc_info=True)

    def _check_session_budget(self, input_tokens: int, output_tokens: int) -> None:
        delta = input_tokens + output_tokens

        if self.budget is not None and self.budget.status == "active":
            with self._metadata_lock:
                self.budget.tokens_used += delta
                self.budget.context_tokens = (
                    getattr(self, "_estimated_token_count", 0) or input_tokens
                )
                if self.budget.is_exhausted():
                    self.budget.status = "budget_limited"
                    logger.info(
                        "Session budget 耗尽: session=%s tokens_used=%d budget=%s",
                        self.session_id,
                        self.budget.tokens_used,
                        self.budget.token_budget,
                    )
                self._do_save_budget()

    def _is_session_budget_blocked(self) -> bool:
        """返回当前 session 是否已经达到预算上限。"""
        if self.budget is None:
            return False
        if self.budget.status == "budget_limited":
            return True
        with self._metadata_lock:
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
