"""
数据库连接器服务核心

职责：
- 管理用户级连接器配置
- 加密保存数据库密码 / URL
- 提供连接测试能力
- 管理会话级连接器挂载

使用 Mixin 模式组织功能：
- StorageMixin: 存储管理（加载/保存）
- AttachmentMixin: 会话附件管理
- QueryMixin: 查询操作
- ExecutionMixin: 执行操作（含审批）
- MetadataMixin: 元数据查询
- AdapterMixin: 适配器管理
- ValidationMixin: 验证和辅助方法
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

from app.core.config import WORKSPACE_DIR
from app.core.database import SessionAttachmentORM, db_session
from app.models.database_connector import (
    DEFAULT_CONNECTOR_PORTS,
    DatabaseConnector,
    DatabaseConnectorCapability,
    DatabaseConnectorDraft,
    DatabaseConnectorTestResult,
    UpdateDatabaseConnectorRequest,
    get_connector_family,
)
from app.services.connector.errors import DatabaseConnectorNotFoundError
from app.services.connector.mixins import (
    AdapterMixin,
    AttachmentMixin,
    ExecutionMixin,
    MetadataMixin,
    QueryMixin,
    StorageMixin,
    ValidationMixin,
)

if TYPE_CHECKING:
    from app.services.session import SessionManager

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    """返回 UTC ISO 时间字符串。"""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ConnectorAccessContext:
    connector_id: str
    handle: str
    audit_id: str
    attached_at: str
    connector_record: dict[str, Any]
    connector_payload: dict[str, Any]


class DatabaseConnectorService(
    StorageMixin,
    AttachmentMixin,
    QueryMixin,
    ExecutionMixin,
    MetadataMixin,
    AdapterMixin,
    ValidationMixin,
):
    """数据库连接器服务"""

    def __init__(
        self,
        workspace_root: Path = WORKSPACE_DIR,
        session_manager: Optional[SessionManager] = None,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        if session_manager is not None:
            self.session_manager = session_manager
        else:
            # 延迟导入避免循环
            from app.services.session import SessionManager

            self.session_manager = SessionManager(self.workspace_root)
        self._connector_adapters = self._build_connector_adapters()

    # ==================== 能力查询 ====================

    def list_capabilities(self) -> list[DatabaseConnectorCapability]:
        """返回平台支持的数据库类型能力。"""
        mysql_driver_available = self._is_mysql_driver_available()
        mysql_note = None
        if not mysql_driver_available:
            mysql_note = "当前环境缺少 PyMySQL，MySQL 连接测试暂不可用"

        return [
            DatabaseConnectorCapability(
                db_type="postgres",
                connector_family=get_connector_family("postgres"),
                label="PostgreSQL",
                driver_available=True,
                driver_name="psycopg2",
            ),
            DatabaseConnectorCapability(
                db_type="mysql",
                connector_family=get_connector_family("mysql"),
                label="MySQL",
                driver_available=mysql_driver_available,
                driver_name="pymysql",
                note=mysql_note,
            ),
            DatabaseConnectorCapability(
                db_type="influxdb3",
                connector_family=get_connector_family("influxdb3"),
                label="InfluxDB 3",
                readonly_enforced=True,
                driver_available=True,
                driver_name="http-api",
                note="基于 /api/v3/query_sql 的 query-only 接入",
            ),
        ]

    # ==================== 连接器 CRUD ====================

    def list_connectors(self, user_id: str) -> list[DatabaseConnector]:
        """列出指定用户的数据库连接器。"""
        payload = self._load_user_config(user_id)
        connectors = [self._to_public_connector(record) for record in payload.get("connectors", [])]
        return sorted(connectors, key=lambda item: item.updated_at, reverse=True)

    def get_connector(self, user_id: str, connector_id: str) -> Optional[DatabaseConnector]:
        """获取单个连接器。"""
        record = self._find_connector_record(user_id, connector_id)
        if record is None:
            return None
        return self._to_public_connector(record)

    def create_connector(self, user_id: str, request: DatabaseConnectorDraft) -> DatabaseConnector:
        """创建数据库连接器。"""
        payload = self._load_user_config(user_id)
        now = _utcnow_iso()
        record = self._normalize_connector_record(
            request.model_dump(),
            connector_id=f"dbc_{uuid4().hex[:16]}",
            created_at=now,
            updated_at=now,
            last_test_status="untested",
            last_test_message=None,
            last_tested_at=None,
        )
        payload.setdefault("connectors", []).append(record)
        self._save_user_config(user_id, payload)
        return self._to_public_connector(record)

    def update_connector(
        self,
        user_id: str,
        connector_id: str,
        request: UpdateDatabaseConnectorRequest,
    ) -> Optional[DatabaseConnector]:
        """更新数据库连接器。"""
        payload = self._load_user_config(user_id)
        updates = request.model_dump(exclude_unset=True)

        for index, existing in enumerate(payload.get("connectors", [])):
            if existing.get("connector_id") != connector_id:
                continue

            merged_payload = self._merge_connector_record(existing, updates)
            draft = DatabaseConnectorDraft(**merged_payload)
            normalized = self._normalize_connector_record(
                draft.model_dump(),
                connector_id=connector_id,
                created_at=existing.get("created_at"),
                updated_at=_utcnow_iso(),
                last_test_status="untested",
                last_test_message=None,
                last_tested_at=None,
            )
            payload["connectors"][index] = normalized
            self._save_user_config(user_id, payload)
            self._rebuild_connector_credentials_for_user_connector(
                user_id,
                connector_id,
            )
            return self._to_public_connector(normalized)

        return None

    def delete_connector(self, user_id: str, connector_id: str) -> bool:
        """删除数据库连接器，并清理所有会话挂载。"""
        payload = self._load_user_config(user_id)
        original_connectors = payload.get("connectors", [])
        filtered = [
            record for record in original_connectors if record.get("connector_id") != connector_id
        ]

        if len(filtered) == len(original_connectors):
            return False

        payload["connectors"] = filtered
        self._save_user_config(user_id, payload)
        affected_session_ids = self._list_connector_session_ids(connector_id)
        self._remove_connector_from_all_sessions(user_id, connector_id)
        for session_id in affected_session_ids:
            self._rebuild_connector_credentials_file(user_id, session_id)
        return True

    # ==================== 连接测试 ====================

    def test_connector_draft(self, request: DatabaseConnectorDraft) -> DatabaseConnectorTestResult:
        """测试尚未保存的连接器草稿。"""
        draft_payload = request.model_dump()
        return self._run_connection_test(
            request.db_type,
            request.connection_mode,
            draft_payload,
        )

    def test_connector(
        self, user_id: str, connector_id: str
    ) -> Optional[DatabaseConnectorTestResult]:
        """测试已保存连接器，并回写最近测试状态。"""
        payload = self._load_user_config(user_id)

        for record in payload.get("connectors", []):
            if record.get("connector_id") != connector_id:
                continue

            connector_payload = self._materialize_connector_payload(record)
            result = self._run_connection_test(
                record["db_type"],
                record["connection_mode"],
                connector_payload,
            )
            record["last_test_status"] = "passed" if result.success else "failed"
            record["last_test_message"] = result.message
            record["last_tested_at"] = _utcnow_iso()
            record["updated_at"] = record["last_tested_at"]
            self._save_user_config(user_id, payload)
            return result

        return None

    # ==================== 记录处理 ====================

    def _merge_connector_record(
        self, existing: dict[str, Any], updates: dict[str, Any]
    ) -> dict[str, Any]:
        materialized = self._materialize_connector_payload(existing)
        merged = {
            "name": materialized.get("name"),
            "db_type": materialized.get("db_type"),
            "connection_mode": materialized.get("connection_mode"),
            "host": materialized.get("host"),
            "port": materialized.get("port"),
            "database_name": materialized.get("database_name"),
            "username": materialized.get("username"),
            "password": materialized.get("password"),
            "api_token": materialized.get("api_token"),
            "connection_url": materialized.get("connection_url"),
            "description": materialized.get("description"),
            "allow_notebook_access": materialized.get("allow_notebook_access", False),
            "allowed_schemas": materialized.get("allowed_schemas", []),
            "allowed_tables": materialized.get("allowed_tables", []),
            "query_timeout_seconds": materialized.get("query_timeout_seconds", 15),
            "row_limit": materialized.get("row_limit", 1000),
        }
        merged.update(updates)
        if merged.get("connection_mode") == "fields" and merged.get("port") is None:
            merged["port"] = DEFAULT_CONNECTOR_PORTS[merged["db_type"]]
        return merged

    def _normalize_connector_record(
        self,
        payload: dict[str, Any],
        *,
        connector_id: str,
        created_at: Optional[str],
        updated_at: str,
        last_test_status: str,
        last_test_message: Optional[str],
        last_tested_at: Optional[str],
    ) -> dict[str, Any]:
        allowed_schemas = self._normalize_scope_list(payload.get("allowed_schemas"))
        allowed_tables = self._normalize_scope_list(payload.get("allowed_tables"))
        description = payload.get("description")
        allow_notebook_access = bool(payload.get("allow_notebook_access", False))
        password = payload.get("password")
        api_token = payload.get("api_token")
        connection_url = payload.get("connection_url")
        return {
            "connector_id": connector_id,
            "name": payload["name"].strip(),
            "db_type": payload["db_type"],
            "connection_mode": payload["connection_mode"],
            "host": payload.get("host"),
            "port": payload.get("port"),
            "database_name": payload.get("database_name"),
            "username": payload.get("username"),
            "password_encrypted": self._encrypt_secret(password),
            "api_token_encrypted": self._encrypt_secret(api_token),
            "connection_url_encrypted": self._encrypt_secret(connection_url),
            "description": description,
            "allow_notebook_access": allow_notebook_access,
            "allowed_schemas": allowed_schemas,
            "allowed_tables": allowed_tables,
            "query_timeout_seconds": payload.get("query_timeout_seconds", 15),
            "row_limit": payload.get("row_limit", 1000),
            "last_test_status": last_test_status,
            "last_test_message": last_test_message,
            "last_tested_at": last_tested_at,
            "created_at": created_at or _utcnow_iso(),
            "updated_at": updated_at,
        }

    def _materialize_connector_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "connector_id": record["connector_id"],
            "name": record["name"],
            "db_type": record["db_type"],
            "connection_mode": record["connection_mode"],
            "host": record.get("host"),
            "port": record.get("port"),
            "database_name": record.get("database_name"),
            "username": record.get("username"),
            "password": self._decrypt_secret(record.get("password_encrypted")),
            "api_token": self._decrypt_secret(record.get("api_token_encrypted")),
            "connection_url": self._decrypt_secret(record.get("connection_url_encrypted")),
            "description": record.get("description"),
            "allow_notebook_access": bool(record.get("allow_notebook_access", False)),
            "allowed_schemas": self._normalize_scope_list(record.get("allowed_schemas")),
            "allowed_tables": self._normalize_scope_list(record.get("allowed_tables")),
            "query_timeout_seconds": int(record.get("query_timeout_seconds", 15)),
            "row_limit": int(record.get("row_limit", 1000)),
        }

    def _to_public_connector(self, record: dict[str, Any]) -> DatabaseConnector:
        password = self._decrypt_secret(record.get("password_encrypted"))
        api_token = self._decrypt_secret(record.get("api_token_encrypted"))
        connection_url = self._decrypt_secret(record.get("connection_url_encrypted"))
        return DatabaseConnector(
            connector_id=record["connector_id"],
            name=record["name"],
            db_type=record["db_type"],
            connector_family=get_connector_family(record["db_type"]),
            connection_mode=record["connection_mode"],
            host=record.get("host"),
            port=record.get("port"),
            database_name=record.get("database_name"),
            username=record.get("username"),
            description=record.get("description"),
            allow_notebook_access=bool(record.get("allow_notebook_access", False)),
            allowed_schemas=self._normalize_scope_list(record.get("allowed_schemas")),
            allowed_tables=self._normalize_scope_list(record.get("allowed_tables")),
            query_timeout_seconds=int(record.get("query_timeout_seconds", 15)),
            row_limit=int(record.get("row_limit", 1000)),
            has_password=bool(password),
            has_api_token=bool(api_token),
            has_connection_url=bool(connection_url),
            password_masked=self._mask_secret(password),
            api_token_masked=self._mask_secret(api_token),
            connection_url_masked=self._mask_connection_url(connection_url),
            last_test_status=record.get("last_test_status", "untested"),
            last_test_message=record.get("last_test_message"),
            last_tested_at=record.get("last_tested_at"),
            created_at=record.get("created_at", _utcnow_iso()),
            updated_at=record.get("updated_at", _utcnow_iso()),
        )

    def _list_connector_session_ids(self, connector_id: str) -> list[str]:
        """列出引用指定连接器的会话。"""
        with db_session() as db:
            return [
                str(session_id)
                for (session_id,) in (
                    db.query(SessionAttachmentORM.session_id)
                    .filter(SessionAttachmentORM.connector_id == connector_id)
                    .distinct()
                    .all()
                )
                if session_id
            ]

    def _rebuild_connector_credentials_for_user_connector(
        self,
        user_id: str,
        connector_id: str,
    ) -> None:
        """重建所有引用该连接器的会话级 Notebook 凭据文件。"""
        for session_id in self._list_connector_session_ids(connector_id):
            self._rebuild_connector_credentials_file(user_id, session_id)

    def _remove_connector_from_all_sessions(self, user_id: str, connector_id: str) -> None:
        """从所有会话挂载中移除指定连接器（DuckDB 查询）。"""
        for session_id in self._list_connector_session_ids(connector_id):
            attachment_payload = self._load_session_attachments(user_id, session_id)
            original = attachment_payload.get("attachments", [])
            filtered = [item for item in original if item.get("connector_id") != connector_id]
            if len(filtered) == len(original):
                continue
            attachment_payload["attachments"] = filtered
            self._save_session_attachments(user_id, session_id, attachment_payload)

    # ==================== 上下文解析 ====================

    def resolve_attachment_action_context(
        self,
        *,
        user_id: str,
        session_id: str,
        connector_id: str,
        action: str,
    ) -> ConnectorAccessContext:
        connector_record, connector_payload, attachment_item = self._resolve_attached_connector(
            user_id=user_id,
            session_id=session_id,
            connector_id=connector_id,
        )

        return ConnectorAccessContext(
            connector_id=connector_id,
            handle=str(attachment_item["handle"]),
            audit_id=f"dba_{uuid4().hex[:16]}",
            attached_at=str(attachment_item["attached_at"]),
            connector_record=connector_record,
            connector_payload=connector_payload,
        )

    def _resolve_attached_connector(
        self,
        *,
        user_id: str,
        session_id: str,
        connector_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        attachment_payload = self._load_session_attachments(user_id, session_id)
        connector_record = self._find_connector_record(user_id, connector_id)
        if connector_record is None:
            raise DatabaseConnectorNotFoundError("数据库连接器不存在")
        connector = self._to_public_connector(connector_record)
        normalized_items: list[dict[str, Any]] = []
        target_attachment: Optional[dict[str, Any]] = None
        mutated = False
        for item in attachment_payload.get("attachments", []):
            item_connector_id = item.get("connector_id")
            if not item_connector_id:
                continue
            normalized_item = item
            if item_connector_id == connector_id:
                normalized_item = self._normalize_attachment_record(item, connector)
                target_attachment = normalized_item
                mutated = mutated or normalized_item != item
            normalized_items.append(normalized_item)

        if target_attachment is None:
            # 数据库连接器已改为全局资源，未显式挂载时自动生成默认权限的 attachment
            target_attachment = self._build_attachment_record(
                connector_id=connector_id,
                connector=connector,
                attached_at=_utcnow_iso(),
            )

        if mutated:
            attachment_payload["attachments"] = normalized_items
            self._save_session_attachments(user_id, session_id, attachment_payload)

        connector_payload = self._materialize_connector_payload(connector_record)
        return connector_record, connector_payload, target_attachment
