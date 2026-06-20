from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Literal, Optional

from app.models.session import SessionMetadata
from app.services.history.session_execution_journal import SessionExecutionJournal
from app.services.history.session_history_projection import unwrap_user_prompt

if TYPE_CHECKING:
    from app.services.session import SessionManager

SessionExportScope = Literal["bundle", "conversation", "workspace"]

INTERNAL_SESSION_DIRS = {".aiasys"}
INTERNAL_SESSION_FILES = {"metadata.json", "file_snapshots.json"}
SENSITIVE_EXACT_FILENAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    "config.local.json",
    "settings.local.json",
    "llm_config.json",
    "mcp.json",
    ".mcp_session.json",
    "mcp.yaml",
    "mcp.yml",
}
SENSITIVE_SUFFIXES = {
    ".key",
    ".pem",
    ".p12",
    ".pfx",
    ".crt",
    ".cer",
}
SENSITIVE_NAME_TOKENS = {
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "credential",
    "private_key",
    "id_rsa",
}


class SessionExportNotFoundError(FileNotFoundError):
    """导出目标会话不存在。"""


class SessionExportService:
    """构建会话级导出结果。"""

    def __init__(self, session_manager: SessionManager):
        self._session_manager = session_manager

    def build_conversation_export(
        self,
        *,
        user_id: str,
        session_id: str,
        exported_by: Optional[str] = None,
    ) -> tuple[bytes, str]:
        """导出完整会话对话，直接读取 history.json 原始消息并回填 tool 结果。"""
        session_dir, metadata = self._get_session_context(session_id, user_id)
        conversation_messages = self._load_exportable_messages(session_dir)
        conversation_messages = self._backfill_tool_results(conversation_messages, session_dir)
        conversation_messages = self._attach_display_content(conversation_messages)

        payload = {
            "feature": "session_conversation_export",
            "version": 1,
            "exported_at": datetime.now().isoformat(),
            "exported_by": exported_by,
            "session": self._serialize_session_metadata(
                metadata=metadata,
                user_id=user_id,
                session_id=session_id,
                conversation_message_count=len(conversation_messages),
            ),
            "messages": conversation_messages,
        }

        return (
            json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"),
            f"session_conversation_{session_id}.json",
        )

    def build_workspace_archive(
        self,
        *,
        user_id: str,
        session_id: str,
        exported_by: Optional[str] = None,
    ) -> tuple[io.BytesIO, str]:
        session_dir, metadata = self._get_session_context(session_id, user_id)
        workspace_files, skipped_sensitive_files = self._scan_workspace_files(session_dir)

        manifest = self._build_manifest(
            scope="workspace",
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
            workspace_files=workspace_files,
            conversation_message_count=0,
            exported_by=exported_by,
            skipped_sensitive_files=skipped_sensitive_files,
        )

        workspace_manifest = self._build_workspace_manifest(workspace_files)
        return self._build_zip_archive(
            session_id=session_id,
            scope="workspace",
            manifest=manifest,
            workspace_manifest=workspace_manifest,
            workspace_files=workspace_files,
            conversation_messages=None,
        )

    def build_bundle_archive(
        self,
        *,
        user_id: str,
        session_id: str,
        exported_by: Optional[str] = None,
    ) -> tuple[io.BytesIO, str]:
        session_dir, metadata = self._get_session_context(session_id, user_id)
        workspace_files, skipped_sensitive_files = self._scan_workspace_files(session_dir)

        conversation_messages = self._load_exportable_messages(session_dir)
        conversation_messages = self._backfill_tool_results(conversation_messages, session_dir)
        conversation_messages = self._attach_display_content(conversation_messages)

        manifest = self._build_manifest(
            scope="bundle",
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
            workspace_files=workspace_files,
            conversation_message_count=len(conversation_messages),
            exported_by=exported_by,
            skipped_sensitive_files=skipped_sensitive_files,
        )
        workspace_manifest = self._build_workspace_manifest(workspace_files)

        return self._build_zip_archive(
            session_id=session_id,
            scope="bundle",
            manifest=manifest,
            workspace_manifest=workspace_manifest,
            workspace_files=workspace_files,
            conversation_messages=conversation_messages,
        )

    def _build_zip_archive(
        self,
        *,
        session_id: str,
        scope: Literal["bundle", "workspace"],
        manifest: Dict[str, Any],
        workspace_manifest: Dict[str, Any],
        workspace_files: List[tuple[str, Path]],
        conversation_messages: Optional[List[Dict[str, Any]]],
    ) -> tuple[io.BytesIO, str]:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(
                "manifest.json",
                json.dumps(manifest, indent=2, ensure_ascii=False),
            )
            zip_file.writestr(
                "workspace_manifest.json",
                json.dumps(workspace_manifest, indent=2, ensure_ascii=False),
            )

            if conversation_messages is not None:
                zip_file.writestr(
                    "conversation.json",
                    json.dumps(conversation_messages, indent=2, ensure_ascii=False),
                )

            if workspace_files:
                for relative_path, file_path in workspace_files:
                    zip_file.write(file_path, f"workspace/{relative_path}")
            else:
                zip_file.writestr("workspace/", "")

        zip_buffer.seek(0)
        return zip_buffer, f"session_export_{session_id}_{scope}.zip"

    def _build_manifest(
        self,
        *,
        scope: Literal["bundle", "workspace"],
        user_id: str,
        session_id: str,
        metadata: Optional[SessionMetadata],
        workspace_files: List[tuple[str, Path]],
        conversation_message_count: int,
        exported_by: Optional[str],
        skipped_sensitive_files: List[str],
    ) -> Dict[str, Any]:
        entries: List[str] = ["manifest.json", "workspace_manifest.json"]
        entries.extend(f"workspace/{relative_path}" for relative_path, _ in workspace_files)
        if scope == "bundle":
            entries.append("conversation.json")

        return {
            "feature": "session_export",
            "version": 1,
            "scope": scope,
            "exported_at": datetime.now().isoformat(),
            "exported_by": exported_by,
            "session": self._serialize_session_metadata(
                metadata=metadata,
                user_id=user_id,
                session_id=session_id,
                conversation_message_count=conversation_message_count,
            ),
            "counts": {
                "conversation_messages": conversation_message_count,
                "workspace_files": len(workspace_files),
                "skipped_sensitive_files": len(skipped_sensitive_files),
            },
            "guards": {
                "excluded_sensitive_files": skipped_sensitive_files,
            },
            "entries": entries,
        }

    def _serialize_session_metadata(
        self,
        *,
        metadata: Optional[SessionMetadata],
        user_id: str,
        session_id: str,
        conversation_message_count: int,
    ) -> Dict[str, Any]:
        return {
            "user_id": user_id,
            "session_id": session_id,
            "title": metadata.title if metadata else session_id,
            "created_at": metadata.created_at if metadata else None,
            "updated_at": metadata.updated_at if metadata else None,
            "message_count": (metadata.message_count if metadata else conversation_message_count),
            "env_id": metadata.env_id if metadata else None,
            "sandbox_mode": metadata.sandbox_mode if metadata else None,
        }

    def _load_exportable_messages(self, session_dir: Path) -> List[Dict[str, Any]]:
        """直接读取 history.json 原始消息，过滤内部角色与 system-reminder。"""
        from app.services.session.constants import (
            ACTIVE_SESSION_STATE_DIR_NAME,
            HISTORY_SNAPSHOT_FILE_NAME,
        )

        history_path = (
            session_dir
            / ".aiasys"
            / "session"
            / ACTIVE_SESSION_STATE_DIR_NAME
            / HISTORY_SNAPSHOT_FILE_NAME
        )
        messages: List[Dict[str, Any]] = []
        if history_path.exists():
            try:
                data = json.loads(history_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    raw_messages = data.get("messages") or []
                    if isinstance(raw_messages, list):
                        messages = raw_messages
            except Exception:
                pass

        return [
            dict(msg)
            for msg in messages
            if isinstance(msg, dict)
            and msg.get("role") not in ("_checkpoint", "_usage", "_system_prompt", "system")
            and not self._is_system_reminder_message(msg)
        ]

    def _backfill_tool_results(
        self,
        messages: List[Dict[str, Any]],
        session_dir: Path,
    ) -> List[Dict[str, Any]]:
        """从 execution journal 回填被压缩清理的 tool 结果，便于调试。"""
        if not messages:
            return messages

        tool_call_ids = {
            str(msg.get("tool_call_id") or "")
            for msg in messages
            if msg.get("role") == "tool" and self._is_cleared_tool_result(msg)
        }
        if not tool_call_ids:
            return messages

        tool_call_ids.discard("")
        journal = SessionExecutionJournal(session_dir, session_dir.name)
        stdout_map: Dict[str, str] = {}
        stderr_map: Dict[str, str] = {}

        # 读取全部 records（不限制 50 条）
        records_path = journal.records_path
        if records_path.exists():
            try:
                with open(records_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(record, dict):
                            continue
                        request_id = str(record.get("origin", {}).get("request_id") or "")
                        if request_id not in tool_call_ids:
                            continue
                        stdout_ref = record.get("stdout_ref")
                        stderr_ref = record.get("stderr_ref")
                        stdout_text = ""
                        stderr_text = ""
                        if stdout_ref:
                            stdout_path = session_dir / stdout_ref
                            if stdout_path.exists():
                                try:
                                    stdout_text = stdout_path.read_text(encoding="utf-8")
                                except Exception:
                                    pass
                        if stderr_ref:
                            stderr_path = session_dir / stderr_ref
                            if stderr_path.exists():
                                try:
                                    stderr_text = stderr_path.read_text(encoding="utf-8")
                                except Exception:
                                    pass
                        if stdout_text:
                            stdout_map[request_id] = stdout_text
                        if stderr_text:
                            stderr_map[request_id] = stderr_text
            except Exception:
                pass

        if not stdout_map and not stderr_map:
            return messages

        backfilled: List[Dict[str, Any]] = []
        for msg in messages:
            if msg.get("role") != "tool" or not self._is_cleared_tool_result(msg):
                backfilled.append(msg)
                continue

            tool_call_id = str(msg.get("tool_call_id") or "")
            new_msg = dict(msg)
            parts: List[str] = []
            if tool_call_id in stdout_map:
                parts.append(stdout_map[tool_call_id])
            if tool_call_id in stderr_map:
                if parts:
                    parts.append("\n")
                parts.append("[stderr]\n")
                parts.append(stderr_map[tool_call_id])
            if parts:
                new_msg["content"] = "".join(parts)
                # 保留清理标记作为追溯信息
                new_msg["_tool_result_backfilled"] = True
            backfilled.append(new_msg)

        return backfilled

    def _is_cleared_tool_result(self, msg: Dict[str, Any]) -> bool:
        content = msg.get("content")
        return isinstance(content, str) and content.startswith("[已清理: tool 结果")

    def _is_system_reminder_message(self, msg: Dict[str, Any]) -> bool:
        if msg.get("role") != "user":
            return False
        content = msg.get("content")
        if not isinstance(content, str):
            return False
        return content.strip().startswith("<system-reminder>")

    def _attach_display_content(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """为 user 消息附加 display_content，用于导入后前端展示。"""
        result: List[Dict[str, Any]] = []
        for msg in messages:
            new_msg = dict(msg)
            if new_msg.get("role") == "user":
                content = new_msg.get("content")
                display = unwrap_user_prompt(content)
                if display is not None:
                    new_msg["display_content"] = display
            result.append(new_msg)
        return result

    def _build_workspace_manifest(
        self,
        workspace_files: List[tuple[str, Path]],
    ) -> Dict[str, Any]:
        files: List[Dict[str, Any]] = []
        for relative_path, file_path in workspace_files:
            stat = file_path.stat()
            files.append(
                {
                    "path": relative_path,
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )

        return {
            "files": files,
            "file_count": len(files),
        }

    def _get_session_context(
        self,
        session_id: str,
        user_id: str,
    ) -> tuple[Path, Optional[SessionMetadata]]:
        session_dir = self._session_manager._get_session_dir(session_id, user_id)
        if not session_dir.exists():
            raise SessionExportNotFoundError(f"会话不存在: {user_id}/{session_id}")

        metadata = self._session_manager.get_session(session_id, user_id)
        return session_dir, metadata

    def _scan_workspace_files(
        self,
        session_dir: Path,
    ) -> tuple[List[tuple[str, Path]], List[str]]:
        files = list(self._collect_workspace_files(session_dir))
        skipped_sensitive_files: List[str] = []
        seen_skipped: set[str] = set()

        for file_path in session_dir.rglob("*"):
            if not file_path.is_file():
                continue

            relative_path = file_path.relative_to(session_dir).as_posix()
            if self._is_sensitive_file(relative_path) and relative_path not in seen_skipped:
                seen_skipped.add(relative_path)
                skipped_sensitive_files.append(relative_path)

        return files, skipped_sensitive_files

    def _collect_workspace_files(self, session_dir: Path) -> Iterable[tuple[str, Path]]:
        emitted_paths: set[str] = set()

        for file_path in session_dir.rglob("*"):
            if not file_path.is_file():
                continue

            relative_path = file_path.relative_to(session_dir).as_posix()
            if relative_path.split("/", 1)[0] in INTERNAL_SESSION_DIRS:
                continue
            if self._should_skip_session_file(relative_path):
                continue
            if relative_path in emitted_paths:
                continue

            emitted_paths.add(relative_path)
            yield relative_path, file_path

    def _should_skip_session_file(self, relative_path: str) -> bool:
        path = Path(relative_path)
        file_name = path.name

        if file_name in INTERNAL_SESSION_FILES:
            return True
        if self._is_sensitive_file(relative_path):
            return True
        if file_name.startswith("."):
            return True
        if any(part.startswith(".") for part in path.parts[:-1]):
            return True
        return False

    def _is_sensitive_file(self, relative_path: str) -> bool:
        file_name = Path(relative_path).name.lower()

        if file_name in SENSITIVE_EXACT_FILENAMES:
            return True
        if Path(file_name).suffix.lower() in SENSITIVE_SUFFIXES:
            return True
        return any(token in file_name for token in SENSITIVE_NAME_TOKENS)
