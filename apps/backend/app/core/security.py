"""
安全工具模块

包含密码哈希和 JWT token 处理
"""

import hashlib
import os
from datetime import timedelta
from pathlib import Path
from typing import Optional

import bcrypt

# 加载 .env 文件
from dotenv import load_dotenv
from jose import JWTError, jwt

from app.core.config import JWT_SECRET
from app.core.time import utc_now

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

# JWT 配置
SECRET_KEY = (
    os.getenv("JWT_SECRET_KEY", "").strip() or os.getenv("SECRET_KEY", "").strip() or JWT_SECRET
)
ALGORITHM = "HS256"

import logging

logger = logging.getLogger(__name__)
ACCESS_TOKEN_EXPIRE_DAYS = 30


def _truncate_password(password: str) -> bytes:
    """
    处理密码长度限制
    bcrypt 限制密码长度为 72 字节
    使用 SHA256 预哈希来支持任意长度密码
    """
    # 使用 SHA256 预哈希，然后取前 72 字节
    return hashlib.sha256(password.encode("utf-8")).digest()[:72]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    # 使用 SHA256 预哈希支持任意长度密码，再用 bcrypt 验证
    password_bytes = _truncate_password(plain_password)
    return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    """获取密码哈希（使用 bcrypt）"""
    # 使用 SHA256 预哈希支持任意长度密码，再用 bcrypt 哈希
    password_bytes = _truncate_password(password)
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建 JWT access token"""
    to_encode = data.copy()

    if expires_delta:
        expire = utc_now() + expires_delta
    else:
        expire = utc_now() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """解码 JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning(f"JWT decode failed: {e}")
        return None
