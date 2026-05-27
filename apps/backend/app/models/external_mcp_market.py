"""
外部 MCP 市场模型

用于承接 AIASys 自身 MCP 市场中的外部目录源，而不是把某个外部站点当成产品主语。
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.models.mcp import MCPServerConfig


class ExternalMCPMarketSource(BaseModel):
    """外部 MCP 市场源定义。"""

    source_id: str = Field(..., description="源 ID")
    display_name: str = Field(..., description="源名称")
    description: Optional[str] = Field(default=None, description="源说明")
    supports_public_catalog: bool = Field(
        default=True,
        description="是否支持匿名公开目录浏览",
    )
    supports_account_sync: bool = Field(
        default=False,
        description="是否支持账号态同步",
    )
    requires_token_for_account_sync: bool = Field(
        default=False,
        description="账号态同步是否需要 token",
    )


class ExternalMCPMarketItem(BaseModel):
    """外部 MCP 市场条目摘要。"""

    source_id: str = Field(..., description="来源 ID")
    item_id: str = Field(..., description="外部条目 ID")
    display_name: str = Field(..., description="展示名称")
    publisher: Optional[str] = Field(default=None, description="发布者")
    description: Optional[str] = Field(default=None, description="条目简介")
    logo_url: Optional[str] = Field(default=None, description="Logo 地址")
    categories: List[str] = Field(default_factory=list, description="分类列表")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    view_count: Optional[int] = Field(default=None, description="访问量")
    is_hosted: Optional[bool] = Field(
        default=None,
        description="是否支持托管",
    )


class ExternalMCPTemplatePreview(BaseModel):
    """可导入的模板预览。"""

    server_key: str = Field(..., description="模板中的 server key")
    import_name: str = Field(..., description="导入到 AIASys 后默认使用的名字")
    transport_type: Literal["streamable-http", "sse", "stdio"] = Field(
        ...,
        description="传输类型",
    )
    target: Optional[str] = Field(default=None, description="连接地址或启动命令")
    args: List[str] = Field(default_factory=list, description="命令参数")
    env_keys: List[str] = Field(default_factory=list, description="环境变量键列表")
    header_keys: List[str] = Field(default_factory=list, description="请求头键列表")


class ExternalMCPEnvField(BaseModel):
    """导入时需要用户补充的变量。"""

    name: str = Field(..., description="变量名")
    required: bool = Field(default=False, description="是否必填")
    description: Optional[str] = Field(default=None, description="说明")
    default_value: Optional[str] = Field(default=None, description="默认值")


class ExternalMCPMarketListResponse(BaseModel):
    """外部 MCP 市场列表响应。"""

    source: ExternalMCPMarketSource
    items: List[ExternalMCPMarketItem] = Field(default_factory=list)
    total_count: int = Field(default=0)
    page_number: int = Field(default=1)
    page_size: int = Field(default=20)


class ExternalMCPMarketDetailResponse(BaseModel):
    """外部 MCP 市场详情响应。"""

    source: ExternalMCPMarketSource
    item: ExternalMCPMarketItem
    env_fields: List[ExternalMCPEnvField] = Field(default_factory=list)
    template_previews: List[ExternalMCPTemplatePreview] = Field(default_factory=list)
    readme_excerpt: Optional[str] = Field(default=None)
    can_import: bool = Field(default=False)
    import_disabled_reason: Optional[str] = Field(default=None)


class ImportExternalMCPRequest(BaseModel):
    """导入外部 MCP 请求。"""

    source_id: str = Field(..., description="来源 ID")
    item_id: str = Field(..., description="条目 ID")
    enabled: bool = Field(default=True, description="导入后是否启用")
    env_overrides: Dict[str, str] = Field(
        default_factory=dict,
        description="用户补充的环境变量值",
    )


class ImportExternalMCPResponse(BaseModel):
    """导入外部 MCP 响应。"""

    source_id: str = Field(..., description="来源 ID")
    item_id: str = Field(..., description="条目 ID")
    imported_names: List[str] = Field(default_factory=list, description="导入后的配置名称")
    imported_servers: List[MCPServerConfig] = Field(
        default_factory=list,
        description="导入后的 MCP 配置",
    )
    message: str = Field(..., description="响应提示")
