"""
会话管理器核心类

提供文件为基础的会话持久化核心功能
"""

import hashlib
import json
import logging
import os
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from app.utils.path_utils import as_system_path
from uuid import uuid4

from app.models.session import (
    SessionCollaborationPolicy,
    SessionMetadata,
    normalize_collaboration_policy,
)
from app.models.task_profile import (
    normalize_execution_policy,
)
from app.services.history.session_execution_journal import SessionExecutionJournal
from app.services.runtime.session_runtime_state import resolve_effective_runtime_state
from app.services.session.constants import (
    CLEARED_CONTEXT_ARCHIVE_DIR_NAME,
    DISPLAY_HISTORY_FILE_NAME,
    METADATA_FILE_NAME,
)
from app.services.session.files import FileSnapshotMixin
from app.services.session.history import HistoryMixin
from app.services.session.status import StatusMixin
from app.utils.validators import validate_id

logger = logging.getLogger(__name__)

_EXPERT_POLICY_UNSET = object()


def _is_rewrite_visible_history_message(message: dict) -> bool:
    role = message.get("role")
    if role in {"_checkpoint", "_usage", "_system_prompt"}:
        return False
    if role == "user":
        content = message.get("content")
        if isinstance(content, str) and content.strip().startswith("<system-reminder>"):
            return False
    return True


