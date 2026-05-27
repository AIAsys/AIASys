export type ChannelPlatform = "weixin" | "feishu" | "dingtalk";

export interface ChannelPlatformCatalogItem {
  platform: ChannelPlatform;
  display_name: string;
  description: string;
  support_status: "ready" | "candidate" | "reference";
  runtime_enabled: boolean;
  auth_fields: string[];
  supports_qr_login: boolean;
  supports_inbound?: boolean;
  supports_outbound?: boolean;
  supports_typing?: boolean;
  supports_inbound_files?: boolean;
  supports_outbound_files?: boolean;
  transport?: string;
  entry_hint?: string;
  default_priority?: number;
  notes?: string | null;
}

export interface Channel {
  channel_id: string;
  platform: ChannelPlatform;
  enabled: boolean;
  name: string;
  account_id: string;
  token_masked?: string | null;
  base_url: string;
  home_chat_id: string;
  allowed_users: string[];
  app_id: string;
  app_secret: string;
  is_configured: boolean;
}

export interface CreateChannelPayload {
  channel_id: string;
  platform: ChannelPlatform;
  name?: string;
  account_id?: string;
  token?: string;
  base_url?: string;
  home_chat_id?: string;
  allowed_users?: string[];
  app_id?: string;
  app_secret?: string;
}

export interface UpdateChannelPayload {
  name?: string;
  account_id?: string;
  token?: string;
  base_url?: string;
  home_chat_id?: string;
  allowed_users?: string[];
  app_id?: string;
  app_secret?: string;
}

export interface UpdateChannelEnabledPayload {
  enabled: boolean;
}

export interface ChannelEnabledResult {
  ok: boolean;
  channel_id: string;
  enabled: boolean;
}

export interface DeleteChannelResult {
  ok: boolean;
  channel_id: string;
}
