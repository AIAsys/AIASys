"""
Agent 配置管理模块

当前主线默认只暴露本地执行模式：
1. 本地执行模式 (local) - 代码在本地受限环境中执行

运行态固定为 local，不再对外暴露模式切换控制。

配置示例 (config.json):
{
  "sandbox": {
    "mode": "local",
    "postgres": {...},
    "pip_index_url": "..."
  }
}
"""

from pathlib import Path
from typing import Literal

# 导入核心配置
from app.core.config import SANDBOX_MODE

# 配置根目录
CONFIG_ROOT = Path(__file__).parent

# 当前仅保留本地模式配置目录。
LOCAL_CONFIG_DIR = CONFIG_ROOT / "local_sandbox_agent_config"


def get_sandbox_mode() -> Literal["local"]:
    """
    获取当前的执行模式。
    """
    mode = SANDBOX_MODE.lower()
    if mode != "local":
        return "local"
    return "local"


def get_config_dir(mode: Literal["local"] | None = None) -> Path:
    """
    获取当前执行模式的配置目录

    Args:
        mode: 执行模式，None 则使用当前配置的值

    Returns:
        配置目录的 Path 对象
    """
    if mode is None:
        mode = get_sandbox_mode()

    return LOCAL_CONFIG_DIR


def get_agent_config_path(agent_name: str = "data_analysis") -> Path:
    """
    获取 Agent preset 虚拟路径标识

    Args:
        agent_name: Agent 名称，默认为 "data_analysis"

    Returns:
        preset 虚拟路径
    """
    config_dir = get_config_dir()
    return config_dir / f"{agent_name}.preset"


def is_local_mode() -> bool:
    """检查是否处于本地执行模式"""
    return get_sandbox_mode() == "local"
