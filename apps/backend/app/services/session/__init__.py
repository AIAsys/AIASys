"""
会话管理服务模块

提供文件为基础的会话持久化
"""

from app.services.session.constants import (
    ACTIVE_SESSION_STATE_DIR_NAME,
    CLEARED_CONTEXT_ARCHIVE_DIR_NAME,
    DISPLAY_HISTORY_FILE_NAME,
    EXCLUDE_FROM_USER_HISTORY_MARKER,
    HISTORY_SNAPSHOT_FILE_NAME,
    METADATA_FILE_NAME,
)
from app.services.session.core import SessionManager
from app.services.session.files import FileSnapshotMixin
from app.services.session.history import HistoryMixin
from app.services.session.status import StatusMixin
from app.services.session.task_plan import (
    PLAN_MODE_ALLOWED_TOOL_NAMES,
    PLAN_WORKFLOW_GUIDANCE,
    TASK_MANAGEMENT_PROTOCOL,
    SessionTaskPlanStore,
    TaskItem,
)

__all__ = [
    "SessionManager",
    "StatusMixin",
    "HistoryMixin",
    "FileSnapshotMixin",
    "TaskItem",
    "SessionTaskPlanStore",
    "TASK_MANAGEMENT_PROTOCOL",
    "PLAN_WORKFLOW_GUIDANCE",
    "PLAN_MODE_ALLOWED_TOOL_NAMES",
    # 常量
    "DISPLAY_HISTORY_FILE_NAME",
    "CLEARED_CONTEXT_ARCHIVE_DIR_NAME",
    "ACTIVE_SESSION_STATE_DIR_NAME",
    "HISTORY_SNAPSHOT_FILE_NAME",
    "EXCLUDE_FROM_USER_HISTORY_MARKER",
    "METADATA_FILE_NAME",
]
