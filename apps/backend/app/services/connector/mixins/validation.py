"""
验证和辅助方法 Mixin

负责数据验证、加密/解密、SQL检查等辅助功能
"""

import logging
import re
from typing import TYPE_CHECKING, Optional

from app.core.encryption import EncryptionError, encryption_service
from app.services.connector.constants import (
    _BLOCKED_SQL_PREFIXES,
    _REMOTE_PERMISSION_ERROR_PATTERNS,
)
from app.services.connector.errors import (
    DatabaseConnectorAccessError,
    DatabaseConnectorPlatformRejectionError,
    DatabaseConnectorRemoteExecutionError,
    DatabaseConnectorRemotePermissionError,
)

if TYPE_CHECKING:
    from app.services.connector import DatabaseConnectorService

logger = logging.getLogger(__name__)


class ValidationMixin:
    """验证和辅助方法功能"""

    def _encrypt_secret(self: "DatabaseConnectorService", value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        return encryption_service.encrypt(value)

    def _decrypt_secret(self: "DatabaseConnectorService", value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        try:
            return encryption_service.decrypt(value)
        except EncryptionError as exc:
            logger.warning("数据库连接器敏感字段解密失败: %s", exc)
            return None

    def _mask_secret(self: "DatabaseConnectorService", value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        if len(value) <= 4:
            return "*" * len(value)
        return f"{value[:2]}***{value[-2:]}"

    def _mask_connection_url(
        self: "DatabaseConnectorService", value: Optional[str]
    ) -> Optional[str]:
        if not value:
            return None
        try:
            return self._redact_error_text(value)
        except Exception:
            return "[REDACTED_SECRET]"

    def _normalize_scope_list(
        self: "DatabaseConnectorService", items: Optional[list[str]]
    ) -> list[str]:
        normalized: list[str] = []
        for item in items or []:
            clean = str(item).strip()
            if not clean or clean in normalized:
                continue
            normalized.append(clean)
        return normalized

    def _redact_error_text(self: "DatabaseConnectorService", text: str | None) -> str | None:
        from app.services.connector.constants import (
            _BEARER_TOKEN_RE,
            _DSN_SECRET_RE,
            _JSON_PASSWORD_FIELD_RE,
            _PASSWORD_FIELD_RE,
        )

        if text is None:
            return None

        def _replace_dsn(match: re.Match[str]) -> str:
            if match.group("password") is None:
                return match.group(0)
            return f"{match.group('scheme')}{match.group('user')}:[REDACTED_SECRET]@"

        redacted = _DSN_SECRET_RE.sub(_replace_dsn, text)
        redacted = _PASSWORD_FIELD_RE.sub(r"\1[REDACTED_SECRET]", redacted)
        redacted = _JSON_PASSWORD_FIELD_RE.sub(r"\1[REDACTED_SECRET]\3", redacted)
        redacted = _BEARER_TOKEN_RE.sub(r"\1[REDACTED_SECRET]", redacted)
        return redacted

    def _is_mysql_driver_available(self: "DatabaseConnectorService") -> bool:
        return self._get_connector_adapter("mysql").is_driver_available()

    def _raise_remote_database_error(
        self: "DatabaseConnectorService",
        exc: Exception,
        *,
        action_label: str,
        fallback_message: str,
    ) -> None:
        if isinstance(exc, DatabaseConnectorAccessError):
            raise exc

        text = self._redact_error_text(str(exc)) or fallback_message
        if self._looks_like_remote_permission_error(text):
            raise DatabaseConnectorRemotePermissionError(
                f"目标数据库账号权限不足，远端数据库拒绝了本次{action_label}: {text}"
            ) from exc

        raise DatabaseConnectorRemoteExecutionError(text or fallback_message) from exc

    def _looks_like_remote_permission_error(self: "DatabaseConnectorService", text: str) -> bool:
        lowered = str(text or "").strip().lower()
        if not lowered:
            return False
        return any(pattern.search(lowered) for pattern in _REMOTE_PERMISSION_ERROR_PATTERNS)

    def _normalize_query_sql(self: "DatabaseConnectorService", sql: str) -> str:
        normalized = str(sql or "").strip()
        if normalized.endswith(";"):
            normalized = normalized[:-1].strip()
        if not normalized:
            raise DatabaseConnectorPlatformRejectionError("SQL 不能为空")
        return normalized

    def _normalize_execute_sql(self: "DatabaseConnectorService", sql: str) -> str:
        normalized = self._normalize_query_sql(sql)
        lowered = normalized.lower()
        if ";" in lowered:
            raise DatabaseConnectorPlatformRejectionError("执行 SQL 不允许多语句")
        if "--" in lowered or "/*" in lowered or "*/" in lowered:
            raise DatabaseConnectorPlatformRejectionError("执行 SQL 不允许注释语句")
        return normalized

    def _validate_readonly_sql(self: "DatabaseConnectorService", sql: str) -> None:
        lowered = sql.lower()
        if ";" in lowered:
            raise DatabaseConnectorPlatformRejectionError("只读查询不允许多语句执行")
        if "--" in lowered or "/*" in lowered or "*/" in lowered:
            raise DatabaseConnectorPlatformRejectionError("只读查询不允许注释语句")

        stripped = lowered.lstrip()
        if any(stripped.startswith(prefix) for prefix in _BLOCKED_SQL_PREFIXES):
            raise DatabaseConnectorPlatformRejectionError("仅允许 SELECT/WITH 只读查询")
        if not (stripped.startswith("select") or stripped.startswith("with")):
            raise DatabaseConnectorPlatformRejectionError("仅允许 SELECT/WITH 只读查询")
