"""Codex 风格 Memory State Runtime。

SQLite 只保存 pipeline 状态、任务租约和水印；长期记忆正文仍保留在
MEMORY.md / memory_summary.md 等 Markdown 文件中，方便用户和 Agent 阅读。
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.services.memory.constants import (
    USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
    is_user_default_global_workspace_scope,
    normalize_memory_scope_key,
)

Stage1JobClaimStatus = Literal["claimed", "already_done", "leased", "throttled"]


@dataclass(frozen=True)
class Stage1JobClaim:
    """Stage 1 租约认领结果。"""

    status: Stage1JobClaimStatus
    worker_id: str | None = None
    lease_until: int | None = None


@dataclass(frozen=True)
class Stage1OutputRecord:
    """Stage 1 会话提炼产物。"""

    id: str
    user_id: str
    session_id: str
    workspace_id: str | None
    source_path: str
    raw_memory: str
    rollout_summary: str
    rollout_slug: str
    metadata: dict[str, Any]
    created_at: int
    consolidated_at: int | None


class MemoryStateRuntime:
    """SQLite-backed memory pipeline 状态库。"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.db_path,
            timeout=30,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS memory_jobs (
                    kind TEXT NOT NULL,
                    job_key TEXT NOT NULL,
                    user_id TEXT,
                    workspace_id TEXT,
                    session_id TEXT,
                    status TEXT NOT NULL,
                    worker_id TEXT,
                    lease_until INTEGER,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    completed_at INTEGER,
                    PRIMARY KEY (kind, job_key)
                );

                CREATE INDEX IF NOT EXISTS idx_memory_jobs_status_lease
                ON memory_jobs(kind, status, lease_until);

                CREATE INDEX IF NOT EXISTS idx_memory_jobs_workspace
                ON memory_jobs(user_id, workspace_id, session_id);

                CREATE TABLE IF NOT EXISTS memory_stage1_outputs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    workspace_id TEXT,
                    source_path TEXT NOT NULL,
                    raw_memory TEXT NOT NULL,
                    rollout_summary TEXT NOT NULL,
                    rollout_slug TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL,
                    consolidated_at INTEGER,
                    usage_count INTEGER DEFAULT 0,
                    last_used_at INTEGER
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_stage1_outputs_session
                ON memory_stage1_outputs(user_id, session_id);

                CREATE INDEX IF NOT EXISTS idx_memory_stage1_outputs_pending
                ON memory_stage1_outputs(consolidated_at, created_at);

                CREATE TABLE IF NOT EXISTS memory_consolidations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    scope_key TEXT NOT NULL,
                    input_watermark INTEGER NOT NULL DEFAULT 0,
                    output_memory_hash TEXT,
                    output_summary_hash TEXT,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(user_id, scope_key)
                );

                CREATE TABLE IF NOT EXISTS memory_versions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    scope_key TEXT NOT NULL,
                    version_type TEXT NOT NULL,
                    source TEXT,
                    memory_content TEXT NOT NULL,
                    summary_content TEXT,
                    created_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_memory_versions_scope
                ON memory_versions(user_id, scope_key, created_at DESC);
                """)
            # Migration: add citation tracking columns if missing
            cols = connection.execute("PRAGMA table_info(memory_stage1_outputs)").fetchall()
            col_names = {row["name"] for row in cols}
            if "usage_count" not in col_names:
                connection.execute(
                    "ALTER TABLE memory_stage1_outputs ADD COLUMN usage_count INTEGER DEFAULT 0"
                )
            if "last_used_at" not in col_names:
                connection.execute(
                    "ALTER TABLE memory_stage1_outputs ADD COLUMN last_used_at INTEGER"
                )

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
        """认领单个 session 的 Stage 1 提炼任务。"""

        now = int(now if now is not None else time.time())
        lease_until = now + lease_seconds
        job_key = self._stage1_job_key(user_id=user_id, session_id=session_id)
        worker_id = worker_id or f"worker_{uuid.uuid4().hex[:12]}"

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing_output = connection.execute(
                    """
                    SELECT id FROM memory_stage1_outputs
                    WHERE user_id = ? AND session_id = ?
                    LIMIT 1
                    """,
                    (user_id, session_id),
                ).fetchone()
                if existing_output is not None:
                    connection.execute("COMMIT")
                    return Stage1JobClaim(status="already_done")

                running_count = connection.execute(
                    """
                    SELECT COUNT(*) FROM memory_jobs
                    WHERE kind = 'stage1'
                      AND status = 'running'
                      AND lease_until IS NOT NULL
                      AND lease_until > ?
                      AND user_id = ?
                    """,
                    (now, user_id),
                ).fetchone()[0]
                if int(running_count) >= max_running_jobs:
                    connection.execute("COMMIT")
                    return Stage1JobClaim(status="throttled")

                existing_job = connection.execute(
                    """
                    SELECT status, lease_until FROM memory_jobs
                    WHERE kind = 'stage1' AND job_key = ?
                    """,
                    (job_key,),
                ).fetchone()
                if existing_job is not None:
                    status = str(existing_job["status"])
                    existing_lease_until = existing_job["lease_until"]
                    if status == "done":
                        connection.execute("COMMIT")
                        return Stage1JobClaim(status="already_done")
                    if (
                        status == "running"
                        and existing_lease_until is not None
                        and int(existing_lease_until) > now
                    ):
                        connection.execute("COMMIT")
                        return Stage1JobClaim(
                            status="leased",
                            lease_until=int(existing_lease_until),
                        )

                connection.execute(
                    """
                    INSERT INTO memory_jobs (
                        kind, job_key, user_id, workspace_id, session_id,
                        status, worker_id, lease_until,
                        attempt_count, last_error, created_at, updated_at, completed_at
                    )
                    VALUES ('stage1', ?, ?, ?, ?, 'running', ?, ?, 1, NULL, ?, ?, NULL)
                    ON CONFLICT(kind, job_key) DO UPDATE SET
                        user_id = excluded.user_id,
                        workspace_id = excluded.workspace_id,
                        session_id = excluded.session_id,
                        status = 'running',
                        worker_id = excluded.worker_id,
                        lease_until = excluded.lease_until,
                        attempt_count = memory_jobs.attempt_count + 1,
                        last_error = NULL,
                        updated_at = excluded.updated_at,
                        completed_at = NULL
                    """,
                    (
                        job_key,
                        user_id,
                        workspace_id,
                        session_id,
                        worker_id,
                        lease_until,
                        now,
                        now,
                    ),
                )
                connection.execute("COMMIT")
                return Stage1JobClaim(
                    status="claimed",
                    worker_id=worker_id,
                    lease_until=lease_until,
                )
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def write_stage1_output(
        self,
        *,
        user_id: str,
        session_id: str,
        source_path: str,
        raw_memory: str,
        rollout_summary: str,
        rollout_slug: str,
        workspace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        now: int | None = None,
    ) -> Stage1OutputRecord:
        """写入 Stage 1 产物，并把对应 job 标为 done。"""

        now = int(now if now is not None else time.time())
        record_id = f"stage1_{uuid.uuid4().hex[:16]}"
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
        job_key = self._stage1_job_key(user_id=user_id, session_id=session_id)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    """
                    SELECT * FROM memory_stage1_outputs
                    WHERE user_id = ? AND session_id = ?
                    LIMIT 1
                    """,
                    (user_id, session_id),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO memory_stage1_outputs (
                            id, user_id, session_id, workspace_id, source_path,
                            raw_memory, rollout_summary, rollout_slug,
                            metadata_json, created_at, consolidated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                        """,
                        (
                            record_id,
                            user_id,
                            session_id,
                            workspace_id,
                            source_path,
                            raw_memory,
                            rollout_summary,
                            rollout_slug,
                            metadata_json,
                            now,
                        ),
                    )
                    row = connection.execute(
                        "SELECT * FROM memory_stage1_outputs WHERE id = ?",
                        (record_id,),
                    ).fetchone()
                else:
                    connection.execute(
                        """
                        UPDATE memory_stage1_outputs
                        SET workspace_id = ?,
                            source_path = ?,
                            raw_memory = ?,
                            rollout_summary = ?,
                            rollout_slug = ?,
                            metadata_json = ?,
                            created_at = ?
                        WHERE id = ?
                        """,
                        (
                            workspace_id,
                            source_path,
                            raw_memory,
                            rollout_summary,
                            rollout_slug,
                            metadata_json,
                            now,
                            existing["id"],
                        ),
                    )
                    row = connection.execute(
                        "SELECT * FROM memory_stage1_outputs WHERE id = ?",
                        (existing["id"],),
                    ).fetchone()

                connection.execute(
                    """
                    INSERT INTO memory_jobs (
                        kind, job_key, user_id, workspace_id, session_id,
                        status, worker_id, lease_until,
                        attempt_count, last_error, created_at, updated_at, completed_at
                    )
                    VALUES ('stage1', ?, ?, ?, ?, 'done', NULL, NULL, 0, NULL, ?, ?, ?)
                    ON CONFLICT(kind, job_key) DO UPDATE SET
                        user_id = excluded.user_id,
                        workspace_id = excluded.workspace_id,
                        session_id = excluded.session_id,
                        status = 'done',
                        worker_id = NULL,
                        lease_until = NULL,
                        last_error = NULL,
                        updated_at = excluded.updated_at,
                        completed_at = excluded.completed_at
                    """,
                    (job_key, user_id, workspace_id, session_id, now, now, now),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

        return self._row_to_stage1_output(row)

    def delete_stage1_output(self, record_id: str) -> None:
        """删除 Stage 1 产物记录（用于镜像写入失败时的回滚）。"""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "DELETE FROM memory_stage1_outputs WHERE id = ?",
                    (record_id,),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def fail_stage1_job(
        self,
        *,
        user_id: str,
        session_id: str,
        error: str,
        now: int | None = None,
    ) -> None:
        """标记 Stage 1 job 失败，释放租约。"""

        now = int(now if now is not None else time.time())
        job_key = self._stage1_job_key(user_id=user_id, session_id=session_id)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    UPDATE memory_jobs
                    SET status = 'failed',
                        worker_id = NULL,
                        lease_until = NULL,
                        last_error = ?,
                        updated_at = ?
                    WHERE kind = 'stage1' AND job_key = ?
                    """,
                    (error[:2000], now, job_key),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def claim_stage2_job(
        self,
        *,
        user_id: str,
        scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
        lease_seconds: int = 900,
        max_running_jobs: int = 1,
        now: int | None = None,
        worker_id: str | None = None,
    ) -> Stage1JobClaim:
        """认领 Stage 2 consolidation 任务。"""

        scope_key = normalize_memory_scope_key(scope_key)
        return self._claim_running_job(
            kind="stage2",
            job_key=self._stage2_job_key(user_id=user_id, scope_key=scope_key),
            user_id=user_id,
            workspace_id=None,
            session_id=None,
            lease_seconds=lease_seconds,
            max_running_jobs=max_running_jobs,
            now=now,
            worker_id=worker_id,
        )

    def complete_stage2_job(
        self,
        *,
        user_id: str,
        scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
        now: int | None = None,
    ) -> None:
        """标记 Stage 2 consolidation 任务完成，释放租约。"""

        scope_key = normalize_memory_scope_key(scope_key)
        self._finish_job(
            kind="stage2",
            job_key=self._stage2_job_key(user_id=user_id, scope_key=scope_key),
            status="done",
            error=None,
            now=now,
        )

    def fail_stage2_job(
        self,
        *,
        user_id: str,
        error: str,
        scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
        now: int | None = None,
    ) -> None:
        """标记 Stage 2 consolidation 任务失败，释放租约。"""

        scope_key = normalize_memory_scope_key(scope_key)
        self._finish_job(
            kind="stage2",
            job_key=self._stage2_job_key(user_id=user_id, scope_key=scope_key),
            status="failed",
            error=error,
            now=now,
        )

    def list_pending_stage1_outputs(
        self,
        *,
        user_id: str,
        limit: int = 128,
        max_created_at: int | None = None,
        scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
    ) -> list[Stage1OutputRecord]:
        """列出尚未合并的 Stage 1 产物。"""

        scope_key = normalize_memory_scope_key(scope_key)
        params: list[Any] = [user_id]
        where = ["user_id = ?", "consolidated_at IS NULL"]
        if is_user_default_global_workspace_scope(scope_key):
            where.append("workspace_id IS NULL")
        else:
            where.append("workspace_id = ?")
            params.append(scope_key)
        if max_created_at is not None:
            where.append("created_at <= ?")
            params.append(max_created_at)
        params.append(max(limit, 0))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM memory_stage1_outputs
                WHERE """
                + " AND ".join(where)
                + """
                ORDER BY created_at ASC, id ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._row_to_stage1_output(row) for row in rows]

    def list_stage1_outputs(
        self,
        *,
        user_id: str,
        limit: int = 128,
    ) -> list[Stage1OutputRecord]:
        """按新到旧列出 Stage 1 产物，用于重建 Markdown 镜像。"""

        if limit <= 0:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM memory_stage1_outputs
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [self._row_to_stage1_output(row) for row in rows]

    def get_pipeline_status(
        self,
        *,
        user_id: str,
        scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
    ) -> dict[str, Any]:
        """返回面向前端的 memory pipeline 轻量状态摘要。"""

        scope_key = normalize_memory_scope_key(scope_key)
        stage1_where = ["user_id = ?"]
        stage1_params: list[Any] = [user_id]
        stage1_job_where = ["user_id = ?", "kind = 'stage1'"]
        stage1_job_params: list[Any] = [user_id]
        if is_user_default_global_workspace_scope(scope_key):
            stage1_where.append("workspace_id IS NULL")
            stage1_job_where.append("workspace_id IS NULL")
        else:
            stage1_where.append("workspace_id = ?")
            stage1_params.append(scope_key)
            stage1_job_where.append("workspace_id = ?")
            stage1_job_params.append(scope_key)
        stage2_job_key = self._stage2_job_key(user_id=user_id, scope_key=scope_key)

        with self._connect() as connection:
            counts = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_count,
                    SUM(CASE WHEN consolidated_at IS NULL THEN 1 ELSE 0 END)
                        AS pending_count,
                    MAX(created_at) AS latest_output_at,
                    MAX(consolidated_at) AS latest_consolidated_at
                FROM memory_stage1_outputs
                WHERE """
                + " AND ".join(stage1_where)
                + """
                """,
                stage1_params,
            ).fetchone()
            latest_stage1_job = connection.execute(
                """
                SELECT * FROM memory_jobs
                WHERE """
                + " AND ".join(stage1_job_where)
                + """
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                stage1_job_params,
            ).fetchone()
            latest_stage2_job = connection.execute(
                """
                SELECT * FROM memory_jobs
                WHERE user_id = ? AND kind = 'stage2' AND job_key = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (user_id, stage2_job_key),
            ).fetchone()
            consolidation = connection.execute(
                """
                SELECT * FROM memory_consolidations
                WHERE user_id = ? AND scope_key = ?
                LIMIT 1
                """,
                (user_id, scope_key),
            ).fetchone()

        total_count = int(counts["total_count"] or 0) if counts else 0
        pending_count = int(counts["pending_count"] or 0) if counts else 0
        return {
            "user_id": user_id,
            "scope_key": scope_key,
            "stage1": {
                "total_outputs": total_count,
                "pending_outputs": pending_count,
                "latest_output_at": counts["latest_output_at"] if counts else None,
                "latest_job": (
                    self._row_to_job_dict(latest_stage1_job)
                    if latest_stage1_job is not None
                    else None
                ),
            },
            "stage2": {
                "latest_consolidated_at": (counts["latest_consolidated_at"] if counts else None),
                "latest_job": (
                    self._row_to_job_dict(latest_stage2_job)
                    if latest_stage2_job is not None
                    else None
                ),
                "consolidation": (
                    self._row_to_consolidation_dict(consolidation)
                    if consolidation is not None
                    else None
                ),
            },
        }

    def prune_stage1_outputs_for_retention(
        self,
        *,
        user_id: str,
        keep_latest: int,
        max_age_days: int | None = None,
        min_usage_count: int = 3,
        now: int | None = None,
    ) -> dict[str, Any]:
        """清理已合并的旧 Stage 1 产物，未合并产物永远保留。

        引用次数 >= min_usage_count 的已合并条目受保护，不参与清理。
        """

        keep_latest = max(int(keep_latest), 0)
        now = int(now if now is not None else time.time())
        cutoff = (
            now - max_age_days * 86400 if max_age_days is not None and max_age_days > 0 else None
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                rows = connection.execute(
                    """
                    SELECT id, rollout_slug, created_at, consolidated_at, usage_count
                    FROM memory_stage1_outputs
                    WHERE user_id = ?
                    ORDER BY created_at DESC, id DESC
                    """,
                    (user_id,),
                ).fetchall()
                consolidated_rows = [row for row in rows if row["consolidated_at"] is not None]
                keep_ids = {str(row["id"]) for row in consolidated_rows[:keep_latest]}
                delete_rows: list[sqlite3.Row] = []
                for row in rows:
                    row_id = str(row["id"])
                    consolidated_at = row["consolidated_at"]
                    usage_count = int(row["usage_count"] or 0)
                    if consolidated_at is None:
                        continue
                    # 保护高引用条目
                    if usage_count >= min_usage_count:
                        continue
                    outside_count_window = row_id not in keep_ids
                    outside_age_window = cutoff is None or int(row["created_at"]) < cutoff
                    if outside_count_window and outside_age_window:
                        delete_rows.append(row)

                if delete_rows:
                    connection.executemany(
                        "DELETE FROM memory_stage1_outputs WHERE id = ?",
                        [(row["id"],) for row in delete_rows],
                    )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

        with self._connect() as connection:
            remaining_pending_count = connection.execute(
                """
                SELECT COUNT(*) FROM memory_stage1_outputs
                WHERE user_id = ? AND consolidated_at IS NULL
                """,
                (user_id,),
            ).fetchone()[0]

        return {
            "pruned_count": len(delete_rows),
            "pruned_rollout_slugs": [str(row["rollout_slug"]) for row in delete_rows],
            "remaining_pending_count": int(remaining_pending_count or 0),
        }

    def record_citation(
        self,
        *,
        user_id: str,
        session_id: str,
        record_id: str | None = None,
        now: int | None = None,
    ) -> None:
        """记录一次 Stage 1 产物的引用，增加 usage_count 并更新 last_used_at。"""

        now = int(now if now is not None else time.time())
        with self._connect() as connection:
            if record_id is not None:
                connection.execute(
                    """
                    UPDATE memory_stage1_outputs
                    SET usage_count = COALESCE(usage_count, 0) + 1,
                        last_used_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (now, record_id, user_id),
                )
            else:
                connection.execute(
                    """
                    UPDATE memory_stage1_outputs
                    SET usage_count = COALESCE(usage_count, 0) + 1,
                        last_used_at = ?
                    WHERE user_id = ? AND session_id = ?
                    """,
                    (now, user_id, session_id),
                )

    def get_citation_stats(
        self,
        *,
        user_id: str,
        limit: int = 128,
    ) -> list[dict[str, Any]]:
        """返回引用统计列表，按 usage_count DESC、last_used_at DESC 排序。"""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, workspace_id, rollout_slug,
                       usage_count, last_used_at, created_at
                FROM memory_stage1_outputs
                WHERE user_id = ? AND COALESCE(usage_count, 0) > 0
                ORDER BY usage_count DESC, last_used_at DESC
                LIMIT ?
                """,
                (user_id, max(limit, 0)),
            ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "session_id": str(row["session_id"]),
                "workspace_id": row["workspace_id"],
                "rollout_slug": str(row["rollout_slug"]),
                "usage_count": int(row["usage_count"] or 0),
                "last_used_at": row["last_used_at"],
                "created_at": int(row["created_at"]),
            }
            for row in rows
        ]

    def get_records_by_usage(
        self,
        *,
        user_id: str,
        min_usage_count: int = 0,
    ) -> list[Stage1OutputRecord]:
        """按引用次数排序获取记录。"""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM memory_stage1_outputs
                WHERE user_id = ? AND COALESCE(usage_count, 0) >= ?
                ORDER BY usage_count DESC, created_at DESC
                """,
                (user_id, max(min_usage_count, 0)),
            ).fetchall()
        return [self._row_to_stage1_output(row) for row in rows]

    def get_consolidation_watermark(
        self,
        *,
        user_id: str,
        scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
    ) -> int:
        scope_key = normalize_memory_scope_key(scope_key)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT input_watermark FROM memory_consolidations
                WHERE user_id = ? AND scope_key = ?
                """,
                (user_id, scope_key),
            ).fetchone()
        return int(row["input_watermark"]) if row is not None else 0

    def update_consolidation_state(
        self,
        *,
        user_id: str,
        input_watermark: int,
        scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
        output_memory_hash: str | None = None,
        output_summary_hash: str | None = None,
        stage1_output_ids: list[str] | None = None,
        now: int | None = None,
    ) -> None:
        """更新合并水印，并可把一组 Stage 1 产物标记为已合并。"""

        scope_key = normalize_memory_scope_key(scope_key)
        now = int(now if now is not None else time.time())
        consolidation_id = f"consolidation_{user_id}_{scope_key}"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO memory_consolidations (
                        id, user_id, scope_key, input_watermark,
                        output_memory_hash, output_summary_hash, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, scope_key) DO UPDATE SET
                        input_watermark = excluded.input_watermark,
                        output_memory_hash = excluded.output_memory_hash,
                        output_summary_hash = excluded.output_summary_hash,
                        updated_at = excluded.updated_at
                    """,
                    (
                        consolidation_id,
                        user_id,
                        scope_key,
                        input_watermark,
                        output_memory_hash,
                        output_summary_hash,
                        now,
                    ),
                )
                if stage1_output_ids:
                    connection.executemany(
                        """
                        UPDATE memory_stage1_outputs
                        SET consolidated_at = ?
                        WHERE id = ?
                        """,
                        [(now, output_id) for output_id in stage1_output_ids],
                    )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    @staticmethod
    def _stage1_job_key(*, user_id: str, session_id: str) -> str:
        return f"{user_id}:{session_id}"

    @staticmethod
    def _stage2_job_key(*, user_id: str, scope_key: str) -> str:
        return f"{user_id}:{scope_key}"

    def _claim_running_job(
        self,
        *,
        kind: str,
        job_key: str,
        user_id: str,
        workspace_id: str | None,
        session_id: str | None,
        lease_seconds: int,
        max_running_jobs: int,
        now: int | None,
        worker_id: str | None,
    ) -> Stage1JobClaim:
        now = int(now if now is not None else time.time())
        lease_until = now + lease_seconds
        worker_id = worker_id or f"worker_{uuid.uuid4().hex[:12]}"

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                running_count = connection.execute(
                    """
                    SELECT COUNT(*) FROM memory_jobs
                    WHERE kind = ?
                      AND status = 'running'
                      AND lease_until IS NOT NULL
                      AND lease_until > ?
                      AND user_id = ?
                    """,
                    (kind, now, user_id),
                ).fetchone()[0]
                if int(running_count) >= max_running_jobs:
                    connection.execute("COMMIT")
                    return Stage1JobClaim(status="throttled")

                existing_job = connection.execute(
                    """
                    SELECT status, lease_until FROM memory_jobs
                    WHERE kind = ? AND job_key = ?
                    """,
                    (kind, job_key),
                ).fetchone()
                if existing_job is not None:
                    existing_lease_until = existing_job["lease_until"]
                    if (
                        str(existing_job["status"]) == "running"
                        and existing_lease_until is not None
                        and int(existing_lease_until) > now
                    ):
                        connection.execute("COMMIT")
                        return Stage1JobClaim(
                            status="leased",
                            lease_until=int(existing_lease_until),
                        )

                connection.execute(
                    """
                    INSERT INTO memory_jobs (
                        kind, job_key, user_id, workspace_id, session_id,
                        status, worker_id, lease_until,
                        attempt_count, last_error, created_at, updated_at, completed_at
                    )
                    VALUES (?, ?, ?, ?, ?, 'running', ?, ?, 1, NULL, ?, ?, NULL)
                    ON CONFLICT(kind, job_key) DO UPDATE SET
                        user_id = excluded.user_id,
                        workspace_id = excluded.workspace_id,
                        session_id = excluded.session_id,
                        status = 'running',
                        worker_id = excluded.worker_id,
                        lease_until = excluded.lease_until,
                        attempt_count = memory_jobs.attempt_count + 1,
                        last_error = NULL,
                        updated_at = excluded.updated_at,
                        completed_at = NULL
                    """,
                    (
                        kind,
                        job_key,
                        user_id,
                        workspace_id,
                        session_id,
                        worker_id,
                        lease_until,
                        now,
                        now,
                    ),
                )
                connection.execute("COMMIT")
                return Stage1JobClaim(
                    status="claimed",
                    worker_id=worker_id,
                    lease_until=lease_until,
                )
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def _finish_job(
        self,
        *,
        kind: str,
        job_key: str,
        status: str,
        error: str | None,
        now: int | None,
    ) -> None:
        now = int(now if now is not None else time.time())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    UPDATE memory_jobs
                    SET status = ?,
                        worker_id = NULL,
                        lease_until = NULL,
                        last_error = ?,
                        updated_at = ?,
                        completed_at = ?
                    WHERE kind = ? AND job_key = ?
                    """,
                    (
                        status,
                        error[:2000] if error else None,
                        now,
                        now if status == "done" else None,
                        kind,
                        job_key,
                    ),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    @staticmethod
    def _row_to_job_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "kind": str(row["kind"]),
            "job_key": str(row["job_key"]),
            "user_id": row["user_id"],
            "workspace_id": row["workspace_id"],
            "session_id": row["session_id"],
            "status": str(row["status"]),
            "worker_id": row["worker_id"],
            "lease_until": row["lease_until"],
            "attempt_count": int(row["attempt_count"] or 0),
            "last_error": row["last_error"],
            "created_at": int(row["created_at"]),
            "updated_at": int(row["updated_at"]),
            "completed_at": (int(row["completed_at"]) if row["completed_at"] is not None else None),
        }

    @staticmethod
    def _row_to_consolidation_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "scope_key": str(row["scope_key"]),
            "input_watermark": int(row["input_watermark"] or 0),
            "output_memory_hash": row["output_memory_hash"],
            "output_summary_hash": row["output_summary_hash"],
            "updated_at": int(row["updated_at"]),
        }

    @staticmethod
    def _row_to_stage1_output(row: sqlite3.Row) -> Stage1OutputRecord:
        metadata_json = row["metadata_json"] or "{}"
        try:
            metadata = json.loads(str(metadata_json))
        except json.JSONDecodeError:
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        return Stage1OutputRecord(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            session_id=str(row["session_id"]),
            workspace_id=row["workspace_id"],
            source_path=str(row["source_path"]),
            raw_memory=str(row["raw_memory"]),
            rollout_summary=str(row["rollout_summary"]),
            rollout_slug=str(row["rollout_slug"]),
            metadata=metadata,
            created_at=int(row["created_at"]),
            consolidated_at=(
                int(row["consolidated_at"]) if row["consolidated_at"] is not None else None
            ),
        )

    # ------------------------------------------------------------------
    # Memory Versions（consolidation 历史版本管理）
    # ------------------------------------------------------------------

    def save_version(
        self,
        *,
        user_id: str,
        scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
        version_type: str = "consolidation",
        source: str | None = None,
        memory_content: str,
        summary_content: str | None = None,
        now: int | None = None,
    ) -> str:
        """保存一个 memory 版本，返回 version_id。"""

        scope_key = normalize_memory_scope_key(scope_key)
        now = int(now if now is not None else time.time())
        version_id = f"mv_{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_versions (
                    id, user_id, scope_key, version_type, source,
                    memory_content, summary_content, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    user_id,
                    scope_key,
                    version_type,
                    source,
                    memory_content,
                    summary_content,
                    now,
                ),
            )
        return version_id

    def list_versions(
        self,
        *,
        user_id: str,
        scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """列出版本元数据，不含完整内容。"""

        scope_key = normalize_memory_scope_key(scope_key)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, version_type, source, created_at,
                       SUBSTR(memory_content, 1, 200) as summary
                FROM memory_versions
                WHERE user_id = ? AND scope_key = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (user_id, scope_key, max(limit, 1)),
            ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "version_type": str(row["version_type"]),
                "source": row["source"],
                "created_at": int(row["created_at"]),
                "summary": str(row["summary"] or ""),
            }
            for row in rows
        ]

    def get_version(
        self,
        *,
        version_id: str,
    ) -> dict[str, Any] | None:
        """读取单个版本的完整内容。"""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM memory_versions WHERE id = ?
                """,
                (version_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "scope_key": str(row["scope_key"]),
            "version_type": str(row["version_type"]),
            "source": row["source"],
            "memory_content": str(row["memory_content"]),
            "summary_content": row["summary_content"],
            "created_at": int(row["created_at"]),
        }

    def prune_old_versions(
        self,
        *,
        user_id: str,
        scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
        keep_latest: int = 20,
    ) -> int:
        """清理超出保留数量的旧版本，返回删除条数。"""

        scope_key = normalize_memory_scope_key(scope_key)
        if keep_latest <= 0:
            return 0
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                # 找出需要删除的旧版本 ID
                rows = connection.execute(
                    """
                    SELECT id FROM memory_versions
                    WHERE user_id = ? AND scope_key = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT -1 OFFSET ?
                    """,
                    (user_id, scope_key, keep_latest),
                ).fetchall()
                if not rows:
                    connection.execute("COMMIT")
                    return 0
                ids_to_delete = [str(row["id"]) for row in rows]
                connection.executemany(
                    "DELETE FROM memory_versions WHERE id = ?",
                    [(vid,) for vid in ids_to_delete],
                )
                connection.execute("COMMIT")
                return len(ids_to_delete)
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def has_versions(
        self,
        *,
        user_id: str,
        scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
    ) -> bool:
        """检查指定 scope 是否有历史版本。"""

        scope_key = normalize_memory_scope_key(scope_key)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM memory_versions
                WHERE user_id = ? AND scope_key = ?
                LIMIT 1
                """,
                (user_id, scope_key),
            ).fetchone()
        return row is not None
