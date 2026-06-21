"""会话对话导入服务。

将 session_conversation_export JSON 恢复为新会话，用于调试/查看对话记录。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from app.models.workspace import WorkspaceConversationSummary
from app.services.history.session_history_projection import unwrap_user_prompt
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService
from app.utils.ids import generate_conversation_id
from app.utils.path_utils import as_system_path

logger = logging.getLogger(__name__)


class SessionImportError(ValueError):
    """导入格式或内容错误。"""


class SessionImportService:
    """从 session_conversation_export JSON 恢复会话对话。"""

    def __init__(
        self,
        workspace_root: Path,
        session_manager: SessionManager,
        registry: WorkspaceRegistryService,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.session_manager = session_manager
        self.registry = registry

    def import_conversation(
        self,
        *,
        user_id: str,
        workspace_id: str,
        json_bytes: bytes,
    ) -> WorkspaceConversationSummary:
        """导入会话对话，创建新会话并追加到工作区。

        Returns:
            新建会话的 WorkspaceConversationSummary。
        """
        payload = self._parse_payload(json_bytes)
        session_meta = payload.get("session") or {}
        messages = payload.get("messages") or []

        if not isinstance(messages, list):
            raise SessionImportError("messages 必须是数组")

        title = str(session_meta.get("title") or "导入的对话")
        conversation_id = generate_conversation_id(self.workspace_root / user_id)
        session_id = conversation_id
        now = datetime.now().isoformat()

        # 创建工作区/会话上下文目录
        workspace_dir = self.workspace_root / user_id / workspace_id
        session_dir = self.workspace_root / user_id / session_id
        ensure_workspace_layout = getattr(self.registry, "_ensure_workspace_context_files", None)

        # 创建 session 元数据；恢复时 env_id/sandbox_mode 不绑定原环境
        self.session_manager.create_session(
            session_id=session_id,
            user_id=user_id,
            title=title,
            workspace_id=workspace_id,
        )

        try:
            # 写入 history.json（原始消息）
            raw_messages = self._normalize_messages_for_history(messages)
            self.session_manager.sync_messages_to_history(
                session_id=session_id,
                user_id=user_id,
                messages=raw_messages,
            )

            # 重建 display_history.jsonl
            display_entries = self._build_display_entries(messages)
            self._write_display_history(session_dir, session_id, display_entries)

            # 更新会话元数据时间
            metadata = self.session_manager.get_session(session_id, user_id)
            if metadata:
                metadata.updated_at = now
                metadata.status = "active"
                self.session_manager._write_metadata_atomic(session_dir, metadata.model_dump())

            # 注册到工作区 conversations.json
            conv_payload = {
                "conversation_id": conversation_id,
                "session_id": session_id,
                "title": title,
                "execution_policy": metadata.execution_policy.model_dump(mode="json")
                if metadata and metadata.execution_policy
                else None,
                "created_at": now,
                "updated_at": now,
                "source": "imported_conversation",
                "conversation_type": session_meta.get("conversation_type") or "chat",
            }
            existing = self.registry._read_conversation_payloads(user_id, workspace_id)
            existing.append(conv_payload)
            self.registry._write_conversation_payloads(user_id, workspace_id, existing)
            self.registry._write_session_index(user_id, session_id, workspace_id)

            if ensure_workspace_layout is not None:
                ensure_workspace_layout(workspace_dir, title=title)

            return self.registry._build_conversation_summary(user_id, workspace_id, conv_payload)
        except Exception as exc:
            # 清理失败的半成品
            if Path(as_system_path(str(session_dir))).exists():
                import shutil

                shutil.rmtree(as_system_path(str(session_dir)), ignore_errors=True)
            raise SessionImportError(f"恢复会话失败: {exc}") from exc

    def _parse_payload(self, json_bytes: bytes) -> Dict[str, Any]:
        try:
            payload = json.loads(json_bytes.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise SessionImportError("JSON 格式错误") from exc
        except UnicodeDecodeError as exc:
            raise SessionImportError("文件编码错误，仅支持 UTF-8") from exc

        if not isinstance(payload, dict):
            raise SessionImportError("JSON 顶层必须是对象")

        feature = payload.get("feature")
        version = payload.get("version")
        if feature != "session_conversation_export":
            raise SessionImportError(f"不支持的导出格式: {feature}")
        if version != 1:
            raise SessionImportError(f"不支持的版本: {version}")

        return payload

    def _normalize_messages_for_history(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """移除导入 JSON 中的展示层字段，保留 history.json 原始格式。"""
        result: List[Dict[str, Any]] = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            normalized = dict(msg)
            # display_content 是展示层字段，不应写入 history.json
            normalized.pop("display_content", None)
            normalized.pop("transport_content", None)
            # _tool_result_backfilled 是导出追溯标记，可保留
            result.append(normalized)
        return result

    def _build_display_entries(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从导入消息重建 display_history.jsonl 条目。"""
        entries: List[Dict[str, Any]] = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            if msg.get("role") != "user":
                continue

            content = msg.get("content")
            display_content = msg.get("display_content")
            if display_content is None and isinstance(content, str):
                display_content = unwrap_user_prompt(content)

            entry: Dict[str, Any] = {
                "role": "user",
                "content": display_content if display_content is not None else content,
                "timestamp": msg.get("timestamp") or datetime.now().isoformat(),
            }
            if isinstance(content, str):
                entry["transport_content"] = content
            entries.append(entry)
        return entries

    def _write_display_history(
        self,
        session_dir: Path,
        session_id: str,
        entries: List[Dict[str, Any]],
    ) -> None:
        sidecar_dir = session_dir / ".aiasys" / "session" / session_id
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        display_history_path = sidecar_dir / "display_history.jsonl"
        Path(as_system_path(display_history_path)).write_text(
            "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries),
            encoding="utf-8",
        )
