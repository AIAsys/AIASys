"""
Claw 会话级通信绑定模型
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

ClawConnectorPlatform = Literal[
    "weixin",
    "feishu",
    "dingtalk",
]
ClawPlatformSupportStatus = Literal["ready", "candidate", "reference"]
ClawLinkStatus = Literal["unconfigured", "stopped", "running", "error"]
ClawOutboundPolicy = Literal["latest_assistant_reply"]
ClawQrLoginStatusType = Literal["wait", "scaned", "confirmed", "expired", "error"]

WEIXIN_DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
FEISHU_DEFAULT_BASE_URL = "https://open.feishu.cn"
DINGTALK_DEFAULT_BASE_URL = "https://oapi.dingtalk.com"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ClawConnector(BaseModel):
    """用户级 Claw 连接资产对外模型"""

    connector_id: str = Field(..., description="连接资产 ID")
    channel_id: Optional[str] = Field(default=None, description="频道 ID")
    platform: ClawConnectorPlatform = Field(..., description="平台类型")
    name: str = Field(..., description="连接名称")
    account_id: str = Field(..., description="平台账号 ID")
    base_url: str = Field(..., description="平台 API 基础地址")
    has_token: bool = Field(default=False, description="是否已保存 token")
    token_masked: Optional[str] = Field(default=None, description="脱敏后的 token")
    created_at: str = Field(default_factory=_utcnow_iso, description="创建时间")
    updated_at: str = Field(default_factory=_utcnow_iso, description="更新时间")


class ClawPlatformCatalogItem(BaseModel):
    """Claw 平台目录项"""

    platform: ClawConnectorPlatform = Field(..., description="平台类型")
    display_name: str = Field(..., description="平台显示名")
    description: str = Field(..., description="平台描述")
    support_status: ClawPlatformSupportStatus = Field(..., description="当前支持状态")
    runtime_enabled: bool = Field(default=False, description="当前后端 runtime 是否已接通")
    supports_inbound: bool = Field(default=False, description="是否支持入站消息回流")
    supports_outbound: bool = Field(default=False, description="是否支持消息外发")
    supports_typing: bool = Field(default=False, description="是否支持输入中状态")
    supports_inbound_files: bool = Field(default=False, description="是否支持入站文件/图片/音视频")
    supports_outbound_files: bool = Field(default=False, description="是否支持出站文件/图片/音视频")
    supports_qr_login: bool = Field(default=False, description="是否支持扫码登录")
    transport: str = Field(..., description="主要接入链路")
    entry_hint: str = Field(..., description="当前接入方式提示")
    auth_fields: list[str] = Field(default_factory=list, description="主要凭据字段")
    default_priority: int = Field(default=0, description="前端展示优先级，越大越靠前")
    notes: Optional[str] = Field(default=None, description="补充说明")


class ClawAttachmentSummary(BaseModel):
    """Claw 附件摘要。"""

    display_name: str = Field(..., description="展示名")
    workspace_path: str = Field(..., description="导入后的 /workspace 路径")
    media_type: Optional[str] = Field(default=None, description="MIME 类型")
    size_bytes: Optional[int] = Field(default=None, description="文件大小")
    imported_to_workspace: bool = Field(default=True, description="是否已导入当前工作区")
    imported_at: Optional[str] = Field(default=None, description="导入时间")


class ClawQrLoginStartRequest(BaseModel):
    """二维码登录启动请求"""

    platform: ClawConnectorPlatform = Field(..., description="目标平台")
    bot_type: str = Field(
        default="3", min_length=1, max_length=32, description="微信 bot 类型（仅微信有效）"
    )

    @model_validator(mode="after")
    def normalize_payload(self) -> "ClawQrLoginStartRequest":
        self.bot_type = self.bot_type.strip() or "3"
        return self


class ClawQrLoginSession(BaseModel):
    """二维码登录会话"""

    flow_id: str = Field(..., description="二维码登录流程 ID")
    platform: ClawConnectorPlatform = Field(..., description="目标平台")
    status: ClawQrLoginStatusType = Field(default="wait", description="当前二维码状态")
    qrcode: str = Field(default="", description="二维码值")
    qrcode_url: Optional[str] = Field(default=None, description="二维码打开链接")
    expires_at: Optional[str] = Field(default=None, description="二维码预计过期时间")
    message: Optional[str] = Field(default=None, description="当前提示信息")


class ClawQrLoginStatus(ClawQrLoginSession):
    """二维码登录轮询结果"""

    connector: Optional[ClawConnector] = Field(
        default=None, description="确认后自动创建/更新的连接资产"
    )


class SessionClawBindingRequest(BaseModel):
    """当前 session 的 Claw 绑定请求"""

    channel_id: Optional[str] = Field(default=None, description="绑定的频道 ID")
    connector_id: Optional[str] = Field(default=None, description="绑定的连接资产 ID")
    chat_id: Optional[str] = Field(default=None, description="目标聊天 ID")
    chat_label: Optional[str] = Field(default=None, max_length=255, description="目标聊天显示名")
    outbound_policy: ClawOutboundPolicy = Field(
        default="latest_assistant_reply",
        description="出站同步策略",
    )

    @model_validator(mode="after")
    def normalize_payload(self) -> "SessionClawBindingRequest":
        self.channel_id = str(self.channel_id or "").strip() or None
        self.connector_id = str(self.connector_id or "").strip() or None
        if self.channel_id and not self.connector_id:
            self.connector_id = self.channel_id
        elif self.connector_id and not self.channel_id:
            self.channel_id = self.connector_id
        self.chat_id = str(self.chat_id or "").strip() or None
        self.chat_label = str(self.chat_label or "").strip() or None
        return self


class SessionClawBinding(BaseModel):
    """当前 session 的 Claw 绑定状态"""

    session_id: str = Field(..., description="会话 ID")
    channel_id: Optional[str] = Field(default=None, description="绑定的频道 ID")
    connector_id: Optional[str] = Field(default=None, description="绑定的连接资产 ID")
    connector: Optional[ClawConnector] = Field(default=None, description="连接资产摘要")
    chat_id: Optional[str] = Field(default=None, description="目标聊天 ID")
    chat_label: Optional[str] = Field(default=None, description="目标聊天显示名")
    outbound_policy: ClawOutboundPolicy = Field(
        default="latest_assistant_reply",
        description="出站同步策略",
    )
    auto_sync_enabled: bool = Field(default=False, description="是否已启用自动同步")
    link_status: ClawLinkStatus = Field(default="unconfigured", description="当前链接状态")
    last_error: Optional[str] = Field(default=None, description="最近一次错误")
    last_started_at: Optional[str] = Field(default=None, description="最近一次启动时间")
    last_stopped_at: Optional[str] = Field(default=None, description="最近一次停止时间")
    last_dispatched_at: Optional[str] = Field(default=None, description="最近一次同步时间")
    last_dispatched_digest: Optional[str] = Field(default=None, description="最近一次同步内容摘要")
    last_inbound_at: Optional[str] = Field(default=None, description="最近一次入站消息时间")
    last_inbound_message_id: Optional[str] = Field(default=None, description="最近一次入站消息 ID")
    last_inbound_text: Optional[str] = Field(default=None, description="最近一次入站文本摘要")
    last_inbound_attachments: list[ClawAttachmentSummary] = Field(
        default_factory=list,
        description="最近一次入站附件摘要",
    )
    runtime_active: bool = Field(default=False, description="后端 connector runtime 是否真的在运行")
    runtime_bound_session_ids: list[str] = Field(
        default_factory=list,
        description="当前 connector runtime 承载的 session 列表",
    )
    runtime_bound_chat_ids: list[str] = Field(
        default_factory=list,
        description="当前 connector runtime 承载的远端 chat 列表",
    )
    runtime_last_inbound_at: Optional[str] = Field(default=None, description="最近一次入站时间")
    runtime_last_outbound_at: Optional[str] = Field(default=None, description="最近一次出站时间")
    runtime_last_error: Optional[str] = Field(default=None, description="runtime 最近一次错误")
    updated_at: str = Field(default_factory=_utcnow_iso, description="最近更新时间")


class ClawOutboundPreview(BaseModel):
    """Claw 出站同步预览"""

    session_id: str = Field(..., description="会话 ID")
    channel_id: Optional[str] = Field(default=None, description="频道 ID")
    connector_id: Optional[str] = Field(default=None, description="连接资产 ID")
    platform: Optional[ClawConnectorPlatform] = Field(default=None, description="平台类型")
    has_candidate: bool = Field(default=False, description="是否找到可同步回复")
    raw_text: str = Field(default="", description="原始可见回复")
    formatted_text: str = Field(default="", description="平台格式化后的文本")
    chunks: list[str] = Field(default_factory=list, description="平台实际分片结果")
    attachments: list[ClawAttachmentSummary] = Field(
        default_factory=list,
        description="本次准备外发的工作区附件",
    )
    digest: Optional[str] = Field(default=None, description="当前预览摘要")
    duplicate_of_last_dispatch: bool = Field(
        default=False,
        description="是否与最近一次已同步内容重复",
    )
    source_timestamp: Optional[str] = Field(default=None, description="原始回复时间")


class ClawDispatchRequest(BaseModel):
    """手动同步最近回复请求"""

    force: bool = Field(default=False, description="是否忽略摘要重复检查")


class ClawDispatchResult(BaseModel):
    """Claw 最近回复同步结果"""

    success: bool = Field(default=True, description="是否执行成功")
    dispatched: bool = Field(default=False, description="这次是否真的向远端发出消息")
    reason: Optional[str] = Field(default=None, description="未发送时的原因")
    binding: SessionClawBinding = Field(..., description="同步后的绑定状态")
    preview: ClawOutboundPreview = Field(..., description="本次同步对应的出站预览")


class ChannelBindingItem(BaseModel):
    """某频道下的单个会话绑定摘要"""

    session_id: str = Field(..., description="会话 ID")
    chat_id: Optional[str] = Field(default=None, description="目标聊天 ID")
    chat_label: Optional[str] = Field(default=None, description="目标聊天显示名")
    link_status: ClawLinkStatus = Field(default="unconfigured", description="链接状态")
    last_started_at: Optional[str] = Field(default=None, description="最近一次启动时间")
    updated_at: Optional[str] = Field(default=None, description="最近更新时间")


class ChannelBindingsResponse(BaseModel):
    """频道绑定会话列表响应"""

    channel_id: str = Field(..., description="频道 ID")
    bindings: list[ChannelBindingItem] = Field(default_factory=list, description="绑定的会话列表")
