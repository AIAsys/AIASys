"""
认证模块

支持两种认证方式：
1. 本地认证 (local) - 单机默认用户 + 可选本地令牌
2. 无认证模式 (none) - 纯离线测试
"""

import logging
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import AUTH_CONFIG
from app.core.database import User, db_session
from app.models.user import AuthConfig, UserInfo

logger = logging.getLogger(__name__)

# Security Scheme for Swagger UI
security = HTTPBearer(auto_error=False)

LOCAL_DEFAULT_USER_ID = "local_default"
LOCAL_DEFAULT_USER_NAME = "Local Default"
LOCAL_DEFAULT_USER_EMAIL = "local_default@localhost"
LOCAL_DEFAULT_USER_ROLE = "admin"


def _get_local_default_identity() -> dict[str, str]:
    return {
        "user_id": getattr(AUTH_CONFIG, "local_default_user_id", LOCAL_DEFAULT_USER_ID)
        or LOCAL_DEFAULT_USER_ID,
        "email": getattr(AUTH_CONFIG, "local_default_email", LOCAL_DEFAULT_USER_EMAIL)
        or LOCAL_DEFAULT_USER_EMAIL,
        "name": getattr(AUTH_CONFIG, "local_default_name", LOCAL_DEFAULT_USER_NAME)
        or LOCAL_DEFAULT_USER_NAME,
        "role": getattr(AUTH_CONFIG, "local_default_role", LOCAL_DEFAULT_USER_ROLE)
        or LOCAL_DEFAULT_USER_ROLE,
    }


def ensure_local_default_user_exists() -> User:
    """确保单机默认用户在数据库中存在，并与配置保持一致。"""
    identity = _get_local_default_identity()
    with db_session() as db:
        db_user = db.query(User).filter(User.id == identity["user_id"]).first()
        created = False
        if db_user is None:
            db_user = User(
                id=identity["user_id"],
                email=identity["email"],
                name=identity["name"],
                role=identity["role"],
                hashed_password=None,
            )
            db.add(db_user)
            created = True
        else:
            db_user.email = identity["email"]
            db_user.name = identity["name"]
            db_user.role = identity["role"]
            db.add(db_user)

        db.commit()
        db.refresh(db_user)

        if created:
            logger.info(" 已创建默认本地用户: %s", db_user.id)

        return db_user


def _build_local_default_user() -> UserInfo:
    """单机个人模式的默认本地用户。"""
    identity = _get_local_default_identity()
    return UserInfo(
        user_id=identity["user_id"],
        role=identity["role"],
        auth_provider="local",
        email=identity["email"],
        name=identity["name"],
        phone=None,
    )


class AuthenticationError(HTTPException):
    """认证错误"""

    def __init__(self, detail: str = "Authentication failed"):
        super().__init__(status_code=401, detail=detail)


class AuthorizationError(HTTPException):
    """授权错误"""

    def __init__(self, detail: str = "Permission denied"):
        super().__init__(status_code=403, detail=detail)


class AuthProvider:
    """认证提供者基类"""

    def __init__(self, config: AuthConfig):
        self.config = config

    async def authenticate(self, request: Request, **kwargs) -> Optional[UserInfo]:
        """执行认证，返回用户信息或 None"""
        raise NotImplementedError()


class NoneAuthProvider(AuthProvider):
    """无认证模式（离线跑单元测试时使用的虚拟身份）"""

    async def authenticate(self, request: Request, **kwargs) -> Optional[UserInfo]:
        # 返回一个默认测试管理用户
        return UserInfo(
            user_id="test_anonymous_dev",
            role="admin",
            auth_provider="none",
        )


class LocalAuthProvider(AuthProvider):
    """
    本地认证模式

    单机默认用户模式。
    不信任历史 JWT 或浏览器残留身份，始终回落到固定本地用户。
    """

    async def authenticate(
        self,
        request: Request,
        **kwargs,
    ) -> Optional[UserInfo]:
        """
        单机模式下固定返回本地默认用户。
        """
        ensure_local_default_user_exists()
        return _build_local_default_user()


# 全局认证提供者实例
_auth_provider: Optional[AuthProvider] = None


def get_auth_provider(config: Optional[AuthConfig] = None) -> AuthProvider:
    """获取认证提供者实例（单例）"""
    global _auth_provider

    if _auth_provider is None:
        cfg = config or AUTH_CONFIG

        if cfg.mode == "none":
            _auth_provider = NoneAuthProvider(cfg)
        elif cfg.mode == "local":
            _auth_provider = LocalAuthProvider(cfg)
        else:
            raise ValueError(f"Unknown auth mode: {cfg.mode}, please use 'local' or 'none'.")

    return _auth_provider


def reset_auth_provider():
    """重置认证提供者（用于测试或热重载配置）"""
    global _auth_provider
    _auth_provider = None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> UserInfo:
    """
    获取当前用户（FastAPI 路由依赖）
    """
    provider = get_auth_provider()

    # 进入校验
    user = await provider.authenticate(request)

    if user is None:
        raise AuthenticationError("Not authenticated or invalid token.")

    # 将用户信息存储在 request.state 中供全局中间件使用
    request.state.user = user

    return user


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[UserInfo]:
    """
    可选认证 - 不强制要求登录。如果解析出则返回 UserInfo，否则返回 None。
    """
    try:
        return await get_current_user(request, credentials)
    except AuthenticationError:
        if AUTH_CONFIG.mode == "local":
            ensure_local_default_user_exists()
            return _build_local_default_user()
        return None


def require_auth(optional: bool = False) -> Callable:
    """认证依赖分发工厂"""
    if optional:
        return get_current_user_optional
    return get_current_user


def require_role(*roles: str) -> Callable:
    """角色越权访问管控装饰器"""

    async def role_checker(
        user: UserInfo = Depends(get_current_user),
    ) -> UserInfo:
        if user.role not in roles and user.role != "admin":
            raise AuthorizationError(f"Required role: {', '.join(roles)}, your role: {user.role}")
        return user

    return role_checker


async def verify_user_access(
    target_user_id: str, current_user: UserInfo = Depends(get_current_user)
) -> bool:
    """数据越权访问检查：判断调用者是不是目标账户本人或管理员"""
    if not current_user.can_access_user_data(target_user_id):
        raise AuthorizationError("You can only access your own data")
    return True


# 在文件末尾添加以下内容


async def require_admin(
    request: Request,
    current_user: UserInfo = Depends(get_current_user),
) -> UserInfo:
    """
    要求管理员权限的依赖

    使用方式:
        @router.get("/admin-only")
        async def admin_endpoint(user: UserInfo = Depends(require_admin)):
            ...

    Args:
        request: FastAPI 请求对象
        current_user: 当前登录用户（由 get_current_user 提供）

    Returns:
        UserInfo: 管理员用户信息

    Raises:
        AuthorizationError: 如果不是管理员
    """
    if not current_user.is_admin():
        raise AuthorizationError(
            f"Permission denied. Admin role required, got: {current_user.role}"
        )
    return current_user
