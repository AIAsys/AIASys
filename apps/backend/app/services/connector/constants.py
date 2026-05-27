"""
数据库连接器常量
"""

import re

# 配置文件名
CONNECTOR_CONFIG_FILE = "database_connectors.json"
SESSION_ATTACHMENT_FILE = "database_connectors.json"

# 正则表达式 - 敏感信息脱敏
_DSN_SECRET_RE = re.compile(
    r"(?P<scheme>[a-z][a-z0-9+.\-]*://)(?P<user>[^:/?#]+)(?::(?P<password>[^@/?#]*))?@",
    re.IGNORECASE,
)
_PASSWORD_FIELD_RE = re.compile(r"(?i)(password\s*[:=]\s*)([^,\s]+)")
_JSON_PASSWORD_FIELD_RE = re.compile(r'(?i)("password"\s*:\s*")([^"]+)(")')
_BEARER_TOKEN_RE = re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)([^\s,]+)")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# SQL 前缀常量
_BLOCKED_SQL_PREFIXES = (
    "insert",
    "update",
    "delete",
    "drop",
    "truncate",
    "alter",
    "create",
    "replace",
    "merge",
    "grant",
    "revoke",
    "call",
    "execute",
    "do",
)

_DDL_SQL_PREFIXES: tuple[str, ...] = ("create", "alter", "drop", "truncate")
_WRITE_SQL_PREFIXES: tuple[str, ...] = ("insert", "update", "delete", "replace", "merge")

# 权限映射
_ACTION_TO_GRANT: dict[str, str] = {
    "list_tables": "schema_read",
    "describe_table": "schema_read",
    "query": "data_read",
    "execute": "data_write",
}

_SUPPORTED_GRANTS: tuple[str, ...] = (
    "schema_read",
    "data_read",
    "data_write",
    "ddl",
)

# 远程权限错误模式
_REMOTE_PERMISSION_ERROR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"permission denied", re.IGNORECASE),
    re.compile(r"insufficient privilege", re.IGNORECASE),
    re.compile(r"access denied", re.IGNORECASE),
    re.compile(r"command denied to user", re.IGNORECASE),
    re.compile(r"must be owner of", re.IGNORECASE),
    re.compile(r"not authorized", re.IGNORECASE),
    re.compile(r"requires .+ privilege", re.IGNORECASE),
)
