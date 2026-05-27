"""
存储管理 Mixin

负责连接器配置和会话挂载的持久化（统一 DuckDB）
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.core.database import (
    DatabaseConnectorORM,
    SessionAttachmentORM,
    db_session,
    engine,
)

if TYPE_CHECKING:
    from app.services.connector import DatabaseConnectorService

logger = logging.getLogger(__name__)
_CONNECTOR_TABLES_READY = False


def _parse_orm_datetime(value: Any) -> datetime | None:
    """把 JSON 时代的 ISO 时间转换成 ORM DateTime 可接受的值。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("忽略无法解析的数据库连接器时间字段: %s", value)
            return None
    else:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _ensure_connector_tables() -> None:
    """确保连接器 ORM 表存在，支持全新 SQLite 数据库直接运行资源测试。"""
    global _CONNECTOR_TABLES_READY
    if _CONNECTOR_TABLES_READY:
        return
    DatabaseConnectorORM.__table__.create(bind=engine, checkfirst=True)
    SessionAttachmentORM.__table__.create(bind=engine, checkfirst=True)
    _CONNECTOR_TABLES_READY = True


class StorageMixin:
    """存储管理功能（DuckDB 版本）"""

    def _load_user_config(self: "DatabaseConnectorService", user_id: str) -> dict[str, Any]:
        """从 DuckDB 加载用户连接器配置，保持 JSON 文件时代的返回结构。"""
        _ensure_connector_tables()
        with db_session() as db:
            try:
                records = (
                    db.query(DatabaseConnectorORM)
                    .filter(DatabaseConnectorORM.user_id == user_id)
                    .all()
                )
                connectors = []
                for r in records:
                    connectors.append(
                        {
                            "connector_id": r.connector_id,
                            "name": r.name,
                            "db_type": r.db_type,
                            "connection_mode": r.connection_mode,
                            "host": r.host,
                            "port": r.port,
                            "database_name": r.database_name,
                            "username": r.username,
                            "password_encrypted": r.password_encrypted,
                            "api_token_encrypted": r.api_token_encrypted,
                            "connection_url_encrypted": r.connection_url_encrypted,
                            "description": r.description,
                            "allow_notebook_access": bool(r.allow_notebook_access),
                            "allowed_schemas": r.allowed_schemas or [],
                            "allowed_tables": r.allowed_tables or [],
                            "query_timeout_seconds": r.query_timeout_seconds,
                            "row_limit": r.row_limit,
                            "last_test_status": r.last_test_status,
                            "last_test_message": r.last_test_message,
                            "last_tested_at": (
                                r.last_tested_at.isoformat() if r.last_tested_at else None
                            ),
                            "created_at": r.created_at.isoformat() if r.created_at else None,
                            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                        }
                    )
                return {"connectors": connectors}
            except Exception as exc:
                logger.warning("加载数据库连接器配置失败: user=%s error=%s", user_id, exc)
                return {"connectors": []}

    def _save_user_config(
        self: "DatabaseConnectorService", user_id: str, payload: dict[str, Any]
    ) -> None:
        """将连接器配置写入 DuckDB（全量替换）。"""
        _ensure_connector_tables()
        with db_session() as db:
            try:
                # 删除该用户所有旧记录
                db.query(DatabaseConnectorORM).filter(
                    DatabaseConnectorORM.user_id == user_id
                ).delete(synchronize_session=False)

                # 插入新记录
                for record in payload.get("connectors", []):
                    orm = DatabaseConnectorORM(
                        connector_id=record.get("connector_id", f"dbc_{uuid4().hex[:16]}"),
                        user_id=user_id,
                        name=record.get("name", ""),
                        db_type=record.get("db_type", "postgres"),
                        connection_mode=record.get("connection_mode", "fields"),
                        host=record.get("host"),
                        port=record.get("port"),
                        database_name=record.get("database_name"),
                        username=record.get("username"),
                        password_encrypted=record.get("password_encrypted"),
                        api_token_encrypted=record.get("api_token_encrypted"),
                        connection_url_encrypted=record.get("connection_url_encrypted"),
                        description=record.get("description"),
                        allow_notebook_access=(
                            1 if record.get("allow_notebook_access", False) else 0
                        ),
                        allowed_schemas=record.get("allowed_schemas", []),
                        allowed_tables=record.get("allowed_tables", []),
                        query_timeout_seconds=record.get("query_timeout_seconds", 15),
                        row_limit=record.get("row_limit", 1000),
                        last_test_status=record.get("last_test_status", "untested"),
                        last_test_message=record.get("last_test_message"),
                        last_tested_at=_parse_orm_datetime(record.get("last_tested_at")),
                        created_at=_parse_orm_datetime(record.get("created_at")),
                        updated_at=_parse_orm_datetime(record.get("updated_at")),
                    )
                    db.add(orm)

                db.commit()
            except Exception as exc:
                db.rollback()
                logger.error("保存数据库连接器配置失败: user=%s error=%s", user_id, exc)
                raise

    def _load_session_attachments(
        self: "DatabaseConnectorService", user_id: str, session_id: str
    ) -> dict[str, Any]:
        """从 DuckDB 加载会话挂载关系，保持 JSON 文件时代的返回结构。"""
        _ensure_connector_tables()
        with db_session() as db:
            try:
                records = (
                    db.query(SessionAttachmentORM)
                    .filter(
                        SessionAttachmentORM.session_id == session_id,
                        SessionAttachmentORM.user_id == user_id,
                    )
                    .all()
                )
                attachments = []
                for r in records:
                    attachments.append(
                        {
                            "connector_id": r.connector_id,
                            "handle": r.handle,
                            "attached_at": r.attached_at.isoformat() if r.attached_at else None,
                        }
                    )
                return {"session_id": session_id, "attachments": attachments}
            except Exception as exc:
                logger.warning(
                    "加载会话数据库挂载失败: user=%s session=%s error=%s",
                    user_id,
                    session_id,
                    exc,
                )
                return {"session_id": session_id, "attachments": []}

    def _save_session_attachments(
        self: "DatabaseConnectorService",
        user_id: str,
        session_id: str,
        payload: dict[str, Any],
    ) -> None:
        """将会话挂载关系写入 DuckDB（全量替换）。"""
        _ensure_connector_tables()
        with db_session() as db:
            try:
                # 删除该会话所有旧记录
                db.query(SessionAttachmentORM).filter(
                    SessionAttachmentORM.session_id == session_id,
                    SessionAttachmentORM.user_id == user_id,
                ).delete(synchronize_session=False)

                # 插入新记录
                for item in payload.get("attachments", []):
                    orm = SessionAttachmentORM(
                        id=f"att_{uuid4().hex[:16]}",
                        user_id=user_id,
                        session_id=session_id,
                        connector_id=item.get("connector_id", ""),
                        handle=item.get("handle"),
                        attached_at=_parse_orm_datetime(item.get("attached_at")),
                    )
                    db.add(orm)

                db.commit()
            except Exception as exc:
                db.rollback()
                logger.error(
                    "保存会话数据库挂载失败: user=%s session=%s error=%s",
                    user_id,
                    session_id,
                    exc,
                )
                raise
