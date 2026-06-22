"""
Agent 配置管理模块

当前主线默认只暴露本地执行模式：
1. 本地执行模式 (local) - 代码在本地受限环境中执行

运行态固定为 local，不再对外暴露模式切换控制。

配置示例 (config.toml):
[sandbox]
default_mode = "local"
enabled_modes = ["local"]
"""

from typing import Literal

# 导入核心配置
from app.core.config import SANDBOX_MODE


def get_sandbox_mode() -> Literal["local"]:
    """
    获取当前的执行模式。
    """
    mode = SANDBOX_MODE.lower()
    if mode != "local":
        return "local"
    return "local"
