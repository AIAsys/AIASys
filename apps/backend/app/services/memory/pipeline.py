"""Memory 两阶段 Pipeline 的基础服务。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.config import get_user_global_memory_dir
from app.services.agent.models.llm_config import LlmModelConfig, LlmProviderConfig
from app.services.agent.runtime_backends.aiasys.llm_clients import create_llm_client
from app.services.history.session_execution_journal import SessionExecutionJournal
from app.services.llm import get_llm_config_service
from app.services.memory.constants import (
    CAPACITY_CRITICAL_PCT,
    CAPACITY_WARNING_PCT,
    MAX_MEMORY_SIZE,
    MAX_SUMMARY_SIZE,
    MAX_WORKSPACE_MEMORY_SIZE,
    USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
    is_user_default_global_workspace_scope,
    normalize_memory_scope_key,
)
from app.services.memory.layout import MemoryLayout, ensure_memory_layout
from app.services.memory.resolver import (
    get_workspace_memory_file_path,
    get_workspace_memory_summary_file_path,
    invalidate_user_resolver_cache,
)
from app.services.memory.state_runtime import (
    MemoryStateRuntime,
    Stage1JobClaim,
    Stage1OutputRecord,
)
from app.services.memory.store import MemoryCapacityError, MemorySecurityError, MemoryStore
from app.utils.path_utils import as_system_path

logger = logging.getLogger(__name__)

STATE_DB_FILE_NAME = "state.db"

# 以下默认值在 _get_memory_config 中作为 fallback，用户可通过 config.toml [memory] 段覆盖
_DEFAULT_STAGE1_MAX_RECORDS = 20
_DEFAULT_STAGE1_MAX_CHARS = 12000
_DEFAULT_STAGE1_SUMMARY_TOKENS = 1800


def _get_memory_config(user_id: str):
    """读取用户 config.toml 中的 [memory] 配置段，文件不存在时返回默认值。"""
    from app.core.aiasys_config import load_aiasys_config

    return load_aiasys_config(user_id).memory


def _deep_truncate_strings(value: Any, max_len: int = 4000) -> Any:
    """递归截断字典/列表中的长字符串，在 json.dumps 前控制总长度。"""
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len].rstrip() + "\n...（内容已截断）"
    if isinstance(value, list):
        return [_deep_truncate_strings(v, max_len) for v in value]
    if isinstance(value, dict):
        return {k: _deep_truncate_strings(v, max_len) for k, v in value.items()}
    return value


def _safe_truncate_prompt_text(text: str, max_chars: int) -> str:
    """安全截断 prompt 文本，优先在换行符处截断，避免截断在 token 中间。

    返回结果的总长度（含后缀）保证不超过 max_chars。
    当 max_chars 不足以容纳完整后缀时，退化为省略号。
    """
    if len(text) <= max_chars:
        return text
    SUFFIX = "\n\n...（以上内容已截断）"
    MIN_SUFFIX = "..."
    effective_max = max_chars - len(SUFFIX)
    if effective_max <= 0:
        # max_chars 不足以容纳完整后缀，退化为省略号
        truncated = text[: max(1, max_chars - len(MIN_SUFFIX))]
        truncated = truncated.rstrip()
        return truncated + MIN_SUFFIX
    truncated = text[:effective_max]
    # 尝试在最近的换行符截断，至少保留 50% 内容
    last_nl = truncated.rfind("\n")
    if last_nl > effective_max * 0.5:
        truncated = truncated[:last_nl]
    truncated = truncated.rstrip()
    return truncated + SUFFIX


def get_memory_state_runtime(
    db_path: Path | None = None,
    *,
    user_id: str = "local_default",
) -> MemoryStateRuntime:
    """返回用户默认层 memory state runtime。"""

    return MemoryStateRuntime(db_path or get_user_global_memory_dir(user_id) / STATE_DB_FILE_NAME)


def _stable_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "-", value).strip("-")
    cleaned = cleaned[:48].strip("-")
    return cleaned or "session-memory"


class MemoryPipelineService:
    """封装 Stage 1/Stage 2 状态和 Markdown 镜像写入。"""

    def __init__(
        self,
        runtime: MemoryStateRuntime | None = None,
        *,
        user_id: str = "local_default",
        workspace_root_resolver: Callable[[str, str], Path] | None = None,
    ):
        self.runtime = runtime or get_memory_state_runtime(user_id=user_id)
        self._workspace_root_resolver = workspace_root_resolver

    def claim_stage1_job(
        self,
        *,
        user_id: str,
        session_id: str,
        workspace_id: str | None = None,
        lease_seconds: int = 900,
        max_running_jobs: int = 2,
        now: int | None = None,
        worker_id: str | None = None,
    ) -> Stage1JobClaim:
        return self.runtime.claim_stage1_job(
            user_id=user_id,
            session_id=session_id,
            workspace_id=workspace_id,
            lease_seconds=lease_seconds,
            max_running_jobs=max_running_jobs,
            now=now,
            worker_id=worker_id,
        )

    def record_stage1_output(
        self,
        *,
        user_id: str,
        session_id: str,
        source_path: str,
        raw_memory: str,
        rollout_summary: str,
        rollout_slug: str | None = None,
        workspace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        now: int | None = None,
    ) -> Stage1OutputRecord:
        """写入 Stage 1 结果，并同步 raw/rollout Markdown 镜像。"""

        now = int(now if now is not None else time.time())
        slug_base = _stable_slug(rollout_slug or session_id)
        slug = f"{_stable_slug(workspace_id)}_{slug_base}" if workspace_id else slug_base
        record = self.runtime.write_stage1_output(
            user_id=user_id,
            session_id=session_id,
            workspace_id=workspace_id,
            source_path=source_path,
            raw_memory=raw_memory.strip(),
            rollout_summary=rollout_summary.strip(),
            rollout_slug=slug,
            metadata=metadata,
            now=now,
        )
        try:
            self._append_raw_memory_mirror(user_id=user_id, record=record)
            self._write_rollout_summary(user_id=user_id, record=record)
        except Exception:
            logger.warning(
                "Stage 1 镜像写入失败，回滚数据库记录: record_id=%s",
                record.id,
            )
            try:
                self.runtime.delete_stage1_output(record.id)
            except Exception as del_exc:
                logger.error("Stage 1 数据库回滚失败: %s", del_exc)
            raise
        return record

    def pending_consolidation_inputs(
        self,
        *,
        user_id: str,
        limit: int = 128,
        max_created_at: int | None = None,
        scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
    ) -> list[Stage1OutputRecord]:
        scope_key = normalize_memory_scope_key(scope_key)
        return self.runtime.list_pending_stage1_outputs(
            user_id=user_id,
            limit=limit,
            max_created_at=max_created_at,
            scope_key=scope_key,
        )

    def get_status(
        self,
        *,
        user_id: str,
        scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
    ) -> dict[str, Any]:
        """读取 memory pipeline 轻量状态。"""

        scope_key = normalize_memory_scope_key(scope_key)
        return self.runtime.get_pipeline_status(user_id=user_id, scope_key=scope_key)

    def apply_retention(
        self,
        *,
        user_id: str,
        keep_latest: int | None = None,
        max_age_days: int | None = None,
    ) -> dict[str, Any]:
        """清理 Stage 1 中间产物并重建 raw/rollout Markdown 镜像。"""

        config = _get_memory_config(user_id)
        keep_count = (
            keep_latest
            if keep_latest is not None
            else (config.max_stage1_outputs or _DEFAULT_STAGE1_MAX_RECORDS)
        )
        prune_result = self.runtime.prune_stage1_outputs_for_retention(
            user_id=user_id,
            keep_latest=keep_count,
            max_age_days=max_age_days or config.stage1_retention_days,
        )
        retained = self.runtime.list_stage1_outputs(
            user_id=user_id,
            limit=max(keep_count, 1) + int(prune_result["remaining_pending_count"]),
        )
        self._rebuild_stage1_markdown_mirrors(user_id=user_id, records=retained)
        return {
            **prune_result,
            "retained_count": len(retained),
            "keep_latest": keep_count,
            "max_age_days": max_age_days or config.stage1_retention_days,
        }

    def mark_consolidated(
        self,
        *,
        user_id: str,
        records: list[Stage1OutputRecord],
        memory_text: str,
        summary_text: str,
        scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
        now: int | None = None,
    ) -> None:
        """记录 Stage 2 水印。"""

        if not records:
            return
        scope_key = normalize_memory_scope_key(scope_key)
        input_watermark = max(record.created_at for record in records)
        self.runtime.update_consolidation_state(
            user_id=user_id,
            scope_key=scope_key,
            input_watermark=input_watermark,
            output_memory_hash=_content_hash(memory_text),
            output_summary_hash=_content_hash(summary_text),
            stage1_output_ids=[record.id for record in records],
            now=now,
        )
        config = _get_memory_config(user_id)
        self.runtime.prune_old_versions(
            user_id=user_id,
            scope_key=scope_key,
            keep_latest=config.max_memory_versions,
        )

    async def run_stage2_consolidation(
        self,
        *,
        user_id: str,
        limit: int = 128,
        lease_seconds: int = 900,
        scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
        force_consolidation: bool = False,
    ) -> int:
        """把待处理 Stage 1 产物落到 Markdown，并在需要时执行 consolidation。

        流程：
        1. 读取当前 scope 的待处理 Stage 1 records
        2. 预估追加后容量，决定追加还是先触发 consolidation
        3. consolidation 成功或追加成功后推进水印
        4. consolidation 失败且未追加时，不推进水印
        """

        scope_key = normalize_memory_scope_key(scope_key)
        records = self.pending_consolidation_inputs(
            user_id=user_id,
            limit=limit,
            scope_key=scope_key,
        )
        if not records:
            return 0

        claim = self.runtime.claim_stage2_job(
            user_id=user_id,
            scope_key=scope_key,
            lease_seconds=lease_seconds,
        )
        if claim.status != "claimed":
            return 0

        try:
            layout = ensure_memory_layout(get_user_global_memory_dir(user_id))
            memory_text = await asyncio.to_thread(
                self._read_scope_memory_text,
                user_id=user_id,
                scope_key=scope_key,
                layout=layout,
            )
            summary_text = await asyncio.to_thread(
                self._read_scope_summary_text,
                user_id=user_id,
                scope_key=scope_key,
                layout=layout,
            )

            workspace_root = (
                None
                if is_user_default_global_workspace_scope(scope_key)
                else self._resolve_workspace_root(user_id, scope_key)
            )
            capacity_info = await asyncio.to_thread(
                self.check_capacity,
                user_id=user_id,
                layout=layout,
                workspace_root=workspace_root,
            )
            projected_capacity_info = await asyncio.to_thread(
                self._project_stage2_append_capacity,
                user_id=user_id,
                records=records,
                scope_key=scope_key,
                capacity_info=capacity_info,
            )
            should_consolidate = force_consolidation or self._should_consolidate(
                records=records,
                capacity_info=projected_capacity_info,
            )

            appended = False
            consolidated = False
            if should_consolidate:
                try:
                    consolidated = await self._run_consolidation(
                        user_id=user_id,
                        layout=layout,
                        records=records,
                        scope_key=scope_key,
                    )
                    # consolidation 后重新读取
                    memory_text = await asyncio.to_thread(
                        self._read_scope_memory_text,
                        user_id=user_id,
                        scope_key=scope_key,
                        layout=layout,
                    )
                    summary_text = await asyncio.to_thread(
                        self._read_scope_summary_text,
                        user_id=user_id,
                        scope_key=scope_key,
                        layout=layout,
                    )
                except Exception as cons_exc:
                    logger.warning(
                        "Memory consolidation 失败: user=%s error=%s",
                        user_id,
                        cons_exc,
                        exc_info=True,
                    )
                    consolidated = False

                if not consolidated:
                    try:
                        await asyncio.to_thread(
                            self._append_stage2_records_to_markdown,
                            user_id=user_id,
                            records=records,
                            scope_key=scope_key,
                        )
                        appended = True
                        memory_text = await asyncio.to_thread(
                            self._read_scope_memory_text,
                            user_id=user_id,
                            scope_key=scope_key,
                            layout=layout,
                        )
                    except MemoryCapacityError:
                        if projected_capacity_info.get("hard_limit_exceeded"):
                            self.runtime.fail_stage2_job(
                                user_id=user_id,
                                scope_key=scope_key,
                                error="memory consolidation did not write output and append would exceed capacity",
                            )
                            return 0
                        raise
            else:
                await asyncio.to_thread(
                    self._append_stage2_records_to_markdown,
                    user_id=user_id,
                    records=records,
                    scope_key=scope_key,
                )
                appended = True
                memory_text = await asyncio.to_thread(
                    self._read_scope_memory_text,
                    user_id=user_id,
                    scope_key=scope_key,
                    layout=layout,
                )

            if not appended and not consolidated:
                self.runtime.fail_stage2_job(
                    user_id=user_id,
                    scope_key=scope_key,
                    error="memory consolidation skipped without append",
                )
                return 0

            self.mark_consolidated(
                user_id=user_id,
                records=records,
                memory_text=memory_text,
                summary_text=summary_text,
                scope_key=scope_key,
            )
            self.runtime.complete_stage2_job(user_id=user_id, scope_key=scope_key)
            invalidate_user_resolver_cache(user_id)
            return len(records)
        except Exception as exc:
            logger.warning(
                "Memory Stage 2 追加写入失败: user=%s error=%s",
                user_id,
                exc,
                exc_info=True,
            )
            self.runtime.fail_stage2_job(
                user_id=user_id,
                scope_key=scope_key,
                error=str(exc),
            )
            return 0

    def _read_scope_memory_text(
        self,
        *,
        user_id: str,
        scope_key: str,
        layout: MemoryLayout,
    ) -> str:
        scope_key = normalize_memory_scope_key(scope_key)
        if is_user_default_global_workspace_scope(scope_key):
            return (
                Path(as_system_path(layout.memory)).read_text(encoding="utf-8")
                if os.path.exists(as_system_path(layout.memory))
                else ""
            )
        workspace_root = self._resolve_workspace_root(user_id, scope_key)
        if workspace_root is None:
            return ""
        path = get_workspace_memory_file_path(workspace_root)
        return (
            Path(as_system_path(path)).read_text(encoding="utf-8")
            if os.path.exists(as_system_path(path))
            else ""
        )

    def _read_scope_summary_text(
        self,
        *,
        user_id: str,
        scope_key: str,
        layout: MemoryLayout,
    ) -> str:
        scope_key = normalize_memory_scope_key(scope_key)
        if is_user_default_global_workspace_scope(scope_key):
            return (
                Path(as_system_path(layout.summary)).read_text(encoding="utf-8")
                if os.path.exists(as_system_path(layout.summary))
                else ""
            )
        workspace_root = self._resolve_workspace_root(user_id, scope_key)
        if workspace_root is None:
            return ""
        path = get_workspace_memory_summary_file_path(workspace_root)
        return (
            Path(as_system_path(path)).read_text(encoding="utf-8")
            if os.path.exists(as_system_path(path))
            else ""
        )

    def check_capacity(
        self,
        *,
        user_id: str,
        layout: MemoryLayout | None = None,
        workspace_root: Path | None = None,
    ) -> dict[str, Any]:
        """返回 memory 容量状态。"""

        if layout is None:
            layout = ensure_memory_layout(get_user_global_memory_dir(user_id))

        memory_size = (
            len(Path(as_system_path(layout.memory)).read_text(encoding="utf-8"))
            if os.path.exists(as_system_path(layout.memory))
            else 0
        )
        summary_size = (
            len(Path(as_system_path(layout.summary)).read_text(encoding="utf-8"))
            if os.path.exists(as_system_path(layout.summary))
            else 0
        )

        memory_pct = memory_size / MAX_MEMORY_SIZE if MAX_MEMORY_SIZE > 0 else 0
        summary_pct = summary_size / MAX_SUMMARY_SIZE if MAX_SUMMARY_SIZE > 0 else 0

        workspace_size = 0
        workspace_pct = 0.0
        if workspace_root is not None:
            ws_path = get_workspace_memory_file_path(workspace_root)
            if os.path.exists(as_system_path(ws_path)):
                workspace_size = len(Path(as_system_path(ws_path)).read_text(encoding="utf-8"))
            workspace_pct = (
                workspace_size / MAX_WORKSPACE_MEMORY_SIZE if MAX_WORKSPACE_MEMORY_SIZE > 0 else 0
            )

        status = "ok"
        if memory_pct >= CAPACITY_CRITICAL_PCT or summary_pct >= CAPACITY_CRITICAL_PCT:
            status = "critical"
        elif memory_pct >= CAPACITY_WARNING_PCT or summary_pct >= CAPACITY_WARNING_PCT:
            status = "warning"

        return {
            "status": status,
            "memory": {
                "current": memory_size,
                "limit": MAX_MEMORY_SIZE,
                "percentage": round(memory_pct * 100, 1),
            },
            "summary": {
                "current": summary_size,
                "limit": MAX_SUMMARY_SIZE,
                "percentage": round(summary_pct * 100, 1),
            },
            "workspace": {
                "current": workspace_size,
                "limit": MAX_WORKSPACE_MEMORY_SIZE,
                "percentage": round(workspace_pct * 100, 1),
            },
        }

    def _should_consolidate(
        self,
        *,
        records: list[Stage1OutputRecord],
        capacity_info: dict[str, Any],
    ) -> bool:
        """判断是否应触发 consolidation。

        触发条件：
        - MEMORY.md 超过 80% 容量
        - 单次待处理 records >= 3
        - summary 超过 80% 容量
        """
        if capacity_info["status"] in ("warning", "critical"):
            return True
        if len(records) >= 3:
            return True
        return False

    def _project_stage2_append_capacity(
        self,
        *,
        user_id: str,
        records: list[Stage1OutputRecord],
        scope_key: str,
        capacity_info: dict[str, Any],
    ) -> dict[str, Any]:
        """预估 Stage 2 追加后的容量状态。"""

        scope_key = normalize_memory_scope_key(scope_key)
        projected = json.loads(json.dumps(capacity_info))
        config = _get_memory_config(user_id)
        if is_user_default_global_workspace_scope(scope_key):
            layout = ensure_memory_layout(get_user_global_memory_dir(user_id))
            existing = (
                Path(as_system_path(layout.memory)).read_text(encoding="utf-8").strip()
                if os.path.exists(as_system_path(layout.memory))
                else ""
            )
            blocks = [_format_stage2_append_block(record) for record in records]
            projected_text = (
                (
                    existing + "\n\n" + "## Stage 2 appended memories\n\n" + "\n\n".join(blocks)
                ).strip()
                if blocks
                else existing
            )
            limit = config.max_memory_size or MAX_MEMORY_SIZE
            projected["memory"]["current"] = len(projected_text)
            projected["memory"]["limit"] = limit
            projected["memory"]["percentage"] = round(
                (len(projected_text) / limit * 100) if limit > 0 else 0,
                1,
            )
            hard_exceeded = len(projected_text) > limit
        else:
            workspace_root = self._resolve_workspace_root(user_id, scope_key)
            existing = ""
            if workspace_root is not None:
                ws_path = get_workspace_memory_file_path(workspace_root)
                existing = (
                    Path(as_system_path(ws_path)).read_text(encoding="utf-8").strip()
                    if os.path.exists(as_system_path(ws_path))
                    else ""
                )
            blocks = [
                _format_stage2_append_block(record)
                for record in records
                if str(record.workspace_id or "").strip() == scope_key
            ]
            projected_text = (
                (
                    existing + "\n\n" + "## Stage 2 appended memories\n\n" + "\n\n".join(blocks)
                ).strip()
                if blocks
                else existing
            )
            limit = config.max_workspace_memory_size or MAX_WORKSPACE_MEMORY_SIZE
            projected["workspace"]["current"] = len(projected_text)
            projected["workspace"]["limit"] = limit
            projected["workspace"]["percentage"] = round(
                (len(projected_text) / limit * 100) if limit > 0 else 0,
                1,
            )
            hard_exceeded = len(projected_text) > limit

        percentages = [
            float(projected["memory"].get("percentage") or 0) / 100,
            float(projected["summary"].get("percentage") or 0) / 100,
            float(projected["workspace"].get("percentage") or 0) / 100,
        ]
        if hard_exceeded or any(p >= CAPACITY_CRITICAL_PCT for p in percentages):
            projected["status"] = "critical"
        elif any(p >= CAPACITY_WARNING_PCT for p in percentages):
            projected["status"] = "warning"
        else:
            projected["status"] = "ok"
        projected["hard_limit_exceeded"] = hard_exceeded
        return projected

    def _load_consolidation_inputs_sync(
        self,
        layout: MemoryLayout,
        target_memory_path: Path,
        target_summary_path: Path,
        records: list[Stage1OutputRecord],
    ) -> tuple[str, str, str, list[str]]:
        """在线程中读取 consolidation 所需的全部文件内容。"""
        current_memory = (
            Path(as_system_path(target_memory_path)).read_text(encoding="utf-8")
            if os.path.exists(as_system_path(target_memory_path))
            else ""
        )
        current_summary = (
            Path(as_system_path(target_summary_path)).read_text(encoding="utf-8")
            if os.path.exists(as_system_path(target_summary_path))
            else ""
        )
        raw_memories = (
            Path(as_system_path(layout.raw_memories)).read_text(encoding="utf-8")
            if os.path.exists(as_system_path(layout.raw_memories))
            else ""
        )

        rollout_texts: list[str] = []
        for record in records:
            rollout_path = layout.rollout_summaries / f"{record.rollout_slug}.md"
            if os.path.exists(as_system_path(rollout_path)):
                rollout_texts.append(Path(as_system_path(rollout_path)).read_text(encoding="utf-8"))

        return current_memory, current_summary, raw_memories, rollout_texts

    def _write_consolidation_outputs_sync(
        self,
        target_memory_path: Path,
        target_summary_path: Path,
        new_memory: str,
        new_summary: str | None,
        target_memory_limit: int,
    ) -> None:
        """在线程中完成 consolidation 结果的原子写入，走 MemoryStore 安全扫描与容量检查。"""
        memory_store = MemoryStore(target_memory_path)
        memory_store.initialize()
        memory_store.write_text(new_memory, max_size=target_memory_limit)

        if new_summary is not None:
            summary_store = MemoryStore(target_summary_path)
            summary_store.initialize()
            summary_store.write_text(new_summary, max_size=MAX_SUMMARY_SIZE)

    async def _run_consolidation(
        self,
        *,
        user_id: str,
        layout: MemoryLayout,
        records: list[Stage1OutputRecord],
        scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
    ) -> bool:
        """调用 LLM 整理 MEMORY.md 和 memory_summary.md，原子写入。"""

        scope_key = normalize_memory_scope_key(scope_key)
        client = _create_memory_llm_client(user_id)
        if client is None:
            logger.warning("Memory consolidation 跳过: 无可用 LLM client")
            return False

        target_memory_path = layout.memory
        target_summary_path = layout.summary
        target_memory_limit = MAX_MEMORY_SIZE
        if not is_user_default_global_workspace_scope(scope_key):
            workspace_root = self._resolve_workspace_root(user_id, scope_key)
            if workspace_root is None:
                raise ValueError(f"无法解析 workspace memory scope: {scope_key}")
            target_memory_path = get_workspace_memory_file_path(workspace_root)
            target_summary_path = get_workspace_memory_summary_file_path(workspace_root)
            target_memory_limit = MAX_WORKSPACE_MEMORY_SIZE

        # 读取输入
        current_memory, current_summary, raw_memories, rollout_texts = await asyncio.to_thread(
            self._load_consolidation_inputs_sync,
            layout,
            target_memory_path,
            target_summary_path,
            records,
        )

        config = _get_memory_config(user_id)
        prompt = _build_consolidation_prompt(
            current_memory=current_memory,
            current_summary=current_summary,
            raw_memories=raw_memories,
            rollout_texts=rollout_texts,
            records=records,
            max_input_chars=config.stage2_max_input_chars,
        )

        start_time = time.time()
        try:
            response_text = ""
            async for chunk in client.chat_stream(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是 AIASys Memory Consolidation Agent。"
                            "你的任务是从用户的长期记忆文件中提取高信号内容，删除低信号和重复内容，"
                            "重新组织成结构清晰的 Markdown。必须保留所有来源引用（session_id、rollout_slug）。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                tools=None,
                temperature=0.2,
                max_tokens=8192,
            ):
                if chunk.delta.content:
                    response_text += chunk.delta.content
        finally:
            try:
                await client.aclose()
            except Exception:
                pass

        if not response_text.strip():
            logger.warning("Memory consolidation 返回空响应，跳过写入")
            return False

        new_memory, new_summary = _parse_consolidation_response(response_text)

        if new_memory is None:
            logger.info("Memory consolidation 返回 no-op，跳过写入")
            return False

        # 截断保护
        if len(new_memory) > target_memory_limit:
            new_memory = _safe_truncate_prompt_text(new_memory, target_memory_limit)
        if new_summary and len(new_summary) > MAX_SUMMARY_SIZE:
            new_summary = _safe_truncate_prompt_text(new_summary, MAX_SUMMARY_SIZE)

        # 统一走 MemoryStore.write_text，经过安全扫描和容量检查
        try:
            await asyncio.to_thread(
                self._write_consolidation_outputs_sync,
                target_memory_path,
                target_summary_path,
                new_memory,
                new_summary,
                target_memory_limit,
            )
        except (MemorySecurityError, MemoryCapacityError) as exc:
            logger.error("Memory consolidation 写入失败: %s", exc)
            return False

        # 保存版本历史（失败不阻断 consolidation 成功）
        try:
            self.runtime.save_version(
                user_id=user_id,
                scope_key=scope_key,
                version_type="consolidation",
                source=records[0].session_id if records else None,
                memory_content=new_memory,
                summary_content=new_summary,
            )
        except Exception as save_err:
            logger.warning(
                "Memory version save 失败: user=%s error=%s",
                user_id,
                save_err,
                exc_info=True,
            )

        duration = time.time() - start_time
        logger.info(
            "Memory consolidation completed: user=%s input_records=%d "
            "output_memory_size=%d output_summary_size=%d duration=%.2fs",
            user_id,
            len(records),
            len(new_memory),
            len(new_summary) if new_summary else 0,
            duration,
        )
        return True

    async def run_stage1_for_session(
        self,
        *,
        user_id: str,
        session_id: str,
        session_dir: Path,
        workspace_id: str | None = None,
        lease_seconds: int = 900,
        max_running_jobs: int = 2,
    ) -> Stage1OutputRecord | None:
        """认领并执行单个 session 的 Stage 1 提炼。

        没有执行记录、租约未拿到或 LLM 调用失败时返回 None。失败会写回 job
        状态，但不会向普通对话路径抛错。
        """

        claim = self.claim_stage1_job(
            user_id=user_id,
            session_id=session_id,
            workspace_id=workspace_id,
            lease_seconds=lease_seconds,
            max_running_jobs=max_running_jobs,
        )
        if claim.status != "claimed":
            return None

        source_path = Path(session_dir) / ".aiasys" / "session" / "execution" / "records.jsonl"
        try:
            journal = SessionExecutionJournal(Path(session_dir), session_id)
            config = _get_memory_config(user_id)
            records = journal.list_records(limit=config.stage1_max_records)
            if not records:
                self.runtime.fail_stage1_job(
                    user_id=user_id,
                    session_id=session_id,
                    error="session has no execution journal records",
                )
                return None

            compacted = await self._summarize_records_with_llm(
                user_id=user_id,
                session_id=session_id,
                workspace_id=workspace_id,
                records=[record.model_dump(mode="json") for record in records],
            )
            if compacted is None:
                return None

            record = self.record_stage1_output(
                user_id=user_id,
                session_id=session_id,
                workspace_id=workspace_id,
                source_path=str(source_path),
                raw_memory=compacted["raw_memory"],
                rollout_summary=compacted["rollout_summary"],
                rollout_slug=compacted["rollout_slug"],
                metadata={
                    "record_count": len(records),
                    "worker_id": claim.worker_id,
                },
            )
            await self.run_stage2_consolidation(
                user_id=user_id,
                scope_key=workspace_id or USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
            )
            return record
        except Exception as exc:
            logger.warning(
                "Memory Stage 1 提炼失败: user=%s session=%s error=%s",
                user_id,
                session_id,
                exc,
                exc_info=True,
            )
            self.runtime.fail_stage1_job(
                user_id=user_id,
                session_id=session_id,
                error=str(exc),
            )
            return None

    async def _summarize_records_with_llm(
        self,
        *,
        user_id: str,
        session_id: str,
        workspace_id: str | None,
        records: list[dict[str, Any]],
    ) -> dict[str, str] | None:
        client = _create_memory_llm_client(user_id)
        if client is None:
            self.runtime.fail_stage1_job(
                user_id=user_id,
                session_id=session_id,
                error="no chat model configured for memory stage1",
            )
            return None

        try:
            prompt = _build_stage1_prompt(
                user_id=user_id,
                session_id=session_id,
                workspace_id=workspace_id,
                records=records,
            )
            summary_text = ""
            async for chunk in client.chat_stream(
                [
                    {
                        "role": "system",
                        "content": "你是 AIASys Memory Stage 1 提炼器，只输出可复用记忆草稿。",
                    },
                    {"role": "user", "content": prompt},
                ],
                tools=None,
                temperature=0.2,
                max_tokens=_get_memory_config(user_id).stage1_summary_tokens,
            ):
                if chunk.delta.content:
                    summary_text += chunk.delta.content
            summary_text = summary_text.strip()
            if not summary_text:
                summary_text = _fallback_record_summary(records)
            rollout_slug = f"{time.strftime('%Y-%m-%d')}-{session_id}"
            return {
                "raw_memory": summary_text,
                "rollout_summary": summary_text,
                "rollout_slug": rollout_slug,
            }
        finally:
            try:
                await client.aclose()
            except Exception:
                pass

    def _append_raw_memory_mirror(
        self,
        *,
        user_id: str,
        record: Stage1OutputRecord,
    ) -> None:
        layout = ensure_memory_layout(get_user_global_memory_dir(user_id))
        store = MemoryStore(layout.raw_memories)
        store.initialize()
        existing = store.read_text() or "# Raw Memories\n"
        payload = {
            "id": record.id,
            "user_id": record.user_id,
            "session_id": record.session_id,
            "workspace_id": record.workspace_id,
            "source_path": record.source_path,
            "rollout_slug": record.rollout_slug,
            "created_at": record.created_at,
            "metadata": record.metadata,
        }
        block = (
            f"\n\n## {record.rollout_slug}\n\n"
            "```json\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
            "```\n\n"
            f"{record.raw_memory.strip()}\n"
        )
        store.write_text(existing.rstrip() + block, skip_security_scan=True)

    def _write_rollout_summary(
        self,
        *,
        user_id: str,
        record: Stage1OutputRecord,
    ) -> None:
        layout = ensure_memory_layout(get_user_global_memory_dir(user_id))
        path = layout.rollout_summaries / f"{record.rollout_slug}.md"
        store = MemoryStore(path)
        store.initialize()
        metadata = {
            "id": record.id,
            "user_id": record.user_id,
            "session_id": record.session_id,
            "workspace_id": record.workspace_id,
            "source_path": record.source_path,
            "created_at": record.created_at,
        }
        content = (
            f"# {record.rollout_slug}\n\n"
            "```json\n"
            f"{json.dumps(metadata, ensure_ascii=False, indent=2)}\n"
            "```\n\n"
            f"{record.rollout_summary.strip()}\n"
        )
        store.write_text(content, skip_security_scan=True)

    def _rebuild_stage1_markdown_mirrors(
        self,
        *,
        user_id: str,
        records: list[Stage1OutputRecord],
    ) -> None:
        layout = ensure_memory_layout(get_user_global_memory_dir(user_id))
        keep_files = {f"{record.rollout_slug}.md" for record in records}
        for path in layout.rollout_summaries.glob("*.md"):
            if path.name not in keep_files:
                try:
                    os.unlink(as_system_path(path))
                except OSError:
                    logger.warning("删除过期 rollout summary 失败: %s", path, exc_info=True)

        raw_parts = ["# Raw Memories"]
        if not records:
            raw_parts.append("\nNo raw memories yet.")
        for record in records:
            self._write_rollout_summary(user_id=user_id, record=record)
            payload = {
                "id": record.id,
                "user_id": record.user_id,
                "session_id": record.session_id,
                "workspace_id": record.workspace_id,
                "source_path": record.source_path,
                "rollout_slug": record.rollout_slug,
                "created_at": record.created_at,
                "metadata": record.metadata,
            }
            raw_parts.append(
                "\n"
                f"## {record.rollout_slug}\n\n"
                "```json\n"
                f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
                "```\n\n"
                f"{record.raw_memory.strip()}\n"
            )
        store = MemoryStore(layout.raw_memories)
        store.initialize()
        store.write_text("\n".join(raw_parts).rstrip() + "\n", skip_security_scan=True)

    def _append_stage2_records_to_markdown(
        self,
        *,
        user_id: str,
        records: list[Stage1OutputRecord],
        scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
    ) -> None:
        scope_key = normalize_memory_scope_key(scope_key)
        config = _get_memory_config(user_id)
        max_memory_size = config.max_memory_size or MAX_MEMORY_SIZE
        max_workspace_memory_size = config.max_workspace_memory_size or MAX_WORKSPACE_MEMORY_SIZE

        if is_user_default_global_workspace_scope(scope_key):
            layout = ensure_memory_layout(get_user_global_memory_dir(user_id))
            global_store = MemoryStore(layout.memory)
            global_store.initialize()

            global_blocks = [_format_stage2_append_block(record) for record in records]
            if not global_blocks:
                return
            existing = global_store.read_text().strip()
            new_text = (
                existing + "\n\n" + "## Stage 2 appended memories\n\n" + "\n\n".join(global_blocks)
            ).strip()
            if len(new_text) > max_memory_size:
                logger.warning(
                    "Memory Stage 2 拒绝追加到全局 MEMORY.md: 追加后大小 %d 超过限制 %d",
                    len(new_text),
                    max_memory_size,
                )
                raise MemoryCapacityError(
                    f"Memory 文件大小超过限制（{len(new_text)}/{max_memory_size} chars），"
                    "请触发 consolidation 或手动清理"
                )
            global_store.write_text(new_text + "\n", max_size=max_memory_size)
            return

        for record in records:
            workspace_id = str(record.workspace_id or "").strip()
            if not workspace_id or workspace_id != scope_key:
                continue
            workspace_root = self._resolve_workspace_root(user_id, workspace_id)
            if workspace_root is None:
                logger.warning(
                    "Memory Stage 2 跳过无法解析的 workspace memory: user=%s workspace=%s",
                    user_id,
                    workspace_id,
                )
                continue
            workspace_store = MemoryStore(get_workspace_memory_file_path(workspace_root))
            workspace_store.initialize()
            existing = workspace_store.read_text().strip()
            new_text = (
                existing
                + "\n\n"
                + "## Stage 2 appended memories\n\n"
                + _format_stage2_append_block(record)
            ).strip()
            if len(new_text) > max_workspace_memory_size:
                logger.warning(
                    "Memory Stage 2 拒绝追加到 workspace memory: 追加后大小 %d 超过限制 %d",
                    len(new_text),
                    max_workspace_memory_size,
                )
                raise MemoryCapacityError(
                    f"Memory 文件大小超过限制（{len(new_text)}/{max_workspace_memory_size} chars），"
                    "请触发 consolidation 或手动清理"
                )
            workspace_store.write_text(new_text + "\n", max_size=max_workspace_memory_size)

    def _resolve_workspace_root(self, user_id: str, workspace_id: str) -> Path | None:
        resolver = self._workspace_root_resolver
        try:
            if resolver is not None:
                return Path(resolver(user_id, workspace_id))
            from app.services.workspace_registry import get_workspace_registry_service

            return get_workspace_registry_service().get_workspace_root(
                user_id,
                workspace_id,
            )
        except Exception:
            logger.warning("Failed to resolve workspace root", exc_info=True)
            return None


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def schedule_stage1_for_session(
    *,
    user_id: str,
    session_id: str,
    session_dir: Path,
    workspace_id: str | None = None,
    service: MemoryPipelineService | None = None,
) -> asyncio.Task | None:
    """调度 Stage 1 后台任务。没有运行中的 event loop 时同步跳过。"""

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    pipeline = service or MemoryPipelineService(user_id=user_id)
    task = loop.create_task(
        pipeline.run_stage1_for_session(
            user_id=user_id,
            session_id=session_id,
            workspace_id=workspace_id,
            session_dir=session_dir,
        )
    )
    task.add_done_callback(_log_stage1_task_result)
    return task


def schedule_stage2_consolidation(
    *,
    user_id: str = "local_default",
    scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
    service: MemoryPipelineService | None = None,
) -> asyncio.Task | None:
    """调度 Stage 2 后台追加写入。没有运行中的 event loop 时同步跳过。"""

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    pipeline = service or MemoryPipelineService(user_id=user_id)
    task = loop.create_task(pipeline.run_stage2_consolidation(user_id=user_id, scope_key=scope_key))
    task.add_done_callback(_log_stage2_task_result)
    return task


def _log_stage1_task_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except Exception:
        logger.warning("Memory Stage 1 后台任务异常结束", exc_info=True)


def _log_stage2_task_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except Exception:
        logger.warning("Memory Stage 2 后台任务异常结束", exc_info=True)


def _create_memory_llm_client(user_id: str):
    # 优先使用用户 config.toml [memory] 段配置的专用模型
    memory_model_id = _get_memory_config(user_id).model
    llm_config = get_llm_config_service().get_full_config(user_id)
    default_model_id = llm_config.get("default_chat_model") or llm_config.get("default_model")
    target_model_id = memory_model_id or default_model_id
    models = llm_config.get("models") or {}
    providers = llm_config.get("providers") or {}
    model_payload = models.get(target_model_id or "")
    if not isinstance(model_payload, dict):
        return None
    provider_id = str(model_payload.get("provider") or "")
    provider_payload = providers.get(provider_id)
    if not isinstance(provider_payload, dict):
        return None
    provider = LlmProviderConfig(**provider_payload)
    model = LlmModelConfig(**model_payload)
    model_name = model.model or str(target_model_id)
    return create_llm_client(provider, model_name)


def _build_stage1_prompt(
    *,
    user_id: str,
    session_id: str,
    workspace_id: str | None,
    records: list[dict[str, Any]],
) -> str:
    truncated_records = _deep_truncate_strings(records, max_len=4000)
    compact_records = json.dumps(
        truncated_records,
        ensure_ascii=False,
        indent=2,
    )
    config = _get_memory_config(user_id)
    compact_records = _safe_truncate_prompt_text(compact_records, config.stage1_max_chars)
    return (
        "请从以下 AIASys session execution journal 中提炼长期可复用记忆。\n"
        "输出内容用于后续 Codex 风格 Memory consolidation。\n\n"
        "必须提炼：用户偏好、稳定决策、可复用知识、失败教训。\n"
        "不要记录一次性的中间日志、临时输出或密钥。\n"
        "如果信息只适用于当前 workspace，请在条目中明确 workspace 边界。\n\n"
        f"user_id: {user_id}\n"
        f"session_id: {session_id}\n"
        f"workspace_id: {workspace_id or ''}\n\n"
        "Execution records:\n"
        f"{compact_records}"
    )


def _format_stage2_append_block(record: Stage1OutputRecord) -> str:
    metadata = {
        "id": record.id,
        "session_id": record.session_id,
        "workspace_id": record.workspace_id,
        "source_path": record.source_path,
        "rollout_slug": record.rollout_slug,
        "created_at": record.created_at,
    }
    parts = [
        f"### {record.rollout_slug}",
        "",
        "```json",
        json.dumps(metadata, ensure_ascii=False, indent=2),
        "```",
    ]
    raw_memory = record.raw_memory.strip()
    rollout_summary = record.rollout_summary.strip()
    if raw_memory:
        parts.extend(["", "#### Raw memory", "", raw_memory])
    if rollout_summary and rollout_summary != raw_memory:
        parts.extend(["", "#### Rollout summary", "", rollout_summary])
    return "\n".join(parts).strip()


def _fallback_record_summary(records: list[dict[str, Any]]) -> str:
    lines = ["# Stage 1 Memory Draft", ""]
    for record in records[:5]:
        sequence = record.get("sequence")
        status = record.get("status")
        preview = ((record.get("result_preview") or {}).get("text") or "").strip()
        code = str(record.get("code") or "").strip()
        if len(code) > 240:
            code = code[:240].rstrip() + "..."
        lines.append(f"- execution {sequence}: status={status}")
        if code:
            lines.append(f"  code: {code}")
        if preview:
            lines.append(f"  result: {preview[:240]}")
    return "\n".join(lines).strip()


def _build_consolidation_prompt(
    *,
    current_memory: str,
    current_summary: str,
    raw_memories: str,
    rollout_texts: list[str],
    records: list[Stage1OutputRecord],
    max_input_chars: int = 24000,
) -> str:
    """构建 Codex 风格 memory consolidation prompt。"""

    record_refs = "\n".join(
        f"- {record.rollout_slug} (session_id={record.session_id})" for record in records
    )

    rollout_section = "\n\n---\n\n".join(rollout_texts)
    if len(rollout_section) > 8000:
        rollout_section = rollout_section[:8000].rstrip() + "\n\n...（rollout summaries 已截断）"

    raw_section = raw_memories
    if len(raw_section) > 6000:
        raw_section = raw_section[:6000].rstrip() + "\n\n...（raw memories 已截断）"

    prompt_parts = [
        "# Memory Consolidation Task",
        "",
        "你是 AIASys 的 Memory Consolidation Agent。请整理以下用户长期记忆文件。",
        "",
        "## 输入文件",
        "",
        "### 1. 当前 MEMORY.md",
        "```markdown",
        (
            current_memory[:6000]
            if len(current_memory) <= 6000
            else current_memory[:6000].rstrip() + "\n...（已截断）"
        ),
        "```",
        "",
        "### 2. 当前 memory_summary.md",
        "```markdown",
        (
            current_summary[:2000]
            if len(current_summary) <= 2000
            else current_summary[:2000].rstrip() + "\n...（已截断）"
        ),
        "```",
        "",
        "### 3. Raw Memories",
        "```markdown",
        raw_section,
        "```",
        "",
        "### 4. 本次待合并的 Rollout Summaries",
        "```markdown",
        rollout_section,
        "```",
        "",
        "### 5. 来源引用",
        record_refs,
        "",
        "## 任务要求",
        "",
        "请输出两个部分，用以下标记分隔：",
        "",
        "### 第一部分：新的 MEMORY.md",
        "标记：`<MEMORY>` 和 `</MEMORY>`",
        "",
        "规则：",
        "1. 保留高信号内容：用户偏好、稳定决策、可复用知识、失败教训。",
        "2. 删除低信号内容：一次性中间日志、临时输出、已过时信息。",
        "3. 删除重复内容：如果新旧内容表达同一意思，保留更完整/更精确的版本。",
        "4. 重组结构：使用清晰的 Markdown 标题层级。",
        "5. 保留来源引用：每个关键条目末尾标注 `(来源: session_id, rollout_slug)`。",
        "6. 控制长度：MEMORY.md 不超过 10000 字符。",
        "",
        "### 第二部分：新的 memory_summary.md",
        "标记：`<SUMMARY>` 和 `</SUMMARY>`",
        "",
        "规则：",
        "1. 这是 MEMORY.md 的精华摘要，用于渐进式披露。",
        "2. 只保留最关键的用户偏好、工作习惯和防护规则。",
        "3. 不超过 3000 字符。",
        "4. 如果当前内容已经很好，可以只微调。",
        "",
        "### 特殊情况",
        "如果当前内容不需要任何改动，只输出 `<NOOP></NOOP>`。",
        "",
        "## 输出格式示例",
        "",
        "```",
        "<MEMORY>",
        "# User Preferences",
        "",
        "- 使用简体中文交流 (来源: session-abc, 2026-05-18-session-abc)",
        "- 偏好深色主题 (来源: session-def, 2026-05-19-session-def)",
        "</MEMORY>",
        "",
        "<SUMMARY>",
        "用户偏好简体中文，使用深色主题。",
        "</SUMMARY>",
        "```",
    ]

    prompt = "\n".join(str(p) for p in prompt_parts)
    if len(prompt) > max_input_chars:
        prompt = prompt[:max_input_chars].rstrip() + "\n\n...（prompt 已截断）"
    return prompt


def _parse_consolidation_response(text: str) -> tuple[str | None, str | None]:
    """解析 LLM consolidation 响应，提取 MEMORY 和 SUMMARY。

    返回 (new_memory, new_summary)。如果收到 <NOOP>，返回 (None, None)。
    """
    text = text.strip()
    if "<NOOP>" in text:
        return None, None

    memory = _extract_tag(text, "MEMORY")
    summary = _extract_tag(text, "SUMMARY")
    return memory, summary


def _extract_tag(text: str, tag: str) -> str | None:
    """从文本中提取 <TAG>...</TAG> 内容。"""
    start_marker = f"<{tag}>"
    end_marker = f"</{tag}>"
    start = text.find(start_marker)
    if start == -1:
        return None
    end = text.find(end_marker, start)
    if end == -1:
        return None
    return text[start + len(start_marker) : end].strip()
