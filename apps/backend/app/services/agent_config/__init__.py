"""
Agent 配置服务

支持多租户的用户级 Agent 配置管理。

目录结构:
    workspaces/{user_id}/global_workspace/.aiasys/agent_config/
    ├── user_config.json          # 用户配置索引
    ├── analysis/                 # analysis 模式覆盖
    │   ├── prompt_override.md    # 提示词覆盖
    │   └── tools.json            # 工具开关
    └── research/                 # research 模式覆盖
        ├── prompt_override.md
        └── tools.json

使用示例:
    from app.services.agent_config import AgentConfigService, get_agent_config_service

    service = get_agent_config_service()

    # 获取用户配置（已合并系统默认）
    config = await service.get_merged_config("analysis", user_id="xxx")

    # 保存用户提示词
    await service.save_prompt_override("analysis", user_id="xxx", content="...")

    # 保存工具开关
    await service.save_tools_config("analysis", user_id="xxx", disabled_tools=[...])
"""

from .models import (
    AgentMode,
    LoopControlOverrides,
    MergeStrategy,
    PromptConfig,
    ResolvedLoopControlConfig,
    ToolOverride,
    ToolsConfig,
    UserAgentConfig,
    UserConfigIndex,
)
from .service import AgentConfigService, get_agent_config_service

__all__ = [
    # 服务
    "AgentConfigService",
    "get_agent_config_service",
    # 模型
    "AgentMode",
    "LoopControlOverrides",
    "MergeStrategy",
    "PromptConfig",
    "ResolvedLoopControlConfig",
    "ToolOverride",
    "ToolsConfig",
    "UserAgentConfig",
    "UserConfigIndex",
]
