"""
AIASys Agent 描述模型，用于动态配置生成与运行时编排。
"""

from typing import Any

from pydantic import BaseModel, Field


class AgentManifest(BaseModel):
    """
    Agent 的静态/动态描述信息。
    """

    name: str
    system_prompt: str = ""
    tools: list[str] = Field(default_factory=list)
    mcp_configs: list[dict[str, Any]] | None = None
    # MCP 继承策略
    mcp_policy: str | None = None  # inherit | allowlist | denylist | none
    mcp_servers: list[str] = Field(default_factory=list)
    # Skill 继承策略
    skill_policy: str | None = None  # inherit | allowlist | denylist | none
    skills: list[str] = Field(default_factory=list)
