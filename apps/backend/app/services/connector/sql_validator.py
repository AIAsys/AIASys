"""
SQL 验证工具

提供 SQL 语句安全检查功能
"""

import logging
from typing import Optional

from app.services.connector.constants import (
    _BLOCKED_SQL_PREFIXES,
    _DDL_SQL_PREFIXES,
    _IDENTIFIER_RE,
    _WRITE_SQL_PREFIXES,
)

logger = logging.getLogger(__name__)


def is_safe_identifier(name: str) -> bool:
    """
    检查标识符是否安全

    Args:
        name: 标识符名称

    Returns:
        是否安全
    """
    return bool(_IDENTIFIER_RE.match(name))


def validate_table_name(table_name: str) -> bool:
    """
    验证表名是否合法

    Args:
        table_name: 表名

    Returns:
        是否合法
    """
    return is_safe_identifier(table_name)


def validate_column_name(column_name: str) -> bool:
    """
    验证列名是否合法

    Args:
        column_name: 列名

    Returns:
        是否合法
    """
    return is_safe_identifier(column_name)


def get_sql_statement_type(sql: str) -> Optional[str]:
    """
    获取 SQL 语句类型

    Args:
        sql: SQL 语句

    Returns:
        语句类型: "read", "write", "ddl", "blocked" 或 None
    """
    normalized = sql.strip().lower()

    # 检查是否被阻止
    for prefix in _BLOCKED_SQL_PREFIXES:
        if normalized.startswith(prefix):
            return "blocked"

    # 检查是否为 DDL
    for prefix in _DDL_SQL_PREFIXES:
        if normalized.startswith(prefix):
            return "ddl"

    # 检查是否为写入操作
    for prefix in _WRITE_SQL_PREFIXES:
        if normalized.startswith(prefix):
            return "write"

    # 默认为读取操作
    return "read"


def is_readonly_sql(sql: str) -> bool:
    """
    检查 SQL 是否为只读

    Args:
        sql: SQL 语句

    Returns:
        是否只读
    """
    stmt_type = get_sql_statement_type(sql)
    return stmt_type == "read"
