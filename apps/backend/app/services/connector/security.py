"""
数据库连接器安全工具

提供敏感信息脱敏、密码加密等功能
"""

import logging

from app.core.encryption import EncryptionError, encryption_service

logger = logging.getLogger(__name__)


def mask_dsn_secrets(dsn: str) -> str:
    """
    脱敏 DSN 中的敏感信息

    Args:
        dsn: 数据源名称（可能包含密码）

    Returns:
        脱敏后的 DSN
    """
    from app.services.connector.constants import _DSN_SECRET_RE

    def replacer(match):
        scheme = match.group("scheme")
        user = match.group("user")
        return f"{scheme}{user}:****@"

    return _DSN_SECRET_RE.sub(replacer, dsn)


def mask_password_in_text(text: str) -> str:
    """
    脱敏文本中的密码字段

    Args:
        text: 可能包含密码的文本

    Returns:
        脱敏后的文本
    """
    from app.services.connector.constants import (
        _BEARER_TOKEN_RE,
        _JSON_PASSWORD_FIELD_RE,
        _PASSWORD_FIELD_RE,
    )

    # 处理 password=xxx 格式
    result = _PASSWORD_FIELD_RE.sub(r"\1****", text)
    # 处理 "password": "xxx" 格式
    result = _JSON_PASSWORD_FIELD_RE.sub(r"\1****\3", result)
    # 处理 Bearer token 格式
    result = _BEARER_TOKEN_RE.sub(r"\1****", result)
    return result


def encrypt_connector_secret(secret: str) -> str:
    """
    加密连接器密钥

    Args:
        secret: 原始密钥

    Returns:
        加密后的密钥
    """
    try:
        return encryption_service.encrypt(secret)
    except EncryptionError as e:
        logger.error(f"加密密钥失败: {e}")
        raise


def decrypt_connector_secret(encrypted_secret: str) -> str:
    """
    解密连接器密钥

    Args:
        encrypted_secret: 加密后的密钥

    Returns:
        原始密钥
    """
    try:
        return encryption_service.decrypt(encrypted_secret)
    except EncryptionError as e:
        logger.error(f"解密密钥失败: {e}")
        raise
