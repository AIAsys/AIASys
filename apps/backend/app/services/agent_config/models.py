"""
Agent 配置数据模型

使用 Pydantic 进行数据验证和序列化。
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.agent.models.llm_config import LoopControl


class AgentMode(str, Enum):
    """Agent 模式"""

    ANALYSIS = "analysis"


class MergeStrategy(str, Enum):
    """配置合并策略"""

    REPLACE = "replace"  # 完全替换
    APPEND = "append"  # 追加到末尾
    MERGE = "merge"  # 智能合并（按 section）


class ToolOverride(BaseModel):
    """工具覆盖配置"""

    name: str = Field(..., description="工具完整路径名，如 app.agents.tools.xxx:ToolName")
    enabled: Optional[bool] = Field(None, description="是否启用，None 表示不覆盖")
    description: Optional[str] = Field(None, description="覆盖工具描述")
    timeout: Optional[int] = Field(None, description="覆盖超时时间（秒）")

    @field_validator("name")
    @classmethod
    def validate_tool_name(cls, v: str) -> str:
        """验证工具名格式"""
        if ":" not in v:
            raise ValueError(f"工具名必须包含 ':' 分隔符，如 'module:ToolClass'， got: {v}")
        return v


class ToolsConfig(BaseModel):
    """工具配置"""

    selection_mode: Literal["inherit", "explicit"] = Field(
        default="inherit",
        description="工具选择模式：inherit 使用差分覆盖，explicit 使用显式启用集合",
    )
    enabled_tools: List[str] = Field(
        default_factory=list,
        description="显式启用的工具列表（完整路径名）",
    )
    disabled_tools: List[str] = Field(
        default_factory=list, description="禁用的工具列表（完整路径名）"
    )
    extra_tools: List[str] = Field(
        default_factory=list, description="额外启用的工具列表（用于自定义模式）"
    )
    tool_overrides: Dict[str, ToolOverride] = Field(
        default_factory=dict, description="工具参数覆盖，key 为工具名"
    )
    tool_strategy: Literal["auto", "search", "deferred", "passthrough"] = Field(
        default="auto",
        description="工具加载策略",
    )

    @field_validator("enabled_tools", "disabled_tools", "extra_tools")
    @classmethod
    def validate_tool_names(cls, v: List[str]) -> List[str]:
        """验证工具名格式"""
        for tool_name in v:
            if ":" not in tool_name:
                raise ValueError(
                    f"工具名必须包含 ':' 分隔符，如 'module:ToolClass'， got: {tool_name}"
                )
        return v


class PromptConfig(BaseModel):
    """提示词配置"""

    content: Optional[str] = Field(None, description="提示词内容（覆盖系统默认）")
    strategy: MergeStrategy = Field(
        default=MergeStrategy.MERGE, description="合并策略：replace/append/merge"
    )
    section_markers: Optional[Dict[str, str]] = Field(
        default=None, description="section 标记映射，用于 merge 策略"
    )


class ModelOverrides(BaseModel):
    """模型参数覆盖"""

    model: Optional[str] = Field(None, description="覆盖模型名称")
    temperature: Optional[float] = Field(None, ge=0, le=2, description="温度参数")
    max_tokens: Optional[int] = Field(None, gt=0, description="最大 token 数")
    top_p: Optional[float] = Field(None, ge=0, le=1, description="top_p 参数")
    thinking_effort: Optional[str] = Field(None, description="思考深度：low/medium/high")


class LoopControlOverrides(BaseModel):
    """运行循环上下文控制覆盖。"""

    reserved_context_size: Optional[int] = Field(
        None,
        ge=1000,
        description="为模型回复保留的 token 空间",
    )
    compaction_trigger_ratio: Optional[float] = Field(
        None,
        ge=0.5,
        le=0.99,
        description="自动压缩触发比例",
    )

    def has_values(self) -> bool:
        return any(
            value is not None
            for value in (
                self.reserved_context_size,
                self.compaction_trigger_ratio,
            )
        )

    def apply_to(self, base: LoopControl) -> LoopControl:
        payload = base.model_dump()
        if self.reserved_context_size is not None:
            payload["reserved_context_size"] = self.reserved_context_size
        if self.compaction_trigger_ratio is not None:
            payload["compaction_trigger_ratio"] = self.compaction_trigger_ratio
        return LoopControl(**payload)


class ResolvedLoopControlConfig(BaseModel):
    """当前生效的 loop_control 运行时配置。"""

    reserved_context_size: int = Field(..., ge=1000, description="保留回复空间")
    compaction_trigger_ratio: float = Field(
        ...,
        ge=0.5,
        le=0.99,
        description="自动压缩触发比例",
    )

    @classmethod
    def from_loop_control(cls, loop_control: LoopControl) -> "ResolvedLoopControlConfig":
        return cls(
            reserved_context_size=loop_control.reserved_context_size,
            compaction_trigger_ratio=loop_control.compaction_trigger_ratio,
        )


class ModeOverrides(BaseModel):
    """单个模式的覆盖配置"""

    enabled: bool = Field(default=True, description="是否启用自定义")
    prompt: Optional[PromptConfig] = Field(None, description="提示词覆盖")
    tools: Optional[ToolsConfig] = Field(None, description="工具配置")
    model: Optional[ModelOverrides] = Field(None, description="模型参数覆盖")
    runtime: Optional[LoopControlOverrides] = Field(
        None,
        description="运行时 loop_control 覆盖",
    )


class UserAgentConfig(BaseModel):
    """
    用户级 Agent 配置

    这是完整的用户配置结构，包含所有模式的自定义。
    """

    version: str = Field(default="1.0", description="配置版本")
    updated_at: Optional[str] = Field(None, description="最后更新时间（ISO 格式）")

    # 分析模式覆盖配置（统一主控，无模式切换）
    analysis: Optional[ModeOverrides] = Field(None, description="analysis 模式配置")

    model_config = ConfigDict(extra="allow")


class UserConfigIndex(BaseModel):
    """
    用户配置索引文件结构 (user_config.json)

    这是轻量级的索引文件，用于快速检查哪些模式启用了自定义。
    实际的详细配置存储在各自的子目录中。
    """

    version: str = Field(default="1.0", description="配置版本")
    updated_at: Optional[str] = Field(None, description="最后更新时间")

    # 各模式的配置索引
    modes: Dict[str, ModeIndex] = Field(default_factory=dict, description="模式配置索引")

    class ModeIndex(BaseModel):
        """单个模式的索引项"""

        enabled: bool = Field(default=False, description="是否启用自定义")
        prompt_path: Optional[str] = Field(None, description="提示词文件相对路径")
        tools_path: Optional[str] = Field(None, description="工具配置文件相对路径")
        runtime_path: Optional[str] = Field(None, description="运行时配置文件相对路径")


class MergedAgentConfig(BaseModel):
    """
    合并后的 Agent 配置

    这是最终用于生成动态 agent 配置的结果。
    """

    mode: AgentMode = Field(..., description="Agent 模式")

    # 提示词
    system_prompt: str = Field(..., description="完整的系统提示词")
    prompt_source: str = Field(
        ..., description="提示词来源：system_default/user_default/session_override"
    )

    # 工具
    enabled_tools: List[str] = Field(default_factory=list, description="启用的工具列表")
    disabled_tools: List[str] = Field(default_factory=list, description="禁用的工具列表")
    tool_overrides: Dict[str, ToolOverride] = Field(
        default_factory=dict, description="工具参数覆盖"
    )
    tool_strategy: Literal["auto", "search", "deferred", "passthrough"] = Field(
        default="auto",
        description="工具加载策略",
    )

    # 模型参数
    model: Optional[str] = Field(None, description="模型名称")
    model_params: Optional[Dict] = Field(None, description="模型生成参数")
    runtime_config: ResolvedLoopControlConfig = Field(
        ...,
        description="当前生效的运行时 loop_control",
    )
    runtime_source: str = Field(
        ...,
        description="运行时配置来源：system_default/user_default/session_override",
    )

    # 元数据
    is_customized: bool = Field(default=False, description="是否有用户自定义")
    base_config_path: str = Field(..., description="基础系统 preset / 配置来源")


# 系统默认配置路径映射
SYSTEM_DEFAULT_CONFIGS = {
    AgentMode.ANALYSIS: {
        "local": "local_sandbox_agent_config/data_analysis.preset",
    },
}


def get_system_default_config_path(mode: AgentMode, sandbox_mode: Optional[str] = None) -> Path:
    """
    获取系统默认配置路径标识

    Args:
        mode: Agent 配置场景标识
        sandbox_mode: 沙盒模式（仅对 analysis 有效）

    Returns:
        配置路径标识
    """
    from app.services.scene.registry import get_scene_registry

    try:
        registry = get_scene_registry()
        scene = registry.get(mode.value if isinstance(mode, AgentMode) else mode)
        return registry.resolve_config_path(scene)
    except KeyError:
        # Fallback: always use the unified local sandbox config
        base_path = Path(__file__).resolve().parents[2] / "agents"
        return base_path / "local_sandbox_agent_config" / "data_analysis.preset"
