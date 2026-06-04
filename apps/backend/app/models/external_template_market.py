"""外部模板市场模型。

用于承接 AIASys 内置模板市场，将系统内置模板以市场形式展示给用户。
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ExternalTemplateMarketSource(BaseModel):
    """外部模板市场源定义。"""

    source_id: str = Field(..., description="源 ID")
    display_name: str = Field(..., description="源名称")
    description: Optional[str] = Field(default=None, description="源说明")
    supports_public_catalog: bool = Field(
        default=True,
        description="是否支持公开目录浏览",
    )
    supports_install: bool = Field(
        default=True,
        description="是否支持安装到用户模板目录",
    )
    install_available: bool = Field(
        default=True,
        description="当前服务环境是否可执行安装",
    )
    install_unavailable_reason: Optional[str] = Field(
        default=None,
        description="当前不可安装时的说明",
    )


class ExternalTemplateMarketItem(BaseModel):
    """外部模板市场条目摘要。"""

    source_id: str = Field(..., description="来源 ID")
    item_id: str = Field(..., description="模板 ID")
    name: str = Field(..., description="模板名称")
    description: Optional[str] = Field(default=None, description="模板简介")
    icon: str = Field(default="file", description="图标标识")
    category: str = Field(default="通用", description="分类")
    env_kind: str = Field(default="none", description="推荐环境类型")
    file_count: int = Field(default=0, description="文件数量")
    capability_count: int = Field(default=0, description="能力数量")
    is_installed: bool = Field(default=False, description="是否已安装到用户模板目录")
    official: bool = Field(default=False, description="是否为官方模板")


class ExternalTemplateMarketListResponse(BaseModel):
    """外部模板市场列表响应。"""

    source: ExternalTemplateMarketSource
    items: list[ExternalTemplateMarketItem] = Field(default_factory=list)
    available_categories: list[str] = Field(default_factory=list)
    total_count: int = Field(default=0)


class ExternalTemplateMarketDetailResponse(BaseModel):
    """外部模板市场详情响应。"""

    source: ExternalTemplateMarketSource
    item: ExternalTemplateMarketItem
    files: list[dict] = Field(default_factory=list, description="文件列表")
    recommended_capabilities: list[dict] = Field(default_factory=list, description="推荐能力列表")
    env_vars: dict[str, str] = Field(default_factory=dict, description="环境变量")
    can_install: bool = Field(default=False)
    install_disabled_reason: Optional[str] = Field(default=None)


class InstallExternalTemplateRequest(BaseModel):
    """安装外部模板请求。"""

    source_id: str = Field(..., description="市场源 ID")
    item_id: str = Field(..., description="模板条目 ID")
