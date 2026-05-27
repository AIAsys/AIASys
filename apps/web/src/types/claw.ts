export type ClawConnectorPlatform = "weixin" | "feishu" | "dingtalk";
export type ClawPlatformSupportStatus = "ready" | "candidate" | "reference";
export type ClawLinkStatus = "unconfigured" | "stopped" | "running" | "error";
export type ClawOutboundPolicy = "latest_assistant_reply";
export type ClawQrLoginStatus = "wait" | "scaned" | "confirmed" | "expired" | "error";

export interface ClawConnector {
  connector_id: string;
  channel_id?: string | null;
  platform: ClawConnectorPlatform;
  name: string;
  account_id: string;
  base_url: string;
  has_token: boolean;
  token_masked?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ClawPlatformCatalogItem {
  platform: ClawConnectorPlatform;
  display_name: string;
  description: string;
  support_status: ClawPlatformSupportStatus;
  runtime_enabled: boolean;
  supports_inbound: boolean;
  supports_outbound: boolean;
  supports_typing: boolean;
  supports_inbound_files: boolean;
  supports_qr_login?: boolean;
  supports_outbound_files: boolean;
  transport: string;
  entry_hint: string;
  auth_fields: string[];
  default_priority: number;
  notes?: string | null;
}

export interface ClawAttachmentSummary {
  display_name: string;
  workspace_path: string;
  media_type?: string | null;
  size_bytes?: number | null;
  imported_to_workspace: boolean;
  imported_at?: string | null;
}

export interface StartClawQrLoginPayload {
  platform: ClawConnectorPlatform;
  bot_type?: string;
}

export interface ClawQrLoginSession {
  flow_id: string;
  platform: ClawConnectorPlatform;
  status: ClawQrLoginStatus;
  qrcode: string;
  qrcode_url?: string | null;
  expires_at?: string | null;
  message?: string | null;
  connector?: ClawConnector | null;
}

// 兼容旧名
export type ClawWeixinQrLoginStatus = ClawQrLoginStatus;
export type StartClawWeixinQrLoginPayload = StartClawQrLoginPayload;
export type ClawWeixinQrLoginSession = ClawQrLoginSession;

export interface UpdateSessionClawBindingPayload {
  channel_id?: string | null;
  connector_id?: string | null;
  chat_id?: string | null;
  chat_label?: string | null;
  outbound_policy?: ClawOutboundPolicy;
}

export interface SessionClawBinding {
  session_id: string;
  channel_id?: string | null;
  connector_id?: string | null;
  connector?: ClawConnector | null;
  chat_id?: string | null;
  chat_label?: string | null;
  outbound_policy: ClawOutboundPolicy;
  auto_sync_enabled: boolean;
  link_status: ClawLinkStatus;
  last_error?: string | null;
  last_started_at?: string | null;
  last_stopped_at?: string | null;
  last_dispatched_at?: string | null;
  last_dispatched_digest?: string | null;
  last_inbound_at?: string | null;
  last_inbound_message_id?: string | null;
  last_inbound_text?: string | null;
  last_inbound_attachments: ClawAttachmentSummary[];
  runtime_active: boolean;
  runtime_bound_session_ids: string[];
  runtime_bound_chat_ids: string[];
  runtime_last_inbound_at?: string | null;
  runtime_last_outbound_at?: string | null;
  runtime_last_error?: string | null;
  updated_at: string;
}

export interface ClawOutboundPreview {
  session_id: string;
  channel_id?: string | null;
  connector_id?: string | null;
  platform?: ClawConnectorPlatform | null;
  has_candidate: boolean;
  raw_text: string;
  formatted_text: string;
  chunks: string[];
  attachments: ClawAttachmentSummary[];
  digest?: string | null;
  duplicate_of_last_dispatch: boolean;
  source_timestamp?: string | null;
}

export interface ClawGatewaySession {
  session_id: string;
  session_key: string;
  platform: string;
  chat_type: string;
  chat_id: string;
  title: string;
  status: string;
  message_count: number;
  created_at: string;
  updated_at?: string | null;
  connector_id?: string | null;
  link_status?: string | null;
  auto_sync_enabled: boolean;
}

export interface DispatchClawReplyPayload {
  force?: boolean;
}

export interface ClawDispatchResult {
  success: boolean;
  dispatched: boolean;
  reason?: string | null;
  binding: SessionClawBinding;
  preview: ClawOutboundPreview;
}

export interface ChannelBindingItem {
  session_id: string;
  chat_id?: string | null;
  chat_label?: string | null;
  link_status: ClawLinkStatus;
  last_started_at?: string | null;
  updated_at?: string | null;
}

export interface ChannelBindingsResponse {
  channel_id: string;
  bindings: ChannelBindingItem[];
}
