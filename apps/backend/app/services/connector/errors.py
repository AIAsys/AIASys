"""
数据库连接器异常类

定义所有与数据库连接器相关的异常类型。
"""


class DatabaseConnectorAccessError(Exception):
    """数据库连接器访问错误基类。"""

    audit_reason = "connector_error"


class DatabaseConnectorPlatformRejectionError(DatabaseConnectorAccessError, ValueError):
    """平台或会话侧的访问拒绝。"""

    audit_reason = "platform_rejected"


class DatabaseConnectorNotFoundError(DatabaseConnectorPlatformRejectionError):
    """数据库连接器不存在。"""

    audit_reason = "connector_not_found"


class DatabaseConnectorAttachmentMissingError(DatabaseConnectorPlatformRejectionError):
    """当前会话未挂载数据库连接器。"""

    audit_reason = "attachment_missing"


class DatabaseConnectorCapabilityDeniedError(DatabaseConnectorPlatformRejectionError):
    """当前连接器能力上限不支持动作。"""

    audit_reason = "capability_denied"


class DatabaseConnectorGrantDeniedError(DatabaseConnectorPlatformRejectionError):
    """当前会话 grants 不允许动作。"""

    audit_reason = "grant_denied"


class DatabaseConnectorApprovalRequiredError(DatabaseConnectorPlatformRejectionError):
    """动作需要人工审批。"""

    audit_reason = "approval_required"


class DatabaseConnectorApprovalRejectedError(DatabaseConnectorPlatformRejectionError):
    """人工审批已拒绝。"""

    audit_reason = "approval_rejected"


class DatabaseConnectorApprovalTimeoutError(DatabaseConnectorPlatformRejectionError):
    """人工审批等待超时。"""

    audit_reason = "approval_timeout"


class DatabaseConnectorRemotePermissionError(DatabaseConnectorAccessError, RuntimeError):
    """目标数据库账号/角色权限不足。"""

    audit_reason = "remote_permission_denied"


class DatabaseConnectorRemoteExecutionError(DatabaseConnectorAccessError, RuntimeError):
    """远端数据库执行失败。"""

    audit_reason = "remote_execution_error"
