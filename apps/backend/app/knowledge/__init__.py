"""知识库服务模块（SQLite + sqlite-vec）"""

from .sqlite_kb_service import SQLiteKBService, get_sqlite_kb_service

__all__ = [
    "SQLiteKBService",
    "get_sqlite_kb_service",
]
