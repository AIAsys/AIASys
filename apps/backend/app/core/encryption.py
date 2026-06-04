"""
加密服务

用于加密存储敏感信息（API Key 等）
使用 Fernet 对称加密，密钥从环境变量获取
"""

import base64
import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

# 加载 .env 文件
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import AUTH_MODE, DEBUG

logger = logging.getLogger(__name__)


def _derive_dev_key() -> str:
    """基于用户主目录生成确定性开发密钥，避免硬编码密钥泄露风险。"""
    home = str(Path.home())
    return hashlib.sha256(home.encode("utf-8")).hexdigest()[:32]


def resolve_encryption_master_key() -> str:
    """解析当前进程应使用的主加密密钥。"""
    master_key = os.getenv("ENCRYPTION_KEY", "").strip()
    if master_key:
        return master_key

    if DEBUG or AUTH_MODE in {"local", "none"}:
        fallback_key = os.getenv("AIASYS_DEV_ENCRYPTION_KEY", "").strip()
        if fallback_key:
            return fallback_key
        dev_key = _derive_dev_key()
        logger.info(
            "ENCRYPTION_KEY 和 AIASYS_DEV_ENCRYPTION_KEY 均未设置，"
            "当前处于本地开发模式，使用基于用户主目录的确定性密钥。"
            "如需跨环境稳定解密，请显式设置 ENCRYPTION_KEY。"
        )
        return dev_key

    # 生产环境强制要求设置 ENCRYPTION_KEY
    logger.critical(
        "ENCRYPTION_KEY 未设置！生产环境必须设置 ENCRYPTION_KEY 环境变量以保护敏感数据。"
    )
    raise RuntimeError(
        "ENCRYPTION_KEY must be set in production. "
        "The dev fallback key is not available outside of local/none auth modes."
    )


class EncryptionService:
    """加密服务

    使用 Fernet 对称加密 API Key 等敏感信息
    密钥派生：从主密钥生成 Fernet 密钥
    """

    _instance: Optional["EncryptionService"] = None
    _fernet: Optional[Fernet] = None

    def __new__(cls) -> "EncryptionService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._fernet is not None:
            return

        # 从环境变量获取主密钥；本地开发模式允许回退到稳定开发密钥。
        master_key = resolve_encryption_master_key()

        # 使用 PBKDF2 从主密钥派生 Fernet 密钥
        self._fernet = self._derive_fernet_key(master_key)

    def _derive_fernet_key(self, master_key: str) -> Fernet:
        """从主密钥派生 Fernet 密钥

        使用 PBKDF2HMAC 算法，固定 salt（确保相同主密钥始终生成相同密钥）
        """
        # 使用固定的 salt（基于项目名称）
        salt = b"aiasys-llm-provider-encryption-salt"

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend(),
        )

        key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
        return Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """加密字符串

        Args:
            plaintext: 明文

        Returns:
            加密后的密文（base64 编码）
        """
        if not plaintext:
            return ""

        try:
            encrypted = self._fernet.encrypt(plaintext.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"加密失败: {e}")
            raise EncryptionError(f"加密失败: {e}") from e

    def decrypt(self, ciphertext: str) -> str:
        """解密字符串

        Args:
            ciphertext: 密文

        Returns:
            解密后的明文
        """
        if not ciphertext:
            return ""

        try:
            decrypted = self._fernet.decrypt(ciphertext.encode())
            return decrypted.decode()
        except InvalidToken:
            logger.error("解密失败: 无效的令牌或密钥不匹配")
            raise EncryptionError("解密失败: 无效的令牌或密钥不匹配")
        except Exception as e:
            logger.error(f"解密失败: {e}")
            raise EncryptionError(f"解密失败: {e}") from e

    def rotate_key(self, old_ciphertext: str, new_master_key: str) -> str:
        """密钥轮换：用新密钥重新加密

        Args:
            old_ciphertext: 旧密文
            new_master_key: 新主密钥

        Returns:
            新密文
        """
        # 先解密
        plaintext = self.decrypt(old_ciphertext)

        # 用新密钥派生 Fernet 并加密
        new_fernet = self._derive_fernet_key(new_master_key)
        new_ciphertext = new_fernet.encrypt(plaintext.encode()).decode()

        return new_ciphertext


class EncryptionError(Exception):
    """加密错误"""

    pass


# 全局加密服务实例
encryption_service = EncryptionService()


def encrypt_api_key(api_key: str) -> str:
    """加密 API Key（便捷函数）"""
    return encryption_service.encrypt(api_key)


def decrypt_api_key(ciphertext: str) -> str:
    """解密 API Key（便捷函数）"""
    return encryption_service.decrypt(ciphertext)


def mask_api_key(api_key: str) -> str:
    """脱敏显示 API Key

    例如: sk-abc123...xyz789 -> sk-ab...yz78
    """
    if not api_key:
        return ""

    if len(api_key) <= 8:
        return "***"

    return f"{api_key[:4]}...{api_key[-4:]}"
