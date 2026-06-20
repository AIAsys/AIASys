"""
Session execution journal 服务。

负责：
- 初始化 `.aiasys/session/execution/` 结构
- 清理旧的 conversation / SDK sidecar 历史
- 追加结构化执行记录
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from filelock import FileLock

from app.models.session import (
    ExecutionOrigin,
    ExecutionRecord,
    ExecutionResultPreview,
    ExecutionRuntimeInfo,
)
from app.services.connector.constants import (
    _BEARER_TOKEN_RE,
    _DSN_SECRET_RE,
    _JSON_PASSWORD_FIELD_RE,
    _PASSWORD_FIELD_RE,
)
from app.services.runtime.execution_replay_risk import derive_execution_replay_risk
from app.utils.path_utils import as_system_path

logger = logging.getLogger(__name__)
EXECUTION_JOURNAL_TOOL_NAMES = {"LocalIPythonBox"}
ACTIVE_SESSION_STATE_DIR_NAME = "_active"
HISTORY_SNAPSHOT_FILE_NAME = "history.json"
REDACTED_SECRET = "[REDACTED_SECRET]"


def _redact_execution_secret_text(text: str | None) -> str | None:
    if text is None:
        return None

    def replace_dsn(match: re.Match[str]) -> str:
        if match.group("password") is None:
            return match.group(0)
        return f"{match.group('scheme')}{match.group('user')}:{REDACTED_SECRET}@"

    redacted = _DSN_SECRET_RE.sub(replace_dsn, text)
    redacted = _PASSWORD_FIELD_RE.sub(rf"\1{REDACTED_SECRET}", redacted)
    redacted = _JSON_PASSWORD_FIELD_RE.sub(rf"\1{REDACTED_SECRET}\3", redacted)
    redacted = _BEARER_TOKEN_RE.sub(rf"\1{REDACTED_SECRET}", redacted)
    return redacted


class SessionExecutionJournal:
    """会话执行记录服务。"""

    def __init__(self, session_dir: Path, session_id: str):
        self.session_dir = Path(session_dir)
        self.session_id = session_id
        self.sidecar_dir = self.session_dir / ".aiasys" / "session"
        self.active_state_dir = self.sidecar_dir / ACTIVE_SESSION_STATE_DIR_NAME
        self.execution_dir = self.sidecar_dir / "execution"
        self.artifacts_dir = self.execution_dir / "artifacts"
        self.stdout_dir = self.artifacts_dir / "stdout"
        self.stderr_dir = self.artifacts_dir / "stderr"
        self.files_dir = self.artifacts_dir / "files"
        self.records_path = self.execution_dir / "records.jsonl"
        self.index_path = self.execution_dir / "records-index.json"
        self.recovery_path = self.execution_dir / "recovery.json"
        self.replay_runs_path = self.execution_dir / "replay-runs.jsonl"
        self.history_path = self.active_state_dir / HISTORY_SNAPSHOT_FILE_NAME
        self._records_lock = FileLock(str(self.records_path) + ".lock")
        self._replay_runs_lock = FileLock(str(self.replay_runs_path) + ".lock")

    def initialize_structure(self) -> None:
        """确保 execution journal 目录存在。"""
        self.sidecar_dir.mkdir(parents=True, exist_ok=True)
        self.active_state_dir.mkdir(parents=True, exist_ok=True)
        self.execution_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now().isoformat()
        index_payload = {
            "session_id": self.session_id,
            "last_sequence": 0,
            "last_record_id": None,
            "last_status": None,
            "total_records": 0,
            "updated_at": now,
        }
        existing_index = self._read_json(self.index_path, default={})
        if existing_index:
            index_payload.update(existing_index)
        self._write_json(self.index_path, index_payload)

        recovery_payload = {
            "session_id": self.session_id,
            "recovery_policy": "journal_only",
            "idempotency_policy": "assume_non_idempotent",
            "requires_confirmation_for_replay": True,
            "last_runtime_state": "fresh",
            "last_record_id": None,
            "last_rebuild_status": None,
            "last_replay_run_id": None,
            "last_replayed_sequences": [],
            "last_remaining_sequences": [],
            "last_failed_sequence": None,
            "updated_at": now,
        }
        existing_recovery = self._read_json(self.recovery_path, default={})
        if existing_recovery:
            recovery_payload.update(existing_recovery)
        self._write_json(self.recovery_path, recovery_payload)

    def has_structure(self) -> bool:
        """判断当前 session 是否已具备 execution journal 结构。"""
        return (
            self.execution_dir.exists() and self.index_path.exists() and self.recovery_path.exists()
        )

    def reset_for_rebuild(self, clear_conversation: bool = True) -> None:
        """
        清理 conversation / execution 相关内容，不删除工作区文件。
        """
        if clear_conversation:
            self.active_state_dir.mkdir(parents=True, exist_ok=True)
            Path(as_system_path(self.history_path)).write_text(
                json.dumps({"_schema_version": 1, "messages": []}, ensure_ascii=False),
                encoding="utf-8",
            )

            legacy_history_path = self.session_dir / "history.json"
            if legacy_history_path.exists():
                legacy_history_path.unlink()

            legacy_display_history_path = (
                self.sidecar_dir / self.session_id / "display_history.jsonl"
            )
            if legacy_display_history_path.exists():
                legacy_display_history_path.unlink()

        if self.execution_dir.exists():
            shutil.rmtree(as_system_path(str(self.execution_dir)))

        self.initialize_structure()

    def get_recovery_config(self) -> dict:
        """读取 recovery 配置，不存在时返回默认值。"""
        self.initialize_structure()
        return self._read_json(
            self.recovery_path,
            default={
                "session_id": self.session_id,
                "recovery_policy": "journal_only",
                "idempotency_policy": "assume_non_idempotent",
                "requires_confirmation_for_replay": True,
                "last_runtime_state": "fresh",
                "last_record_id": None,
                "last_rebuild_status": None,
                "last_replay_run_id": None,
                "last_replayed_sequences": [],
                "last_remaining_sequences": [],
                "last_failed_sequence": None,
                "updated_at": datetime.now().isoformat(),
            },
        )

    def update_recovery_config(
        self,
        *,
        recovery_policy: Optional[str] = None,
        idempotency_policy: Optional[str] = None,
        requires_confirmation_for_replay: Optional[bool] = None,
        last_runtime_state: Optional[str] = None,
        last_record_id: Optional[str] = None,
        last_rebuild_status: Optional[str] = None,
        last_replay_run_id: Optional[str] = None,
        last_replayed_sequences: Optional[list[int]] = None,
        last_remaining_sequences: Optional[list[int]] = None,
        last_failed_sequence: Optional[int] = None,
    ) -> dict:
        """更新 recovery 配置，保留未指定字段。"""
        payload = self.get_recovery_config()
        payload["session_id"] = self.session_id
        if recovery_policy is not None:
            payload["recovery_policy"] = recovery_policy
        if idempotency_policy is not None:
            payload["idempotency_policy"] = idempotency_policy
        if requires_confirmation_for_replay is not None:
            payload["requires_confirmation_for_replay"] = requires_confirmation_for_replay
        if last_runtime_state is not None:
            payload["last_runtime_state"] = last_runtime_state
        if last_record_id is not None:
            payload["last_record_id"] = last_record_id
        if last_rebuild_status is not None:
            payload["last_rebuild_status"] = last_rebuild_status
        if last_replay_run_id is not None:
            payload["last_replay_run_id"] = last_replay_run_id
        if last_replayed_sequences is not None:
            payload["last_replayed_sequences"] = list(last_replayed_sequences)
        if last_remaining_sequences is not None:
            payload["last_remaining_sequences"] = list(last_remaining_sequences)
        if last_failed_sequence is not None or "last_failed_sequence" in payload:
            payload["last_failed_sequence"] = last_failed_sequence
        payload["updated_at"] = datetime.now().isoformat()
        self._write_json(self.recovery_path, payload)
        return payload

    def append_record(
        self,
        *,
        code: str,
        started_at: str,
        finished_at: str,
        status: str,
        sandbox_mode: Optional[str] = None,
        env_id: Optional[str] = None,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
        error: Optional[str] = None,
        result_preview_text: Optional[str] = None,
        artifact_refs: Optional[list[str]] = None,
        origin_source: str = "local_ipython_box",
        tool_name: Optional[str] = "LocalIPythonBox",
        request_id: Optional[str] = None,
        target_path: Optional[str] = None,
        agent_config_snapshot: Optional[dict[str, Any]] = None,
    ) -> ExecutionRecord:
        """追加一条结构化执行记录。"""
        self.initialize_structure()

        index = self._read_json(self.index_path, default={})
        sequence = int(index.get("last_sequence") or 0) + 1
        record_id = f"exec_{sequence:06d}"

        redacted_stdout = _redact_execution_secret_text(stdout)
        redacted_stderr = _redact_execution_secret_text(stderr)
        redacted_error = _redact_execution_secret_text(error)
        redacted_result_preview_text = _redact_execution_secret_text(result_preview_text)

        stdout_ref = self._write_stream_artifact("stdout", record_id, redacted_stdout)
        stderr_ref = self._write_stream_artifact("stderr", record_id, redacted_stderr)

        preview_text = self._derive_preview_text(
            result_preview_text=redacted_result_preview_text,
            stdout=redacted_stdout,
            stderr=redacted_stderr,
            error=redacted_error,
        )

        record = ExecutionRecord(
            record_id=record_id,
            session_id=self.session_id,
            sequence=sequence,
            origin=ExecutionOrigin(
                source=origin_source,
                tool_name=tool_name,
                request_id=request_id,
                target_path=target_path,
            ),
            runtime=ExecutionRuntimeInfo(
                sandbox_mode=sandbox_mode,
                env_id=env_id,
            ),
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            code=code,
            stdout_ref=stdout_ref,
            stderr_ref=stderr_ref,
            result_preview=ExecutionResultPreview(type="text", text=preview_text),
            artifact_refs=list(artifact_refs or []),
            error=redacted_error,
            replay_risk=derive_execution_replay_risk(code),
            agent_config_snapshot=agent_config_snapshot,
        )

        with self._records_lock:
            with open(as_system_path(self.records_path), "a", encoding="utf-8") as f:
                f.write(json.dumps(record.model_dump(), ensure_ascii=False) + "\n")

        self._write_json(
            self.index_path,
            {
                "session_id": self.session_id,
                "last_sequence": sequence,
                "last_record_id": record_id,
                "last_status": status,
                "total_records": int(index.get("total_records") or 0) + 1,
                "updated_at": finished_at,
            },
        )
        self.update_recovery_config(
            last_runtime_state="available" if status == "completed" else "failed",
            last_record_id=record_id,
        )

        return record

    def append_replay_run(
        self,
        *,
        started_at: str,
        finished_at: str,
        source_sequences: list[int],
        recovery_policy: Optional[str],
        sandbox_mode: Optional[str],
        env_id: Optional[str],
        restart_runtime: bool,
        include_failed: bool,
        risk_acknowledged: bool,
        upto_sequence: Optional[int],
        selected_sequences: Optional[list[int]],
        replayed_sequences: list[int],
        remaining_sequences: list[int],
        rebuild_status: str,
        completed: bool,
        failed_sequence: Optional[int],
        error: Optional[str],
    ) -> dict:
        """记录一次手动重放审计，不污染主 execution records。"""
        self.initialize_structure()

        payload = {
            "replay_run_id": f"replay_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            "session_id": self.session_id,
            "source_sequences": list(source_sequences),
            "recovery_policy": recovery_policy,
            "runtime": {
                "sandbox_mode": sandbox_mode,
                "env_id": env_id,
            },
            "restart_runtime": restart_runtime,
            "include_failed": include_failed,
            "risk_acknowledged": risk_acknowledged,
            "upto_sequence": upto_sequence,
            "selected_sequences": list(selected_sequences or []),
            "replayed_sequences": list(replayed_sequences),
            "remaining_sequences": list(remaining_sequences),
            "rebuild_status": rebuild_status,
            "completed": completed,
            "failed_sequence": failed_sequence,
            "error": error,
            "started_at": started_at,
            "finished_at": finished_at,
        }

        with self._replay_runs_lock:
            with open(as_system_path(self.replay_runs_path), "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")

        return payload

    def list_records(self, limit: int = 50) -> list[ExecutionRecord]:
        """按时间倒序读取最近执行记录。"""
        if not self.records_path.exists():
            return []

        records: list[ExecutionRecord] = []
        with open(as_system_path(self.records_path), "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                    record = ExecutionRecord.model_validate(payload)
                    record.replay_risk = derive_execution_replay_risk(record.code)
                    records.append(record)
                except Exception as exc:
                    logger.warning("解析 execution record 失败: %s", exc)
                    continue

        records.reverse()
        return records[: max(0, limit)]

    def get_summary(self) -> dict:
        """读取 execution journal 摘要，不主动创建结构。"""
        has_structure = self.has_structure()
        index = self._read_json(self.index_path, default={}) if has_structure else {}
        recovery = self._read_json(self.recovery_path, default={}) if has_structure else {}

        return {
            "has_execution_journal": has_structure,
            "execution_record_count": int(index.get("total_records") or 0),
            "last_execution_status": index.get("last_status"),
            "last_execution_record_id": index.get("last_record_id"),
            "recovery_policy": recovery.get("recovery_policy"),
            "idempotency_policy": recovery.get("idempotency_policy"),
            "requires_confirmation_for_replay": bool(
                recovery.get("requires_confirmation_for_replay", True)
            ),
            "last_runtime_state": recovery.get("last_runtime_state"),
            "rebuild_status": recovery.get("last_rebuild_status"),
            "last_replay_run_id": recovery.get("last_replay_run_id"),
            "last_replayed_sequences": list(recovery.get("last_replayed_sequences") or []),
            "last_remaining_sequences": list(recovery.get("last_remaining_sequences") or []),
            "last_failed_sequence": recovery.get("last_failed_sequence"),
        }

    def _write_stream_artifact(
        self,
        stream_name: str,
        record_id: str,
        content: Optional[str],
    ) -> Optional[str]:
        if not content:
            return None

        target_dir = self.stdout_dir if stream_name == "stdout" else self.stderr_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{record_id}.log"
        Path(as_system_path(target_path)).write_text(str(content), encoding="utf-8")
        return str(target_path.relative_to(self.session_dir).as_posix())

    def _derive_preview_text(
        self,
        *,
        result_preview_text: Optional[str],
        stdout: Optional[str],
        stderr: Optional[str],
        error: Optional[str],
    ) -> str:
        preview = result_preview_text or stdout or stderr or error or ""
        preview = str(preview).strip()
        if len(preview) > 500:
            preview = preview[:500]
        return preview

    def _extract_code_from_tool_arguments(self, arguments: Any) -> str:
        if isinstance(arguments, dict):
            code = arguments.get("code")
            return str(code) if code is not None else ""
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except Exception:
                return ""
            if isinstance(parsed, dict):
                code = parsed.get("code")
                return str(code) if code is not None else ""
        return ""

    def _normalize_tool_content(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if content is None:
            return ""
        if isinstance(content, list):
            normalized_parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    normalized_parts.append(item)
                elif isinstance(item, dict):
                    normalized_parts.append(str(item.get("text") or item.get("content") or ""))
                else:
                    normalized_parts.append(str(item))
            return "".join(normalized_parts)
        if isinstance(content, dict):
            if "text" in content:
                return str(content.get("text") or "")
            return json.dumps(content, ensure_ascii=False)
        return str(content)

    def _read_json(self, path: Path, default: dict) -> dict:
        if not path.exists():
            return dict(default)
        try:
            return json.loads(Path(as_system_path(path)).read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("读取 JSON 失败，回退默认值: path=%s error=%s", path, exc)
            return dict(default)

    def _write_json(self, path: Path, payload: dict) -> None:
        Path(as_system_path(path)).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
