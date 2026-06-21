"""
用户模型

支持认证方式：
- local: 单机默认用户模式
- none: 强制不认证的假人模式 (纯离线测试环境)
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class UserInfo(BaseModel):
    """用户信息模型"""

    user_id: str = Field(..., description="用户唯一标识")
    role: str = Field(default="user", description="用户角色: admin/user")
    auth_provider: str = Field(default="local", description="认证来源")
    email: Optional[str] = Field(default=None, description="用户邮箱")
    name: Optional[str] = Field(default=None, description="用户名称")
    phone: Optional[str] = Field(default=None, description="手机号")

    def is_admin(self) -> bool:
        """检查是否为管理员"""
        return self.role == "admin"

    def can_access_user_data(self, target_user_id: str) -> bool:
        """检查是否可以访问目标用户的数据"""
        return self.is_admin() or self.user_id == target_user_id


class AuthConfig(BaseModel):
    """认证配置"""

    mode: str = Field(default="local", description="认证模式: local/none")
    local_default_user_id: str = Field(
        default="local_default",
        description="单机默认用户 ID",
    )
    local_default_email: str = Field(
        default="local_default@localhost",
        description="单机默认用户邮箱",
    )
    local_default_name: str = Field(
        default="Local Default",
        description="单机默认用户名",
    )
    local_default_role: str = Field(
        default="admin",
        description="单机默认用户角色",
    )

    # CORS 配置
    # 默认不再使用 "*"，避免与 allow_credentials=true 组合形成安全漏洞
    cors_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:13000", "http://127.0.0.1:13000"],
        description="允许的跨域来源",
    )
    cors_allow_credentials: bool = Field(default=True, description="允许跨域凭证")

    # 安全 Headers
    enable_security_headers: bool = Field(default=True, description="启用安全Headers")
