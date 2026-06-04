import type { ClawAttachmentSummary } from "@/types/claw";

// ── Formatting helpers ──

export function formatDateTime(value?: string | null): string {
  if (!value) {
    return "未记录";
  }
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) {
    return value;
  }
  return timestamp.toLocaleString("zh-CN", { hour12: false });
}

export function formatIdleDuration(value?: string | null): string {
  if (!value) {
    return "";
  }
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) {
    return "";
  }
  const now = Date.now();
  const diffMs = now - timestamp.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) {
    return "刚刚";
  }
  if (diffMins < 60) {
    return `${diffMins} 分钟前`;
  }
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) {
    return `${diffHours} 小时前`;
  }
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) {
    return `${diffDays} 天前`;
  }
  return `${Math.floor(diffDays / 30)} 个月前`;
}

export function formatFileSize(value?: number | null): string {
  if (!value || value <= 0) {
    return "大小未知";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

// ── Platform/QR constants ──

export const PLATFORM_SUPPORT_LABELS = {
  ready: "已接入",
  candidate: "候选",
  reference: "参考",
} as const;

export const AUTH_FIELD_LABELS: Record<string, string> = {
  token: "Token",
  base_url: "Base URL",
  api_base_url: "API Base URL",
  app_id: "App ID",
  app_secret: "App Secret",
  client_id: "Client ID",
  client_secret: "Client Secret",
};

export type SupportedManualPlatform = "weixin" | "feishu" | "dingtalk";

export const PLATFORM_FORM_PRESETS: Record<
  SupportedManualPlatform,
  {
    namePlaceholder: string;
    accountLabel: string;
    accountPlaceholder: string;
    tokenLabel: string;
    tokenPlaceholder: string;
    baseLabel: string;
    basePlaceholder: string;
    defaultBaseUrl: string;
  }
> = {
  weixin: {
    namePlaceholder: "例如：我的微信 A",
    accountLabel: "account_id",
    accountPlaceholder: "微信 account_id",
    tokenLabel: "token",
    tokenPlaceholder: "微信 bot token",
    baseLabel: "base_url",
    basePlaceholder: "https://ilinkai.weixin.qq.com",
    defaultBaseUrl: "https://ilinkai.weixin.qq.com",
  },
  feishu: {
    namePlaceholder: "例如：我的飞书",
    accountLabel: "app_id",
    accountPlaceholder: "cli_xxx",
    tokenLabel: "app_secret",
    tokenPlaceholder: "飞书 app_secret",
    baseLabel: "api_base_url",
    basePlaceholder: "https://open.feishu.cn",
    defaultBaseUrl: "https://open.feishu.cn",
  },
  dingtalk: {
    namePlaceholder: "例如：我的钉钉",
    accountLabel: "client_id",
    accountPlaceholder: "dingxxx",
    tokenLabel: "client_secret",
    tokenPlaceholder: "钉钉 client_secret",
    baseLabel: "base_url",
    basePlaceholder: "https://oapi.dingtalk.com",
    defaultBaseUrl: "https://oapi.dingtalk.com",
  },
};

// ── QR journey helpers ──

export type QrJourneyState = "complete" | "current" | "pending" | "error";

export function getQrJourneyDotClass(state: QrJourneyState): string {
  switch (state) {
    case "complete":
      return "bg-success";
    case "current":
      return "bg-primary";
    case "error":
      return "bg-warning";
    case "pending":
    default:
      return "bg-muted-foreground/30";
  }
}

export function getQrJourneyTextClass(state: QrJourneyState): string {
  switch (state) {
    case "complete":
      return "text-foreground";
    case "current":
      return "text-foreground";
    case "error":
      return "text-warning dark:text-warning";
    case "pending":
    default:
      return "text-muted-foreground";
  }
}

// ── Attachment list renderer ──

export function renderAttachmentList(items: ClawAttachmentSummary[]) {
  return (
    <div className="mt-2 space-y-2">
      {items.map((item) => (
        <div
          key={`${item.workspace_path}:${item.display_name}`}
          className="rounded-md border border-border/60 bg-muted/10 px-3 py-2 text-xs leading-5 text-muted-foreground"
        >
          <div className="font-medium text-foreground">{item.display_name}</div>
          <div>
            {item.media_type || "未知类型"} · {formatFileSize(item.size_bytes)}
          </div>
          <div className="truncate">{item.workspace_path}</div>
          {item.imported_at ? <div>导入时间：{formatDateTime(item.imported_at)}</div> : null}
        </div>
      ))}
    </div>
  );
}
