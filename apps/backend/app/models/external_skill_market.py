"""
外部 Skill 市场模型

用于承接 AIASys 自身 Skill 市场中的外部目录源，而不是把某个外部平台当成产品主语。
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class ExternalSkillMarketSource(BaseModel):
    """外部 Skill 市场源定义。"""

    source_id: str = Field(..., description="源 ID")
    display_name: str = Field(..., description="源名称")
    description: Optional[str] = Field(default=None, description="源说明")
    supports_public_catalog: bool = Field(
        default=True,
        description="是否支持公开目录浏览",
    )
    supports_workspace_install: bool = Field(
        default=True,
        description="是否支持安装到工作区",
    )
    install_available: bool = Field(
        default=True,
        description="当前服务环境是否可执行安装",
    )
    install_unavailable_reason: Optional[str] = Field(
        default=None,
        description="当前不可安装时的说明",
    )


class ExternalSkillMarketItem(BaseModel):
    """外部 Skill 市场条目摘要。"""

    source_id: str = Field(..., description="来源 ID")
    item_id: str = Field(..., description="外部条目 ID")
    slug: str = Field(..., description="外部条目标识")
    display_name: str = Field(..., description="展示名称")
    description: Optional[str] = Field(default=None, description="条目简介")
    summary: Optional[str] = Field(default=None, description="简短摘要")
    description_zh: Optional[str] = Field(default=None, description="中文简介")
    version: Optional[str] = Field(default=None, description="版本号")
    homepage_url: Optional[str] = Field(default=None, description="主页地址")
    categories: List[str] = Field(default_factory=list, description="分类列表")
    labels: Optional[dict] = Field(default=None, description="标签（如 requires_api_key）")
    owner_name: Optional[str] = Field(default=None, description="作者 ID")
    source: Optional[str] = Field(default=None, description="原始来源（如 clawhub）")
    icon_url: Optional[str] = Field(default=None, description="图标地址")
    downloads: Optional[int] = Field(default=None, description="下载量")
    installs: Optional[int] = Field(default=None, description="安装量")
    stars: Optional[int] = Field(default=None, description="收藏量")
    score: Optional[float] = Field(default=None, description="推荐分")
    rank: Optional[int] = Field(default=None, description="目录排序")


class ExternalSkillMarketListResponse(BaseModel):
    """外部 Skill 市场列表响应。"""

    source: ExternalSkillMarketSource
    items: List[ExternalSkillMarketItem] = Field(default_factory=list)
    available_categories: List[str] = Field(default_factory=list)
    total_count: int = Field(default=0)
    page_number: int = Field(default=1)
    page_size: int = Field(default=20)


class ExternalSkillMarketDetailResponse(BaseModel):
    """外部 Skill 市场详情响应。"""

    source: ExternalSkillMarketSource
    item: ExternalSkillMarketItem
    readme_excerpt: Optional[str] = Field(default=None, description="入口文档摘要")
    entry_relative_path: Optional[str] = Field(default=None, description="入口文档相对路径")
    included_files: List[str] = Field(default_factory=list, description="包内文件预览")
    can_install: bool = Field(default=False)
    install_disabled_reason: Optional[str] = Field(default=None)


class InstallExternalSkillRequest(BaseModel):
    """安装外部 Skill 请求。"""

    source_id: str = Field(..., description="来源 ID")
    item_id: str = Field(..., description="外部条目 ID")
    force: bool = Field(default=False, description="是否覆盖当前工作区已有同名 Skill")


class InstallExternalSkillResponse(BaseModel):
    """安装外部 Skill 响应。"""

    source_id: str = Field(..., description="来源 ID")
    item_id: str = Field(..., description="外部条目 ID")
    workspace_id: str = Field(..., description="目标工作区 ID")
    skill_name: str = Field(..., description="安装后的 Skill 名称")
    message: str = Field(..., description="结果消息")
