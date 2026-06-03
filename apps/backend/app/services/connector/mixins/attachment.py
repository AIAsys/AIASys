"""
附件管理 Mixin

负责会话级别的数据库连接器挂载管理
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from app.models.database_connector import (
    DatabaseConnector,
    SessionDatabaseAttachment,
)
from app.services.database.database_access_broker import get_connector_credentials_path

if TYPE_CHECKING:
    from app.services.connector import DatabaseConnectorService

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    """返回 UTC ISO 时间字符串。"""
    return datetime.now(timezone.utc).isoformat()


class AttachmentMixin:
    """附件管理功能"""

    def _resolve_session_workspace_id(
        self: "DatabaseConnectorService", user_id: str, session_id: str
    ) -> str | None:
        """从会话元数据解析所属工作区 ID。"""
        session = self.session_manager.get_session(session_id, user_id)
        return session.workspace_id if session else None

    def list_session_attachments(
        self: "DatabaseConnectorService",
        user_id: str,
        session_id: str,
    ) -> list[SessionDatabaseAttachment]:
        """列出会话已挂载的数据库连接器。"""
        self._ensure_session_exists(user_id, session_id)
        workspace_id = self._resolve_session_workspace_id(user_id, session_id)
        payload = self._load_session_attachments(user_id, session_id)
        connectors = {
            connector.connector_id: connector
            for connector in self.list_connectors(user_id, workspace_id=workspace_id)
        }
        attachments: list[SessionDatabaseAttachment] = []
        normalized_items: list[dict[str, Any]] = []
        mutated = False
        for item in payload.get("attachments", []):
            connector = connectors.get(item.get("connector_id", ""))
            if connector is None:
                continue
            normalized_item = self._normalize_attachment_record(item, connector)
            normalized_items.append(normalized_item)
            mutated = mutated or normalized_item != item
            attachments.append(
                SessionDatabaseAttachment(
                    session_id=session_id,
                    connector_id=connector.connector_id,
                    handle=normalized_item["handle"],
                    name=connector.name,
                    db_type=connector.db_type,
                    attached_at=normalized_item["attached_at"],
                )
            )
        if mutated:
            payload["attachments"] = normalized_items
            self._save_session_attachments(user_id, session_id, payload)
        return attachments

    def attach_connector(
        self: "DatabaseConnectorService",
        user_id: str,
        session_id: str,
        connector_id: str,
        *,
        sync_defaults: bool = False,
    ) -> SessionDatabaseAttachment:
        """向会话挂载数据库连接器。"""
        self._ensure_session_exists(user_id, session_id)
        workspace_id = self._resolve_session_workspace_id(user_id, session_id)
        connector = self.get_connector(user_id, connector_id, workspace_id=workspace_id)
        if connector is None:
            raise ValueError("数据库连接器不存在")

        payload = self._load_session_attachments(user_id, session_id)
        for item in payload.get("attachments", []):
            if item.get("connector_id") == connector_id:
                normalized_item = self._normalize_attachment_record(
                    item,
                    connector,
                    sync_defaults=sync_defaults,
                )
                if normalized_item != item:
                    payload["attachments"] = [
                        normalized_item if existing is item else existing
                        for existing in payload.get("attachments", [])
                    ]
                    self._save_session_attachments(user_id, session_id, payload)
                self._rebuild_connector_credentials_file(user_id, session_id)
                return SessionDatabaseAttachment(
                    session_id=session_id,
                    connector_id=connector.connector_id,
                    handle=normalized_item["handle"],
                    name=connector.name,
                    db_type=connector.db_type,
                    attached_at=normalized_item["attached_at"],
                )

        attached_at = _utcnow_iso()
        attachment_record = self._build_attachment_record(
            connector_id=connector_id,
            connector=connector,
            attached_at=attached_at,
        )
        payload.setdefault("attachments", []).append(attachment_record)
        self._save_session_attachments(user_id, session_id, payload)
        self._rebuild_connector_credentials_file(user_id, session_id)
        return SessionDatabaseAttachment(
            session_id=session_id,
            connector_id=connector.connector_id,
            handle=attachment_record["handle"],
            name=connector.name,
            db_type=connector.db_type,
            attached_at=attached_at,
        )

    def detach_connector(
        self: "DatabaseConnectorService",
        user_id: str,
        session_id: str,
        connector_id: str,
    ) -> bool:
        """从会话卸载数据库连接器。"""
        self._ensure_session_exists(user_id, session_id)
        payload = self._load_session_attachments(user_id, session_id)
        original = payload.get("attachments", [])
        filtered = [item for item in original if item.get("connector_id") != connector_id]
        if len(filtered) == len(original):
            return False
        payload["attachments"] = filtered
        self._save_session_attachments(user_id, session_id, payload)
        self._rebuild_connector_credentials_file(user_id, session_id)
        return True

    def clone_session_attachments(
        self: "DatabaseConnectorService",
        *,
        user_id: str,
        source_session_id: str,
        target_session_id: str,
    ) -> list[SessionDatabaseAttachment]:
        """复制来源会话的数据库挂载到目标会话。"""
        self._ensure_session_exists(user_id, source_session_id)
        self._ensure_session_exists(user_id, target_session_id)

        source_workspace_id = self._resolve_session_workspace_id(user_id, source_session_id)
        source_payload = self._load_session_attachments(user_id, source_session_id)
        connectors = {
            connector.connector_id: connector
            for connector in self.list_connectors(user_id, workspace_id=source_workspace_id)
        }
        cloned_records: list[dict[str, Any]] = []
        attachments: list[SessionDatabaseAttachment] = []

        for item in source_payload.get("attachments", []):
            connector = connectors.get(str(item.get("connector_id") or ""))
            if connector is None:
                continue
            normalized_item = self._normalize_attachment_record(item, connector)
            cloned_records.append(normalized_item)
            attachments.append(
                SessionDatabaseAttachment(
                    session_id=target_session_id,
                    connector_id=connector.connector_id,
                    handle=normalized_item["handle"],
                    name=connector.name,
                    db_type=connector.db_type,
                    attached_at=normalized_item["attached_at"],
                )
            )

        self._save_session_attachments(
            user_id,
            target_session_id,
            {
                "session_id": target_session_id,
                "attachments": cloned_records,
            },
        )
        return attachments

    def _build_attachment_record(
        self: "DatabaseConnectorService",
        *,
        connector_id: str,
        connector: DatabaseConnector,
        attached_at: str,
        existing: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        existing = existing or {}
        return {
            "connector_id": connector_id,
            "handle": str(existing.get("handle") or f"connector:{connector_id}"),
            "attached_at": attached_at,
        }

    def _normalize_attachment_record(
        self: "DatabaseConnectorService",
        item: dict[str, Any],
        connector: DatabaseConnector,
        *,
        sync_defaults: bool = False,
    ) -> dict[str, Any]:
        return self._build_attachment_record(
            connector_id=connector.connector_id,
            connector=connector,
            attached_at=str(item.get("attached_at") or _utcnow_iso()),
            existing=None if sync_defaults else item,
        )

    def _rebuild_connector_credentials_file(
        self: "DatabaseConnectorService",
        user_id: str,
        session_id: str,
    ) -> Path | None:
        """根据当前会话挂载的连接器重建凭据配置文件。"""
        path = get_connector_credentials_path(session_id)
        attachments = self.list_session_attachments(user_id, session_id)
        workspace_id = self._resolve_session_workspace_id(user_id, session_id)
        creds: dict[str, Any] = {}
        for att in attachments:
            connector = self.get_connector(user_id, att.connector_id, workspace_id=workspace_id)
            if not connector or not connector.allow_notebook_access:
                continue
            record = self._find_connector_record(user_id, att.connector_id)
            if not record:
                continue
            payload = self._materialize_connector_payload(record)
            creds[att.handle] = {
                "host": payload.get("host"),
                "port": payload.get("port"),
                "database": payload.get("database_name"),
                "username": payload.get("username"),
                "password": payload.get("password"),
                "db_type": payload.get("db_type"),
            }
        if not creds:
            if path.exists():
                path.unlink()
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(creds, ensure_ascii=False, indent=2), encoding="utf-8")
        path.chmod(0o600)
        return path

    def _remove_connector_credentials_file(
        self: "DatabaseConnectorService",
        session_id: str,
    ) -> None:
        """删除会话的凭据配置文件。"""
        path = get_connector_credentials_path(session_id)
        if path.exists():
            path.unlink()

    def _ensure_session_exists(
        self: "DatabaseConnectorService", user_id: str, session_id: str
    ) -> None:
        if self.session_manager.get_session(session_id, user_id) is None:
            raise ValueError("目标会话不存在，无法挂载数据库连接器")

    def _find_connector_record(
        self: "DatabaseConnectorService",
        user_id: str,
        connector_id: str,
    ) -> Optional[dict[str, Any]]:
        payload = self._load_user_config(user_id)
        for record in payload.get("connectors", []):
            if record.get("connector_id") == connector_id:
                return record
        return None