class SessionManager(StatusMixin, HistoryMixin, FileSnapshotMixin):
    """会话管理器 - 文件存储"""

    def __init__(
        self,
        base_dir: Path,
    ):
        self._metadata_lock = threading.Lock()
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_dir(self, session_id: str, user_id: str) -> Path:
        """获取会话目录路径"""
        validate_id(user_id, "user_id")
        validate_id(session_id, "session_id")
        return self.base_dir / user_id / session_id

    def _write_metadata_atomic(self, session_dir: Path, data: dict) -> None:
        """原子写入 metadata.json，防止并发竞态导致文件损坏。"""
        with self._metadata_lock:
            meta_path = session_dir / METADATA_FILE_NAME
            fd, temp_path = tempfile.mkstemp(dir=as_system_path(str(session_dir)), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, as_system_path(str(meta_path)))
            except Exception:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass
                raise

    def create_session(
        self, session_id: str, user_id: str, title: str | None = "新会话", **kwargs
    ) -> SessionMetadata:
        """创建新会话"""
        session_dir = self._get_session_dir(session_id, user_id)

        # 检查是否是重新创建已存在的会话
        is_recreate = session_dir.exists() and (session_dir / METADATA_FILE_NAME).exists()
        existing_hidden = False
        existing_title = None
        existing_execution_policy = None
        existing_source = None
        existing_auto_task_id = None
        existing_automation_continuation_id = None
        existing_automation_continuation_target_kind = None
        existing_preferred_model_id = None
        existing_enabled_expert_role_ids = None
        existing_expert_role_tool_ids = None
        existing_collaboration_policy = None
        existing_context_tokens = None
        existing_budget = None
        if is_recreate:
            # 保留现有的 hidden 标记和标题
            try:
                existing_meta = self.get_session(session_id, user_id)
                if existing_meta:
                    existing_hidden = getattr(existing_meta, "exclude_from_user_history", False)
                    existing_title = getattr(existing_meta, "title", None)
                    existing_execution_policy = getattr(
                        existing_meta,
                        "execution_policy",
                        None,
                    )
                    existing_source = getattr(existing_meta, "source", None)
                    existing_auto_task_id = getattr(
                        existing_meta,
                        "auto_task_id",
                        None,
                    )
                    existing_automation_continuation_id = getattr(
                        existing_meta,
                        "automation_continuation_id",
                        None,
                    )
                    existing_automation_continuation_target_kind = getattr(
                        existing_meta,
                        "automation_continuation_target_kind",
                        None,
                    )
                    existing_preferred_model_id = getattr(
                        existing_meta,
                        "preferred_model_id",
                        None,
                    )
                    existing_enabled_expert_role_ids = getattr(
                        existing_meta,
                        "enabled_expert_role_ids",
                        None,
                    )
                    existing_expert_role_tool_ids = getattr(
                        existing_meta,
                        "expert_role_tool_ids",
                        None,
                    )
                    existing_collaboration_policy = getattr(
                        existing_meta,
                        "collaboration_policy",
                        None,
                    )
                    existing_context_tokens = getattr(
                        existing_meta,
                        "context_tokens",
                        None,
                    )
                    existing_budget = getattr(existing_meta, "budget", None)
            except FileNotFoundError:
                pass
            except Exception:
                logger.warning("读取旧会话元数据失败", exc_info=True)

        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / ".aiasys/session").mkdir(parents=True, exist_ok=True)

        now = datetime.now().isoformat()

        # 如果是重新创建且原会话是隐藏的，保留隐藏标记
        if existing_hidden and "exclude_from_user_history" not in kwargs:
            kwargs["exclude_from_user_history"] = True

        # 重建已有 session 时，如果调用方没有显式改写任务工作层配置，
        # 则保留原来的 execution_policy，避免 runtime rebuild
        # 把 auto_explore 等运行行为意外重置回默认 chat_assist。
        if is_recreate:
            if kwargs.get("execution_policy") is None and existing_execution_policy is not None:
                kwargs["execution_policy"] = existing_execution_policy
            if kwargs.get("source") is None and existing_source is not None:
                kwargs["source"] = existing_source
            if kwargs.get("auto_task_id") is None and existing_auto_task_id is not None:
                kwargs["auto_task_id"] = existing_auto_task_id
            if (
                kwargs.get("automation_continuation_id") is None
                and existing_automation_continuation_id is not None
            ):
                kwargs["automation_continuation_id"] = existing_automation_continuation_id
            if (
                kwargs.get("automation_continuation_target_kind") is None
                and existing_automation_continuation_target_kind is not None
            ):
                kwargs["automation_continuation_target_kind"] = (
                    existing_automation_continuation_target_kind
                )
            if kwargs.get("preferred_model_id") is None and existing_preferred_model_id is not None:
                kwargs["preferred_model_id"] = existing_preferred_model_id
            if (
                kwargs.get("enabled_expert_role_ids") is None
                and existing_enabled_expert_role_ids is not None
            ):
                kwargs["enabled_expert_role_ids"] = list(existing_enabled_expert_role_ids)
            if (
                kwargs.get("expert_role_tool_ids") is None
                and existing_expert_role_tool_ids is not None
            ):
                kwargs["expert_role_tool_ids"] = {
                    role_id: list(tool_ids)
                    for role_id, tool_ids in existing_expert_role_tool_ids.items()
                }
            if (
                kwargs.get("collaboration_policy") is None
                and existing_collaboration_policy is not None
            ):
                kwargs["collaboration_policy"] = normalize_collaboration_policy(
                    existing_collaboration_policy
                )
            # 保留已保存的精确 token 占用和 budget，避免 runtime rebuild 把它重置为默认值
            if (
                kwargs.get("context_tokens") is None
                and existing_context_tokens is not None
                and existing_context_tokens > 0
            ):
                kwargs["context_tokens"] = existing_context_tokens
            if kwargs.get("budget") is None and existing_budget is not None:
                kwargs["budget"] = existing_budget

        # 如果是重新创建且原会话有标题（不是默认标题），保留原有标题
        generic_titles = ("新会话", "新会话", "新任务")
        effective_title = title or "新会话"
        if is_recreate and existing_title:
            # 如果传入的是默认标题但已有非默认标题，保留原有标题
            if effective_title in generic_titles and existing_title not in (
                *generic_titles,
                "",
                None,
            ):
                effective_title = existing_title
            # 如果传入的是非默认标题，使用传入的标题（允许显式更新）
            elif effective_title not in generic_titles:
                pass
            # 否则使用原有标题
            else:
                effective_title = existing_title

        kwargs["execution_policy"] = normalize_execution_policy(
            kwargs.get("execution_policy"),
        )

        workspace_id = kwargs.pop("workspace_id", None)
        status = kwargs.pop("status", "draft")
        metadata = SessionMetadata(
            session_id=session_id,
            title=effective_title,
            created_at=now,
            updated_at=now,
            status=status,
            workspace_id=workspace_id,
            **kwargs,
        )

        # 保存元数据
        self._write_metadata_atomic(session_dir, metadata.model_dump())

        journal = SessionExecutionJournal(session_dir, session_id)
        if is_recreate:
            journal.initialize_structure()
            self._write_history_snapshot(
                session_dir,
                self._read_history_snapshot(session_dir),
            )
        else:
            journal.reset_for_rebuild(clear_conversation=True)
            self._write_history_snapshot(session_dir, [])

        if metadata.recovery_policy:
            journal.update_recovery_config(recovery_policy=metadata.recovery_policy)

        logger.info(f"创建会话: user={user_id}, session={session_id}")
        return metadata

    def get_session(self, session_id: str, user_id: str) -> Optional[SessionMetadata]:
        """获取会话元数据（只读，不做 eager write-back 避免竞态）"""
        try:
            session_dir = self._get_session_dir(session_id, user_id)
            meta_path = session_dir / METADATA_FILE_NAME

            if not meta_path.exists():
                return None

            data = json.loads(meta_path.read_text(encoding="utf-8"))
            message_count = data.get("message_count", 0)
            completed_message_count = data.get("completed_message_count")
            derived_status = self._derive_status(
                message_count, data.get("status"), completed_message_count
            )
            # 派生状态只用于返回，不写回文件，避免并发 get_session 竞态覆盖
            data["status"] = derived_status
            if derived_status != "completed":
                data["completed_at"] = None
                data["completed_message_count"] = None
            return SessionMetadata(**data)

        except Exception as e:
            logger.error("获取会话失败: %s", e)
            return None

    def delete_session(self, session_id: str, user_id: str) -> bool:
        """删除会话"""
        try:
            session_dir = self._get_session_dir(session_id, user_id)
            if not session_dir.exists():
                return False

            shutil.rmtree(as_system_path(str(session_dir)))
            logger.info("删除会话: user=%s, session=%s", user_id, session_id)

            # 清理 MemoryResolver 缓存，避免已删除会话的缓存残留
            try:
                from app.services.memory.resolver import invalidate_resolver_cache

                invalidate_resolver_cache(user_id, session_id)
            except Exception:
                pass

            return True
        except Exception as e:
            logger.error("删除会话失败: %s", e)
            return False

    def detach_session_for_deletion(
        self,
        session_id: str,
        user_id: str,
    ) -> Path | None:
        """把会话目录移到 `.trash`，供后台异步物理删除。"""
        session_dir = self._get_session_dir(session_id, user_id)
        if not session_dir.exists():
            return None

        trash_dir = self.base_dir / ".trash" / user_id
        trash_dir.mkdir(parents=True, exist_ok=True)
        detached_path = trash_dir / f"{session_id}-{uuid4().hex[:8]}"
        shutil.move(as_system_path(str(session_dir)), as_system_path(str(detached_path)))
        logger.info(
            "会话目录已 detach 到回收区: user=%s, session=%s, path=%s",
            user_id,
            session_id,
            detached_path,
        )
        return detached_path

    def purge_detached_session(self, detached_path: Path) -> bool:
        """物理删除已 detach 的会话目录。"""
        target = Path(detached_path)
        if not target.exists():
            return False

        shutil.rmtree(as_system_path(str(target)))
        logger.info("已物理删除 detach 会话目录: %s", target)
        return True

    def list_user_sessions(self, user_id: str, include_drafts: bool = False) -> List[dict]:
        """列出用户的所有会话"""
        validate_id(user_id, "user_id")
        user_dir = self.base_dir / user_id

        if not user_dir.exists():
            return []

        sessions = []
        for session_dir in user_dir.iterdir():
            if not session_dir.is_dir():
                continue
            if session_dir.name.startswith("."):
                continue
            if not (session_dir / METADATA_FILE_NAME).is_file():
                continue

            session_id = session_dir.name
            metadata = self.get_session(session_id, user_id)
            if metadata is None:
                continue

            if (
                not include_drafts
                and metadata.status == "draft"
                and self.is_blank_draft_session(session_id, user_id)
            ):
                continue

            # 排除标记为 internal/hidden 的会话
            if getattr(metadata, "exclude_from_user_history", False):
                continue

            sessions.append(
                {
                    "session_id": metadata.session_id,
                    "title": metadata.title,
                    "status": metadata.status,
                    "created_at": metadata.created_at,
                    "updated_at": metadata.updated_at,
                    "message_count": metadata.message_count,
                    "source": getattr(metadata, "source", None),
                    "auto_task_id": getattr(metadata, "auto_task_id", None),
                }
            )

        # 按更新时间排序
        sessions.sort(key=lambda x: x["updated_at"] or "", reverse=True)
        return sessions

    def is_blank_draft_session(self, session_id: str, user_id: str) -> bool:
        """判断会话是否为空白草稿。"""
        metadata = self.get_session(session_id, user_id)
        if metadata is None:
            return False
        if metadata.status != "draft":
            return False
        if int(metadata.message_count or 0) > 0:
            return False

        execution_summary = self.get_execution_summary(session_id, user_id)
        if int(execution_summary.get("execution_record_count") or 0) > 0:
            return False
        if self.list_cleared_context_archives(session_id, user_id):
            return False
        return True

    def _update_message_count(self, session_id: str, user_id: str, count: int):
        """更新会话消息计数"""
        try:
            metadata = self.get_session(session_id, user_id)
            if metadata:
                metadata.message_count = count
                metadata.updated_at = datetime.now().isoformat()
                session_dir = self._get_session_dir(session_id, user_id)
                self._write_metadata_atomic(session_dir, metadata.model_dump())
        except Exception as e:
            logger.warning("更新消息计数失败: %s", e)

    def update_session_env(
        self,
        session_id: str,
        user_id: str,
        env_id: Optional[str],
        sandbox_mode: Optional[str] = None,
        code_timeout: Optional[int] = None,
    ) -> bool:
        """更新会话绑定的运行环境与执行配置。"""
        try:
            metadata = self.get_session(session_id, user_id)
            if not metadata:
                logger.warning(
                    "会话元数据不存在，无法更新环境: user=%s, session=%s, env=%s",
                    user_id,
                    session_id,
                    env_id,
                )
                return False

            metadata.env_id = env_id
            if sandbox_mode:
                metadata.sandbox_mode = sandbox_mode
            if code_timeout is not None:
                metadata.code_timeout = code_timeout
            metadata.updated_at = datetime.now().isoformat()

            session_dir = self._get_session_dir(session_id, user_id)
            self._write_metadata_atomic(session_dir, metadata.model_dump())

            logger.info(
                "会话环境已更新: user=%s, session=%s, env=%s, sandbox_mode=%s, code_timeout=%s",
                user_id,
                session_id,
                env_id,
                metadata.sandbox_mode,
                metadata.code_timeout,
            )
            return True
        except Exception as e:
            logger.error(
                "更新会话环境失败: user=%s, session=%s, env=%s, error=%s",
                user_id,
                session_id,
                env_id,
                e,
            )
            return False

    def get_execution_records(
        self,
        session_id: str,
        user_id: str,
        limit: int = 50,
    ) -> list[dict]:
        """读取 session execution journal 记录。"""
        session_dir = self._get_session_dir(session_id, user_id)
        if not session_dir.exists():
            return []

        journal = SessionExecutionJournal(session_dir, session_id)
        return [record.model_dump() for record in journal.list_records(limit=limit)]

    def get_execution_summary(
        self,
        session_id: str,
        user_id: str,
    ) -> dict:
        """读取 session execution journal 摘要。"""
        session_dir = self._get_session_dir(session_id, user_id)
        if not session_dir.exists():
            return {
                "has_execution_journal": False,
                "execution_record_count": 0,
                "last_execution_status": None,
                "last_execution_record_id": None,
                "recovery_policy": None,
                "idempotency_policy": None,
                "requires_confirmation_for_replay": True,
                "last_runtime_state": None,
            }

        journal = SessionExecutionJournal(session_dir, session_id)
        self._backfill_execution_journal_from_sdk_context(session_dir, session_id)
        summary = journal.get_summary()
        metadata = self.get_session(session_id, user_id)
        summary["last_runtime_state"] = resolve_effective_runtime_state(
            session_dir=session_dir,
            session_id=session_id,
            user_id=user_id,
            sandbox_mode=getattr(metadata, "sandbox_mode", None),
            env_id=getattr(metadata, "env_id", None),
            last_runtime_state=summary.get("last_runtime_state"),
        )
        return summary

    def _backfill_execution_journal_from_sdk_context(
        self,
        session_dir: Path,
        session_id: str,
    ) -> None:
        """从旧 SDK context.jsonl 回填本地执行记录。"""
        journal = SessionExecutionJournal(session_dir, session_id)
        if journal.list_records(limit=1):
            return

        context_path = session_dir / ".aiasys/session" / session_id / "context.jsonl"
        if not context_path.exists():
            return

        try:
            messages: list[dict[str, Any]] = []
            for line in context_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                if isinstance(payload, dict):
                    messages.append(payload)
        except Exception:
            logger.debug(
                "回填 execution journal 时读取 SDK context 失败: %s",
                context_path,
                exc_info=True,
            )
            return

        pending_calls: dict[str, dict[str, str | None]] = {}
        for message in messages:
            role = message.get("role")
            if role == "assistant":
                tool_calls = message.get("tool_calls")
                if not isinstance(tool_calls, list):
                    continue
                for call in tool_calls:
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function")
                    if not isinstance(function, dict):
                        continue
                    tool_name = str(function.get("name") or "").strip()
                    if tool_name not in {"LocalIPythonBox"}:
                        continue
                    call_id = str(call.get("id") or "").strip()
                    if not call_id:
                        continue
                    code = ""
                    raw_arguments = function.get("arguments")
                    if isinstance(raw_arguments, str):
                        try:
                            parsed_arguments = json.loads(raw_arguments)
                            if isinstance(parsed_arguments, dict):
                                code = str(parsed_arguments.get("code") or "")
                        except Exception:
                            code = ""
                    elif isinstance(raw_arguments, dict):
                        code = str(raw_arguments.get("code") or "")
                    pending_calls[call_id] = {"tool_name": tool_name, "code": code}
                continue

            if role != "tool":
                continue
            call_id = str(message.get("tool_call_id") or "").strip()
            pending = pending_calls.pop(call_id, None)
            if pending is None:
                continue
            now = datetime.now().isoformat()
            journal.append_record(
                code=str(pending.get("code") or ""),
                started_at=now,
                finished_at=now,
                status="completed",
                stdout=str(message.get("content") or ""),
                origin_source="sdk_context_backfill",
                tool_name=str(pending.get("tool_name") or "LocalIPythonBox"),
                request_id=call_id,
            )

    def reset_session_history(
        self,
        session_id: str,
        user_id: str,
    ) -> None:
        """清理旧历史对话与执行 sidecar，重置为新结构起点。"""
        session_dir = self._get_session_dir(session_id, user_id)
        journal = SessionExecutionJournal(session_dir, session_id)
        journal.reset_for_rebuild(clear_conversation=True)

        # history.json 由 reset_for_rebuild 清空，不需要额外操作 context.jsonl
        metadata = self.get_session(session_id, user_id)
        if metadata:
            journal.update_recovery_config(recovery_policy=metadata.recovery_policy)
            metadata.message_count = 0
            metadata.status = "draft"
            metadata.completed_at = None
            metadata.completed_message_count = None
            metadata.updated_at = datetime.now().isoformat()

            self._write_metadata_atomic(session_dir, metadata.model_dump())

    def archive_cleared_context(
        self,
        session_id: str,
        user_id: str,
        messages: list[dict],
        *,
        reason: str = "clear_context",
    ) -> dict:
        """把 clear 前的可见历史与相关 sidecar 归档到带时间戳的文件。"""
        session_dir = self._get_session_dir(session_id, user_id)
        sidecar_session_dir = session_dir / ".aiasys/session" / session_id
        archive_dir = session_dir / ".aiasys/session" / CLEARED_CONTEXT_ARCHIVE_DIR_NAME
        archive_dir.mkdir(parents=True, exist_ok=True)

        archived_at = datetime.now().isoformat()
        archive_token = archived_at.replace(":", "-")
        normalized_reason = (
            reason if reason in {"clear_context", "message_rewritten"} else "clear_context"
        )
        archive_suffix = (
            "message-rewritten" if normalized_reason == "message_rewritten" else "clear-context"
        )
        archive_payload = {
            "archived_at": archived_at,
            "reason": normalized_reason,
            "messages": messages,
        }
        archive_path = archive_dir / f"{archive_token}-{archive_suffix}.json"
        archive_path.write_text(
            json.dumps(archive_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if normalized_reason == "clear_context":
            display_history_path = sidecar_session_dir / DISPLAY_HISTORY_FILE_NAME
            if display_history_path.exists():
                shutil.copy2(
                    as_system_path(str(display_history_path)),
                    as_system_path(
                        str(archive_dir / f"{archive_token}-{DISPLAY_HISTORY_FILE_NAME}")
                    ),
                )
                display_history_path.write_text("", encoding="utf-8")

        if normalized_reason == "clear_context":
            history_path = self._get_history_snapshot_path(session_dir)
            if history_path.exists():
                shutil.copy2(
                    as_system_path(str(history_path)),
                    as_system_path(str(archive_dir / f"{archive_token}-history.json")),
                )
            self._write_history_snapshot(session_dir, [])

        return {
            "archived_at": archived_at,
            "archive_file": archive_path.name,
        }

    def _build_history_message_id(
        self,
        session_id: str,
        index: int,
        message: dict,
    ) -> str:
        """为缺少 id 的历史消息生成稳定 id。"""
        existing_id = message.get("id")
        if isinstance(existing_id, str) and existing_id.strip():
            return existing_id.strip()

        role = str(message.get("role") or "message")
        content = message.get("content")
        signature = json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha1(
            f"{session_id}:{index}:{role}:{signature}".encode("utf-8")
        ).hexdigest()[:12]
        return f"{role}-{index}-{digest}"

    def _read_display_history_entries(self, sidecar_session_dir: Path) -> list[dict]:
        display_history_path = sidecar_session_dir / DISPLAY_HISTORY_FILE_NAME
        if not display_history_path.exists():
            return []

        entries: list[dict] = []
        for line in display_history_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                entries.append(payload)
        return entries

    def _write_display_history_entries(
        self,
        sidecar_session_dir: Path,
        entries: list[dict],
    ) -> None:
        sidecar_session_dir.mkdir(parents=True, exist_ok=True)
        display_history_path = sidecar_session_dir / DISPLAY_HISTORY_FILE_NAME
        content = "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries)
        display_history_path.write_text(content, encoding="utf-8")

    def assign_history_message_ids(
        self,
        session_id: str,
        messages: list[dict],
    ) -> list[dict]:
        """为 API 返回的历史消息补稳定 id。"""
        assigned: list[dict] = []
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            updated = dict(message)
            updated["id"] = self._build_history_message_id(
                session_id,
                index,
                updated,
            )
            assigned.append(updated)
        return assigned

    def rewrite_history_from_message(
        self,
        session_id: str,
        user_id: str,
        *,
        message_id: str,
        content: str,
        confirm_drop_tail: bool,
    ) -> dict:
        """从指定用户消息处重写当前聊天上下文。"""
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("消息内容不能为空")

        session_dir = self._get_session_dir(session_id, user_id)
        sidecar_session_dir = session_dir / ".aiasys/session" / session_id
        context_messages = self._read_history_snapshot(session_dir)
        if not context_messages:
            raise LookupError("当前会话没有可重写的聊天历史")

        visible_message_ids: dict[int, str] = {}
        visible_context_messages: list[dict] = []
        visible_context_indexes: list[int] = []
        for index, message in enumerate(context_messages):
            if not isinstance(message, dict) or not _is_rewrite_visible_history_message(message):
                continue
            visible_context_messages.append(message)
            visible_context_indexes.append(index)

        for visible_index, message in enumerate(
            self.assign_history_message_ids(session_id, visible_context_messages)
        ):
            source_index = visible_context_indexes[visible_index]
            visible_message_ids[source_index] = str(message.get("id") or "")

        target_index: int | None = None
        for index, message in enumerate(context_messages):
            if visible_message_ids.get(index) == message_id:
                if message.get("role") != "user":
                    raise ValueError("只能重写用户消息")
                target_index = index
                break

        if target_index is None:
            raise LookupError("未找到要重写的用户消息")

        tail_messages = context_messages[target_index + 1 :]
        if tail_messages and not confirm_drop_tail:
            raise ValueError("重写该消息会删除后续对话上下文，需要确认")

        target_message = dict(context_messages[target_index])
        target_message["id"] = visible_message_ids.get(target_index, message_id)
        original_content = target_message.get("content")
        if isinstance(original_content, list):
            rewritten_content = []
            text_replaced = False
            for item in original_content:
                if isinstance(item, dict) and item.get("type") == "text" and not text_replaced:
                    updated_item = dict(item)
                    updated_item["text"] = normalized_content
                    rewritten_content.append(updated_item)
                    text_replaced = True
                    continue
                rewritten_content.append(item)
            if not text_replaced:
                rewritten_content.insert(0, {"type": "text", "text": normalized_content})
            target_message["content"] = rewritten_content
        else:
            target_message["content"] = normalized_content
        target_message["timestamp"] = datetime.now().isoformat()
        target_message["rewritten_from"] = message_id

        next_context_messages = [
            *context_messages[:target_index],
            target_message,
        ]

        display_entries = self._read_display_history_entries(sidecar_session_dir)
        user_seen = -1
        target_user_position = -1
        for index, message in enumerate(context_messages):
            if index > target_index:
                break
            if message.get("role") == "user":
                user_seen += 1
                if index == target_index:
                    target_user_position = user_seen
                    break

        next_display_entries = display_entries
        if target_user_position >= 0:
            kept_display_entries = display_entries[: target_user_position + 1]
            if len(kept_display_entries) <= target_user_position:
                missing_count = target_user_position + 1 - len(kept_display_entries)
                kept_display_entries.extend({} for _ in range(missing_count))
            target_entry = dict(kept_display_entries[target_user_position] or {})
            target_entry["role"] = "user"
            target_entry["content"] = normalized_content
            target_entry["timestamp"] = target_message["timestamp"]
            if "transport_content" in target_entry:
                transport_content = target_entry.get("transport_content")
                if isinstance(transport_content, list):
                    next_transport = []
                    text_replaced = False
                    for item in transport_content:
                        if (
                            isinstance(item, dict)
                            and item.get("type") == "text"
                            and not text_replaced
                        ):
                            updated_item = dict(item)
                            updated_item["text"] = normalized_content
                            next_transport.append(updated_item)
                            text_replaced = True
                            continue
                        next_transport.append(item)
                    target_entry["transport_content"] = next_transport
                else:
                    target_entry["transport_content"] = target_message.get("content")
            kept_display_entries[target_user_position] = target_entry
            next_display_entries = kept_display_entries

        history_snapshot = self._read_history_snapshot(session_dir)
        snapshot_message_ids: dict[int, str] = {}
        visible_snapshot_messages: list[dict] = []
        visible_snapshot_indexes: list[int] = []
        for index, message in enumerate(history_snapshot):
            if not isinstance(message, dict) or not _is_rewrite_visible_history_message(message):
                continue
            visible_snapshot_messages.append(message)
            visible_snapshot_indexes.append(index)

        for visible_index, message in enumerate(
            self.assign_history_message_ids(session_id, visible_snapshot_messages)
        ):
            source_index = visible_snapshot_indexes[visible_index]
            snapshot_message_ids[source_index] = str(message.get("id") or "")

        snapshot_target_index: int | None = None
        for index, message in enumerate(history_snapshot):
            if snapshot_message_ids.get(index) == message_id:
                snapshot_target_index = index
                break
        if snapshot_target_index is not None:
            snapshot_target = dict(history_snapshot[snapshot_target_index])
            snapshot_target["content"] = target_message["content"]
            snapshot_target["display_content"] = normalized_content
            snapshot_target["timestamp"] = target_message["timestamp"]
            snapshot_target["rewritten_from"] = message_id
            next_history_snapshot = [
                *history_snapshot[:snapshot_target_index],
                snapshot_target,
            ]
        else:
            next_history_snapshot = next_context_messages

        archive: dict | None = None
        if tail_messages:
            archive = self.archive_cleared_context(
                session_id,
                user_id,
                tail_messages,
                reason="message_rewritten",
            )

        self._write_history_snapshot(session_dir, next_context_messages)
        self._write_display_history_entries(sidecar_session_dir, next_display_entries)
        self._write_history_snapshot(session_dir, next_history_snapshot)

        metadata = self.get_session(session_id, user_id)
        if metadata:
            metadata.message_count = len(next_history_snapshot)
            metadata.status = self._derive_status(
                metadata.message_count,
                None,
                None,
            )
            metadata.completed_at = None
            metadata.completed_message_count = None
            metadata.updated_at = datetime.now().isoformat()
            self._write_metadata_atomic(session_dir, metadata.model_dump())

        try:
            SessionExecutionJournal(session_dir, session_id).update_recovery_config(
                last_runtime_state="refresh_required",
            )
        except Exception as exc:
            logger.warning("标记重写后的运行态失败: %s", exc)

        return {
            "message_id": target_message["id"],
            "content": normalized_content,
            "dropped_count": len(tail_messages),
            "archive": archive,
            "messages": self.assign_history_message_ids(
                session_id,
                next_context_messages,
            ),
        }

    def list_cleared_context_archives(
        self,
        session_id: str,
        user_id: str,
    ) -> list[dict]:
        """读取按时间顺序归档的 clear 前可见历史。"""
        session_dir = self._get_session_dir(session_id, user_id)
        archive_dir = session_dir / ".aiasys/session" / CLEARED_CONTEXT_ARCHIVE_DIR_NAME
        if not archive_dir.exists():
            return []

        archives: list[dict] = []
        for archive_path in sorted(archive_dir.glob("*-clear-context.json")):
            try:
                payload = json.loads(archive_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("读取上下文归档失败: path=%s error=%s", archive_path, exc)
                continue

            if not isinstance(payload, dict):
                continue
            if payload.get("reason") != "clear_context":
                continue

            messages = payload.get("messages")
            if not isinstance(messages, list):
                messages = []

            archives.append(
                {
                    "archived_at": payload.get("archived_at"),
                    "messages": messages,
                    "archive_file": archive_path.name,
                }
            )

        return archives

    def list_context_rewrite_archives(
        self,
        session_id: str,
        user_id: str,
    ) -> list[dict]:
        """读取消息重写时截断的历史归档，不并入当前聊天历史。"""
        session_dir = self._get_session_dir(session_id, user_id)
        archive_dir = session_dir / ".aiasys/session" / CLEARED_CONTEXT_ARCHIVE_DIR_NAME
        if not archive_dir.exists():
            return []

        archives: list[dict] = []
        for archive_path in sorted(archive_dir.glob("*-message-rewritten.json")):
            try:
                payload = json.loads(archive_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("读取消息重写归档失败: path=%s error=%s", archive_path, exc)
                continue

            if not isinstance(payload, dict):
                continue
            if payload.get("reason") != "message_rewritten":
                continue

            messages = payload.get("messages")
            if not isinstance(messages, list):
                messages = []

            archives.append(
                {
                    "archived_at": payload.get("archived_at"),
                    "messages": messages,
                    "archive_file": archive_path.name,
                }
            )

        return archives

    def list_execution_maintenance_markers(
        self,
        session_id: str,
        user_id: str,
    ) -> list[dict]:
        """返回用于前端展示分段的维护事件 marker。"""
        markers: list[dict] = []
        for archive in self.list_cleared_context_archives(session_id, user_id):
            occurred_at = archive.get("archived_at")
            if not occurred_at:
                continue

            archive_file = archive.get("archive_file") or occurred_at
            markers.append(
                {
                    "marker_id": f"context_cleared:{archive_file}",
                    "type": "context_cleared",
                    "occurred_at": occurred_at,
                    "label": "已清理当前上下文",
                    "description": "以下为清理前保留的较早执行证据。",
                }
            )
        for archive in self.list_context_rewrite_archives(session_id, user_id):
            occurred_at = archive.get("archived_at")
            if not occurred_at:
                continue

            archive_file = archive.get("archive_file") or occurred_at
            markers.append(
                {
                    "marker_id": f"message_rewritten:{archive_file}",
                    "type": "message_rewritten",
                    "occurred_at": occurred_at,
                    "label": "已编辑并重发对话",
                    "description": "较早的后续对话只作为执行证据保留。",
                }
            )

        markers.sort(key=lambda item: item.get("occurred_at") or "", reverse=True)
        return markers

    def mark_context_cleared(
        self,
        session_id: str,
        user_id: str,
    ) -> None:
        """标记当前会话上下文已清空，但不删除 UI 历史快照或工作区文件。"""
        metadata = self.get_session(session_id, user_id)
        if not metadata:
            return

        session_dir = self._get_session_dir(session_id, user_id)
        metadata.message_count = 0
        metadata.status = "draft"
        metadata.completed_at = None
        metadata.completed_message_count = None
        metadata.updated_at = datetime.now().isoformat()

        self._write_metadata_atomic(session_dir, metadata.model_dump())

    def update_session_recovery_policy(
        self,
        session_id: str,
        user_id: str,
        recovery_policy: str,
    ) -> bool:
        """更新会话恢复策略，并同步到 execution journal。"""
        try:
            metadata = self.get_session(session_id, user_id)
            if not metadata:
                logger.warning(
                    "会话元数据不存在，无法更新恢复策略: user=%s, session=%s, policy=%s",
                    user_id,
                    session_id,
                    recovery_policy,
                )
                return False

            metadata.recovery_policy = recovery_policy
            metadata.updated_at = datetime.now().isoformat()

            session_dir = self._get_session_dir(session_id, user_id)
            self._write_metadata_atomic(session_dir, metadata.model_dump())

            journal = SessionExecutionJournal(session_dir, session_id)
            journal.update_recovery_config(recovery_policy=recovery_policy)

            logger.info(
                "会话恢复策略已更新: user=%s, session=%s, policy=%s",
                user_id,
                session_id,
                recovery_policy,
            )
            return True
        except Exception as e:
            logger.error(
                "更新会话恢复策略失败: user=%s, session=%s, policy=%s, error=%s",
                user_id,
                session_id,
                recovery_policy,
                e,
            )
            return False

    def update_session_title(
        self,
        session_id: str,
        user_id: str,
        title: str,
    ) -> bool:
        """更新会话标题"""
        try:
            metadata = self.get_session(session_id, user_id)
            if not metadata:
                logger.warning(
                    "会话元数据不存在，无法更新标题: user=%s, session=%s",
                    user_id,
                    session_id,
                )
                return False

            metadata.title = title
            metadata.updated_at = datetime.now().isoformat()

            session_dir = self._get_session_dir(session_id, user_id)
            self._write_metadata_atomic(session_dir, metadata.model_dump())

            logger.info(
                "会话标题已更新: user=%s, session=%s, title=%s",
                user_id,
                session_id,
                title,
            )
            return True
        except Exception as e:
            logger.error(
                "更新会话标题失败: user=%s, session=%s, title=%s, error=%s",
                user_id,
                session_id,
                title,
                e,
            )
            return False

    def update_session_budget(
        self,
        session_id: str,
        user_id: str,
        budget: Any | None,
    ) -> bool:
        """更新会话的 budget 状态。"""
        try:
            metadata = self.get_session(session_id, user_id)
            if metadata is None:
                return False
            from app.models.session import SessionBudget

            if budget is None:
                metadata.budget = None
            elif isinstance(budget, SessionBudget):
                metadata.budget = budget
            else:
                metadata.budget = SessionBudget(**budget)
            metadata.updated_at = datetime.now().isoformat()

            session_dir = self._get_session_dir(session_id, user_id)
            self._write_metadata_atomic(session_dir, metadata.model_dump())
            return True
        except Exception as e:
            logger.error(
                "更新会话 budget 失败: user=%s, session=%s, error=%s",
                user_id,
                session_id,
                e,
            )
            return False

    def update_session_preferred_model_id(
        self,
        session_id: str,
        user_id: str,
        preferred_model_id: str | None,
    ) -> bool:
        """更新当前会话私有模型覆盖。"""
        try:
            metadata = self.get_session(session_id, user_id)
            if not metadata:
                logger.warning(
                    "会话元数据不存在，无法更新模型覆盖: user=%s, session=%s",
                    user_id,
                    session_id,
                )
                return False

            metadata.preferred_model_id = preferred_model_id
            metadata.updated_at = datetime.now().isoformat()

            session_dir = self._get_session_dir(session_id, user_id)
            self._write_metadata_atomic(session_dir, metadata.model_dump())

            logger.info(
                "会话模型覆盖已更新: user=%s, session=%s, preferred_model_id=%s",
                user_id,
                session_id,
                preferred_model_id,
            )
            return True
        except Exception as e:
            logger.error(
                "更新会话模型覆盖失败: user=%s, session=%s, preferred_model_id=%s, error=%s",
                user_id,
                session_id,
                preferred_model_id,
                e,
            )
            return False

    def update_task_profile(
        self,
        *,
        session_id: str,
        user_id: str,
        execution_policy=None,
    ) -> SessionMetadata | None:
        """更新任务工作层配置。"""
        try:
            metadata = self.get_session(session_id, user_id)
            if not metadata:
                logger.warning(
                    "会话元数据不存在，无法更新任务配置: user=%s, session=%s",
                    user_id,
                    session_id,
                )
                return None

            metadata.execution_policy = normalize_execution_policy(
                execution_policy if execution_policy is not None else metadata.execution_policy,
            )
            metadata.updated_at = datetime.now().isoformat()

            session_dir = self._get_session_dir(session_id, user_id)
            self._write_metadata_atomic(session_dir, metadata.model_dump())

            logger.info(
                "会话任务配置已更新: user=%s, session=%s, execution_policy=%s",
                user_id,
                session_id,
                metadata.execution_policy.mode.value,
            )
            return metadata
        except Exception as e:
            logger.error(
                "更新会话任务配置失败: user=%s, session=%s, error=%s",
                user_id,
                session_id,
                e,
            )
            return None

    def update_session_expert_policy(
        self,
        *,
        session_id: str,
        user_id: str,
        enabled_expert_role_ids: list[str] | None | object = _EXPERT_POLICY_UNSET,
        expert_role_tool_ids: dict[str, list[str]] | None | object = _EXPERT_POLICY_UNSET,
        collaboration_policy: (
            SessionCollaborationPolicy | dict[str, Any] | None | object
        ) = _EXPERT_POLICY_UNSET,
    ) -> SessionMetadata | None:
        """更新当前会话的专家策略和协作节点运行策略。"""
        try:
            metadata = self.get_session(session_id, user_id)
            if not metadata:
                logger.warning(
                    "会话元数据不存在，无法更新专家策略: user=%s, session=%s",
                    user_id,
                    session_id,
                )
                return None

            if enabled_expert_role_ids is not _EXPERT_POLICY_UNSET:
                metadata.enabled_expert_role_ids = (
                    list(enabled_expert_role_ids) if enabled_expert_role_ids is not None else None
                )
            if expert_role_tool_ids is not _EXPERT_POLICY_UNSET:
                metadata.expert_role_tool_ids = (
                    {role_id: list(tool_ids) for role_id, tool_ids in expert_role_tool_ids.items()}
                    if expert_role_tool_ids is not None
                    else None
                )
            if collaboration_policy is not _EXPERT_POLICY_UNSET:
                metadata.collaboration_policy = normalize_collaboration_policy(collaboration_policy)
            metadata.updated_at = datetime.now().isoformat()

            session_dir = self._get_session_dir(session_id, user_id)
            self._write_metadata_atomic(session_dir, metadata.model_dump())

            logger.info(
                "会话专家策略已更新: user=%s, session=%s, enabled_roles=%s, role_tool_ids=%s, collaboration_policy=%s",
                user_id,
                session_id,
                metadata.enabled_expert_role_ids,
                metadata.expert_role_tool_ids,
                metadata.collaboration_policy.model_dump(),
            )
            return metadata
        except Exception as e:
            logger.error(
                "更新会话专家策略失败: user=%s, session=%s, error=%s",
                user_id,
                session_id,
                e,
            )
            return None

    def fork_session_history(
        self,
        *,
        source_session_id: str,
        target_session_id: str,
        user_id: str,
    ) -> bool:
        """复制 source 会话的当前历史到 target 会话，作为 Fork 对话起点。"""
        try:
            source_dir = self._get_session_dir(source_session_id, user_id)
            target_dir = self._get_session_dir(target_session_id, user_id)
            if not source_dir.exists() or not target_dir.exists():
                return False

            source_history = self._read_history_snapshot(source_dir)
            self._write_history_snapshot(target_dir, source_history)

            source_sidecar_dir = source_dir / ".aiasys/session" / source_session_id
            target_sidecar_dir = target_dir / ".aiasys/session" / target_session_id
            target_sidecar_dir.mkdir(parents=True, exist_ok=True)

            for filename in (DISPLAY_HISTORY_FILE_NAME,):
                source_path = source_sidecar_dir / filename
                target_path = target_sidecar_dir / filename
                if source_path.exists():
                    shutil.copy2(as_system_path(str(source_path)), as_system_path(str(target_path)))

            self._update_message_count(
                target_session_id,
                user_id,
                len(source_history),
            )
            return True
        except Exception as e:
            logger.error(
                "Fork 会话历史失败: user=%s source=%s target=%s error=%s",
                user_id,
                source_session_id,
                target_session_id,
                e,
            )
            return False
