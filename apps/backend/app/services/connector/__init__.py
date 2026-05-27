"""
Connector 服务模块

包含数据库连接器的所有功能：
- 错误定义 (errors)
- 常量定义 (constants)
- 安全工具 (security)
- SQL 验证 (sql_validator)
- 服务核心 (core) 和 Mixin 模块
"""

# 从 constants 重新导出常量（可选）
from app.services.connector.constants import (
    CONNECTOR_CONFIG_FILE,
    SESSION_ATTACHMENT_FILE,
)

# 从 core 重新导出主要类
from app.services.connector.core import (
    ConnectorAccessContext,
    DatabaseConnectorService,
)

# 从 errors 重新导出异常类
from app.services.connector.errors import (
    DatabaseConnectorAccessError,
    DatabaseConnectorApprovalRejectedError,
    DatabaseConnectorApprovalRequiredError,
    DatabaseConnectorApprovalTimeoutError,
    DatabaseConnectorAttachmentMissingError,
    DatabaseConnectorCapabilityDeniedError,
    DatabaseConnectorGrantDeniedError,
    DatabaseConnectorNotFoundError,
    DatabaseConnectorPlatformRejectionError,
    DatabaseConnectorRemoteExecutionError,
    DatabaseConnectorRemotePermissionError,
)

# 从 security 重新导出安全工具
from app.services.connector.security import (
    decrypt_connector_secret,
    encrypt_connector_secret,
    mask_dsn_secrets,
    mask_password_in_text,
)

# 从 sql_validator 重新导出验证工具
from app.services.connector.sql_validator import (
    get_sql_statement_type,
    is_readonly_sql,
    validate_table_name,
)

__all__ = [
    # 异常类
    "DatabaseConnectorAccessError",
    "DatabaseConnectorApprovalRejectedError",
    "DatabaseConnectorApprovalRequiredError",
    "DatabaseConnectorApprovalTimeoutError",
    "DatabaseConnectorAttachmentMissingError",
    "DatabaseConnectorCapabilityDeniedError",
    "DatabaseConnectorGrantDeniedError",
    "DatabaseConnectorNotFoundError",
    "DatabaseConnectorPlatformRejectionError",
    "DatabaseConnectorRemoteExecutionError",
    "DatabaseConnectorRemotePermissionError",
    # 安全工具
    "decrypt_connector_secret",
    "encrypt_connector_secret",
    "mask_dsn_secrets",
    "mask_password_in_text",
    # 验证工具
    "get_sql_statement_type",
    "is_readonly_sql",
    "validate_table_name",
    # 主要类
    "ConnectorAccessContext",
    "DatabaseConnectorService",
    # 常量
    "CONNECTOR_CONFIG_FILE",
    "SESSION_ATTACHMENT_FILE",
]
