"""
Skill 数据模型
"""

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class SkillSecurityInfo(BaseModel):
    """Skill 安全元数据。

    可由 SKILL.md frontmatter [security] 显式声明，也可由后端保守扫描自动推断。
    """

    source_trust: str = Field(default="external", description="builtin | curated | external | local")
    risk_level: str = Field(default="medium", description="low | medium | high | critical")
    has_scripts: bool = Field(default=False, description="是否包含可执行脚本")
    requires_env: bool = Field(default=False, description="是否需要环境变量")
    writes_workspace: bool = Field(default=False, description="是否会写工作区文件")
    writes_global: bool = Field(default=False, description="是否会写全局工作区")
    uses_shell: bool = Field(default=False, description="是否会调用 Shell")
    uses_network: bool = Field(default=False, description="是否使用网络")
    installs_dependencies: bool = Field(default=False, description="是否会安装外部依赖")
    adds_tools: list[str] = Field(default_factory=list, description="新增工具列表")


class SkillInfo(BaseModel):
    """Skill 包信息。"""

    name: str = Field(description="Skill 包目录名")
    display_name: str = Field(description="Skill 展示名")
    description: str = Field(description="Skill 描述")
    source: str = Field(description="来源：store/workspace")
    path: Path = Field(description="Skill 包根目录")
    entry_path: Path = Field(description="Skill 入口文件路径")
    entry_relative_path: str = Field(description="入口文件相对包根目录的路径")
    env_fields: list[dict[str, Any]] = Field(
        default_factory=list, description="环境变量字段定义列表"
    )
    security: SkillSecurityInfo = Field(
        default_factory=SkillSecurityInfo, description="安全元数据"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)


class SkillMetaInfo(BaseModel):
    """Skill 副本元数据（.aiasys-skill-meta.json）。"""

    name: str = Field(description="Skill 标识名")
    display_name: str = Field(default="", description="展示用中文名")
    source_type: str = Field(default="custom", description="来源类型：builtin/store/market/custom")
    source_name: Optional[str] = Field(None, description="源中的 skill 名")
    source_fingerprint: Optional[str] = Field(None, description="安装时源目录的内容指纹")
    installed_at: str = Field(default="", description="安装时间 ISO 格式")
    version: Optional[str] = Field(None, description="版本号（展示用）")


class SkillOperationResult(BaseModel):
    """Skill 操作结果。"""

    success: bool = Field(description="是否成功")
    skill_name: str = Field(description="Skill 包名")
    package_path: Optional[Path] = Field(None, description="目标包路径")
    message: str = Field(description="结果消息")

    model_config = ConfigDict(arbitrary_types_allowed=True)
