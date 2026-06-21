import { useEffect, useState } from "react";
import {
  CheckCircle2,
  Clock3,
  Loader2,
  MessageCircle,
  Plug,
  Power,
  PowerOff,
  QrCode,
  RefreshCw,
  Send,
  Trash2,
  Users,
  ChevronDown,
  ChevronRight,
  FolderOpen,
  MessageSquare,
  Link2,
} from "lucide-react";
import { QRCodeSVG } from "qrcode.react";

import { Button } from "@/components/ui/button";
import {
  FileUploadToast,
  useFileUploadToast,
} from "@/components/file/FileUploadToast";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

import {
  getChannelClawBindings,
  saveSessionClawBinding,
  getClawErrorMessage,
} from "@/lib/api/claw";
import { cn } from "@/lib/utils";
import type {
  Channel,
  ChannelPlatform,
  ChannelPlatformCatalogItem,
  CreateChannelPayload,
} from "@/types/channel";
import type { ChannelBindingItem, ClawQrLoginSession, SessionClawBinding } from "@/types/claw";

type ManualChannelPlatform = "weixin" | "feishu" | "dingtalk";

const PLATFORM_CARD_GRID_CLASS = "grid gap-2 [grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr))]";
const QR_PROGRESS_GRID_CLASS = "mt-3 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr))]";

interface ChannelAssetsSectionProps {
  channels: Channel[];
  platforms: ChannelPlatformCatalogItem[];
  qrLogin: ClawQrLoginSession | null;
  selectedChannelId: string;
  isMutating: boolean;
  isQrLoginStarting: boolean;
  isQrLoginPolling: boolean;
  qrLoginError?: string | null;
  onSelectChannel: (id: string) => void;
  onCreateChannel: (payload: CreateChannelPayload) => void | Promise<void>;
  onDeleteChannel?: (channelId: string) => void | Promise<void>;
  onUpdateChannelEnabled?: (channelId: string, enabled: boolean) => void | Promise<void>;
  onStartQrLogin: (platform: string) => Promise<ClawQrLoginSession | null>;
  onPollQrLogin: (platform: string) => Promise<ClawQrLoginSession | null>;
  onClearQrLogin?: () => void;
  getPlatformName: (platform?: string | null) => string;
  sessionId?: string;
  binding: SessionClawBinding | null;
  onSaveBinding?: (payload: {
    channel_id?: string | null;
    connector_id?: string | null;
    chat_id?: string | null;
    chat_label?: string | null;
  }) => void | Promise<void>;
  onClearBinding?: () => void | Promise<void>;
  onStartLink?: () => void | Promise<void>;
  onStopLink?: () => void | Promise<void>;
  qrDisplayValue: string;
  qrStatusText: string;
  qrStartButtonLabel: string;
  qrProgressTitle: string;
  qrProgressDetail: string;
  isQrAutoPolling: boolean;
  qrJourneySteps: Array<{
    key: string;
    label: string;
    detail: string;
    state: string;
  }>;
  showCreateForm: boolean;
  setShowCreateForm: (value: boolean) => void;
  selectedChannel: Channel | null;
  allSessions?: Array<{ session_id: string; title?: string | null }>;
  availableSessionGroups?: Array<{
    workspace_id: string;
    workspace_title: string;
    sessions: Array<{ session_id: string; title?: string | null }>;
  }>;
}

function getQrJourneyDotClass(state: string): string {
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

function getQrJourneyTextClass(state: string): string {
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

function formatDateTime(value?: string | null): string {
  if (!value) {
    return "未记录";
  }
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) {
    return value;
  }
  return timestamp.toLocaleString("zh-CN", { hour12: false });
}

const PLATFORM_PRESETS: Record<
  ManualChannelPlatform,
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

function isManualChannelPlatform(value: string): value is ManualChannelPlatform {
  return value in PLATFORM_PRESETS;
}

const PLATFORM_ACCENT: Partial<Record<ChannelPlatform, string>> = {
  weixin: "bg-[#18A058] text-white",
  feishu: "bg-[#2563EB] text-white",
  dingtalk: "bg-[#1677FF] text-white",
};

function getPlatformIcon(platform: ChannelPlatform) {
  if (platform === "weixin") {
    return MessageCircle;
  }
  return Send;
}

function getSupportStatusLabel(status: ChannelPlatformCatalogItem["support_status"]): string {
  if (status === "ready") return "已接入";
  if (status === "candidate") return "待接入";
  return "参考";
}

function getSupportStatusClass(item: ChannelPlatformCatalogItem): string {
  if (item.runtime_enabled) {
    return "border-success/20 bg-success-container text-success";
  }
  if (item.support_status === "candidate") {
    return "border-warning/20 bg-warning-container text-warning";
  }
  return "border-border bg-muted text-muted-foreground";
}

function countConfiguredChannels(channels: Channel[], platform: ChannelPlatform): number {
  return channels.filter((channel) => channel.platform === platform).length;
}

export function ChannelAssetsSection({
  channels,
  platforms,
  qrLogin,
  selectedChannelId,
  isMutating,
  isQrLoginStarting,
  isQrLoginPolling,
  qrLoginError,
  onSelectChannel,
  onDeleteChannel,
  onUpdateChannelEnabled,
  onStartQrLogin,
  onPollQrLogin,
  onClearQrLogin,
  getPlatformName,
  qrDisplayValue,
  qrStatusText,
  qrStartButtonLabel,
  qrProgressTitle,
  qrProgressDetail,
  isQrAutoPolling,
  qrJourneySteps,
  showCreateForm,
  setShowCreateForm,
  onCreateChannel,
  selectedChannel,
  sessionId,
  binding,
  onSaveBinding,
  onClearBinding,
  onStartLink,
  onStopLink,
  availableSessionGroups = [],
}: ChannelAssetsSectionProps) {
  const { toasts, showError } = useFileUploadToast();
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [pendingDeleteChannelId, setPendingDeleteChannelId] = useState<string | null>(null);
  const [isDeletingChannel, setIsDeletingChannel] = useState(false);
  const [qrDialogOpen, setQrDialogOpen] = useState(false);
  const [qrDialogPlatform, setQrDialogPlatform] = useState<string>("");
  const [channelBindingsMap, setChannelBindingsMap] = useState<Record<string, ChannelBindingItem[]>>({});
  const [editingChannelId, setEditingChannelId] = useState<string | null>(null);
  const [editChatId, setEditChatId] = useState("");
  const [editChatLabel, setEditChatLabel] = useState("");
  const [creatingForChannelId, setCreatingForChannelId] = useState<string | null>(null);
  const [createSessionId, setCreateSessionId] = useState("");
  const [createChatId, setCreateChatId] = useState("");
  const [createChatLabel, setCreateChatLabel] = useState("");
  const [isBindingSaving, setIsBindingSaving] = useState(false);
  const [bindingError, setBindingError] = useState<string | null>(null);
  const [bindingNotice, setBindingNotice] = useState<string | null>(null);

  useEffect(() => {
    if (channels.length === 0) {
      setChannelBindingsMap({});
      return;
    }
    const abortCtrl = new AbortController();
    Promise.all(
      channels.map(async (ch) => {
        try {
          const resp = await getChannelClawBindings(ch.channel_id);
          if (!abortCtrl.signal.aborted) {
            setChannelBindingsMap((prev) => ({ ...prev, [ch.channel_id]: resp.bindings }));
          }
        } catch {
          // ignore
        }
      }),
    );
    return () => abortCtrl.abort();
  }, [channels]);

  const [createPlatform, setCreatePlatform] = useState<ManualChannelPlatform>("weixin");
  const [createName, setCreateName] = useState("");
  const [createAccountId, setCreateAccountId] = useState("");
  const [createToken, setCreateToken] = useState("");
  const [createBaseUrl, setCreateBaseUrl] = useState(PLATFORM_PRESETS.weixin.defaultBaseUrl);

  const confirmDelete = async () => {
    if (!pendingDeleteChannelId || !onDeleteChannel) {
      setShowDeleteDialog(false);
      setPendingDeleteChannelId(null);
      return;
    }
    setIsDeletingChannel(true);
    try {
      await onDeleteChannel(pendingDeleteChannelId);
      setShowDeleteDialog(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "删除频道失败";
      showError(message);
    } finally {
      setIsDeletingChannel(false);
      setPendingDeleteChannelId(null);
    }
  };

  const visiblePlatforms = [...platforms].sort(
    (left, right) => (right.default_priority ?? 0) - (left.default_priority ?? 0),
  );
  const readyPlatforms = visiblePlatforms.filter((item) => item.runtime_enabled);
  const futurePlatformCount = visiblePlatforms.length - readyPlatforms.length;
  const preset = PLATFORM_PRESETS[createPlatform] ?? PLATFORM_PRESETS.feishu;

  const resetCreateForm = () => {
    setCreateName("");
    setCreateAccountId("");
    setCreateToken("");
    const fallback = PLATFORM_PRESETS[createPlatform] ?? PLATFORM_PRESETS.feishu;
    setCreateBaseUrl(fallback.defaultBaseUrl);
  };

  const openCreateFormForPlatform = (platform: ChannelPlatform) => {
    if (!isManualChannelPlatform(platform)) {
      return;
    }
    setCreatePlatform(platform);
    setCreateBaseUrl(PLATFORM_PRESETS[platform].defaultBaseUrl);
    setShowCreateForm(true);
  };

  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-foreground">频道资产</div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setShowCreateForm(!showCreateForm)}
        >
          {showCreateForm ? "收起手动录入" : "手动录入凭据"}
        </Button>
      </div>

      {/* Saved Channels */}
      <div className="mt-3 grid gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-sm font-medium text-foreground">已保存频道</div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              共 {channels.length} 个频道，{channels.filter((c) => c.enabled).length} 个已启用。
            </div>
          </div>
        </div>
        {channels.length > 0 ? (
          <div className="grid gap-2">
            {channels.map((channel) => {
              const Icon = getPlatformIcon(channel.platform);
              const bindings = channelBindingsMap[channel.channel_id] ?? [];
              const runningBindings = bindings.filter((b) => b.link_status === "running");
              const isSelected = selectedChannelId === channel.channel_id;
              return (
                <div
                  key={channel.channel_id}
                  className={cn(
                    "min-w-0 rounded-md border p-3 cursor-pointer transition-colors",
                    isSelected
                      ? "border-primary/40 bg-primary/5"
                      : "border-border/70 bg-background hover:bg-muted/20",
                  )}
                  onClick={() => onSelectChannel(channel.channel_id)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <div
                        className={cn(
                          "flex h-8 w-8 shrink-0 items-center justify-center rounded-md",
                          PLATFORM_ACCENT[channel.platform] || "bg-muted text-muted-foreground",
                        )}
                      >
                        <Icon className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-sm font-medium text-foreground">{channel.name}</span>
                          {channel.enabled ? (
                            <span className="rounded-full border border-success/20 bg-success-container px-1.5 py-0 text-[10px] text-success">
                              已启用
                            </span>
                          ) : (
                            <span className="rounded-full border border-border bg-muted px-1.5 py-0 text-[10px] text-muted-foreground">
                              已禁用
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] leading-4 text-muted-foreground">
                          {getPlatformName(channel.platform)} · {channel.account_id || channel.app_id || "未配置"}
                        </div>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      {onUpdateChannelEnabled ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0"
                          disabled={isMutating}
                          onClick={(e) => {
                            e.stopPropagation();
                            void onUpdateChannelEnabled(channel.channel_id, !channel.enabled);
                          }}
                          title={channel.enabled ? "禁用" : "启用"}
                        >
                          {channel.enabled ? <PowerOff className="h-3.5 w-3.5 text-warning" /> : <Power className="h-3.5 w-3.5 text-success" />}
                        </Button>
                      ) : null}
                      {onDeleteChannel ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0 text-error hover:text-error hover:bg-error-container"
                          disabled={isMutating}
                          onClick={(e) => {
                            e.stopPropagation();
                            setPendingDeleteChannelId(channel.channel_id);
                            setShowDeleteDialog(true);
                          }}
                          title="删除"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      ) : null}
                    </div>
                  </div>
                  {bindings.length > 0 ? (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <Users className="h-3 w-3 text-muted-foreground" />
                      <span className="text-[11px] text-muted-foreground">
                        已绑定 {bindings.length} 个会话
                        {runningBindings.length > 0 ? `，${runningBindings.length} 个运行中` : ""}
                      </span>
                      {bindings.slice(0, 3).map((b) => (
                        <span
                          key={b.session_id}
                          className={cn(
                            "max-w-[120px] truncate rounded-full border px-1.5 py-0 text-[10px]",
                            b.link_status === "running"
                              ? "border-success/20 bg-success-container text-success"
                              : "border-border bg-muted text-muted-foreground",
                          )}
                          title={b.chat_label || b.chat_id || b.session_id}
                        >
                          {b.chat_label || b.chat_id || b.session_id.slice(0, 8)}
                        </span>
                      ))}
                      {bindings.length > 3 ? (
                        <span className="text-[10px] text-muted-foreground">+{bindings.length - 3}</span>
                      ) : null}
                    </div>
                  ) : null}

                  {/* Session binding management */}
                  <div className="mt-2 pt-2 border-t border-border/50" onClick={(e) => e.stopPropagation()}>
                    {/* Quick action for current session */}
                    {sessionId && onSaveBinding ? (() => {
                      const isThisBound = Boolean(
                        binding &&
                          (binding.channel_id === channel.channel_id || binding.connector_id === channel.channel_id),
                      );
                      if (isThisBound) {
                        const statusLabel =
                          binding?.link_status === "running"
                            ? "运行中"
                            : binding?.link_status === "error"
                              ? "异常"
                              : "已配置";
                        const statusClass =
                          binding?.link_status === "running"
                            ? "border border-success/20 bg-success-container text-success"
                            : binding?.link_status === "error"
                              ? "border border-error/20 bg-error-container text-error"
                              : "border border-border bg-muted/20 text-muted-foreground";
                        return (
                          <div className="flex items-center gap-2 flex-wrap mb-2">
                            <span className={cn("rounded-full px-1.5 py-0 text-[10px]", statusClass)}>
                              {statusLabel}
                            </span>
                            {binding?.chat_label ? (
                              <span className="text-[11px] text-muted-foreground truncate max-w-[120px]">
                                {binding.chat_label}
                              </span>
                            ) : null}
                            <div className="ml-auto flex gap-1">
                              {onStartLink && binding?.link_status !== "running" ? (
                                <Button variant="outline" size="sm" disabled={isMutating} onClick={() => void onStartLink()}>
                                  启动链接
                                </Button>
                              ) : null}
                              {onStopLink && binding?.link_status === "running" ? (
                                <Button variant="outline" size="sm" disabled={isMutating} onClick={() => void onStopLink()}>
                                  停止链接
                                </Button>
                              ) : null}
                              {onClearBinding ? (
                                <Button variant="outline" size="sm" disabled={isMutating} onClick={() => void onClearBinding()}>
                                  解绑
                                </Button>
                              ) : null}
                            </div>
                          </div>
                        );
                      }
                      if (editingChannelId === channel.channel_id) {
                        return (
                          <div className="grid gap-2 mb-2">
                            <div className="grid gap-1">
                              <Label className="text-[11px]">目标聊天 ID</Label>
                              <Input value={editChatId} onChange={(e) => setEditChatId(e.target.value)} placeholder="可选，留空会自动认领" className="h-8 text-xs" />
                            </div>
                            <div className="grid gap-1">
                              <Label className="text-[11px]">目标聊天备注</Label>
                              <Input value={editChatLabel} onChange={(e) => setEditChatLabel(e.target.value)} placeholder="可选" className="h-8 text-xs" />
                            </div>
                            <div className="flex gap-2 justify-end">
                              <Button variant="ghost" size="sm" onClick={() => setEditingChannelId(null)}>取消</Button>
                              <Button size="sm" disabled={isMutating} onClick={() => {
                                void onSaveBinding({
                                  channel_id: channel.channel_id,
                                  connector_id: channel.channel_id,
                                  chat_id: editChatId.trim() || null,
                                  chat_label: editChatLabel.trim() || null,
                                });
                                setEditingChannelId(null);
                              }}>保存绑定</Button>
                            </div>
                          </div>
                        );
                      }
                      return (
                        <div className="flex items-center gap-2 mb-2">
                          <span className="rounded-full border border-border bg-muted px-1.5 py-0 text-[10px] text-muted-foreground">未绑定</span>
                          <Button variant="outline" size="sm" className="ml-auto" disabled={isMutating} onClick={() => {
                            setEditChatId("");
                            setEditChatLabel("");
                            setEditingChannelId(channel.channel_id);
                          }}>绑定到当前会话</Button>
                        </div>
                      );
                    })() : null}

                    {/* Full binding management */}
                    <Collapsible>
                      <CollapsibleTrigger asChild>
                        <Button variant="ghost" size="sm" className="h-7 w-full justify-between px-2 text-xs text-muted-foreground hover:text-foreground">
                          <span className="flex items-center gap-1.5">
                            <Link2 className="h-3 w-3" />
                            管理绑定
                            {bindings.length > 0 ? <span className="text-[10px]">({bindings.length})</span> : null}
                          </span>
                          <ChevronDown className="h-3.5 w-3.5 shrink-0 transition-transform duration-200 data-[state=open]:rotate-180" />
                        </Button>
                      </CollapsibleTrigger>
                      <CollapsibleContent className="mt-1">
                        {bindings.length > 0 ? (
                          <div className="grid gap-1.5 mb-2">
                            {bindings.map((b) => (
                              <div key={b.session_id} className="flex items-center gap-2 rounded-md border border-border/50 px-2 py-1.5">
                                <span className={cn(
                                  "shrink-0 rounded-full px-1.5 py-0 text-[10px]",
                                  b.link_status === "running"
                                    ? "border border-success/20 bg-success-container text-success"
                                    : b.link_status === "error"
                                      ? "border border-error/20 bg-error-container text-error"
                                      : "border border-border bg-muted/20 text-muted-foreground",
                                )}>
                                  {b.link_status === "running" ? "运行中" : b.link_status === "error" ? "异常" : "已配置"}
                                </span>
                                {(() => {
                                  const group = availableSessionGroups.find((g) => g.sessions.some((s) => s.session_id === b.session_id));
                                  const session = group?.sessions.find((s) => s.session_id === b.session_id);
                                  const sessionTitle = session?.title || b.session_id.slice(0, 8);
                                  const display = group ? `${group.workspace_title} / ${sessionTitle}` : sessionTitle;
                                  return (
                                    <span className="min-w-0 truncate text-[11px] text-foreground" title={display}>
                                      {display}
                                    </span>
                                  );
                                })()}
                                {b.chat_label ? (
                                  <span className="ml-auto shrink-0 truncate text-[10px] text-muted-foreground max-w-[80px]">{b.chat_label}</span>
                                ) : null}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="mb-2 text-[11px] text-muted-foreground">暂无绑定</div>
                        )}

                        {creatingForChannelId === channel.channel_id ? (
                          <div className="grid gap-2 rounded-md border border-border/50 p-2">
                            {bindingNotice ? (
                              <div className="rounded-md border border-success/20 bg-success-container px-2 py-1 text-[11px] text-success">{bindingNotice}</div>
                            ) : null}
                            {bindingError ? (
                              <div className="rounded-md border border-error/20 bg-error-container px-2 py-1 text-[11px] text-error">{bindingError}</div>
                            ) : null}
                            <div className="grid gap-1">
                              <Label className="text-[11px]">选择会话</Label>
                              {createSessionId ? (
                                <div className="flex items-center gap-2 text-xs">
                                  <span className="text-muted-foreground">已选择：</span>
                                  <span className="font-medium text-foreground">
                                    {(() => {
                                      const group = availableSessionGroups.find((g) => g.sessions.some((s) => s.session_id === createSessionId));
                                      const session = group?.sessions.find((s) => s.session_id === createSessionId);
                                      return group
                                        ? `${group.workspace_title} / ${session?.title || createSessionId.slice(0, 8)}`
                                        : createSessionId.slice(0, 8);
                                    })()}
                                  </span>
                                </div>
                              ) : null}
                              <div className="rounded-md border border-border max-h-[180px] overflow-y-auto">
                                {availableSessionGroups.length === 0 ? (
                                  <div className="px-3 py-2 text-xs text-muted-foreground">没有可用会话</div>
                                ) : (
                                  availableSessionGroups.map((group) => {
                                    const hasSelected = group.sessions.some((s) => s.session_id === createSessionId);
                                    return (
                                      <Collapsible key={group.workspace_id} defaultOpen={hasSelected || availableSessionGroups.length <= 3}>
                                        <CollapsibleTrigger asChild>
                                          <button
                                            type="button"
                                            className="group flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-muted/50 transition-colors"
                                          >
                                            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0 transition-transform group-data-[state=open]:rotate-90" />
                                            <FolderOpen className="h-4 w-4 text-warning shrink-0" />
                                            <span className="truncate text-foreground text-xs">{group.workspace_title}</span>
                                            <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">
                                              {group.sessions.length} 个对话
                                            </span>
                                          </button>
                                        </CollapsibleTrigger>
                                        <CollapsibleContent>
                                          {group.sessions.map((s) => (
                                            <button
                                              key={s.session_id}
                                              type="button"
                                              className={cn(
                                                "flex w-full items-center gap-2 px-3 py-1.5 pl-9 text-xs transition-colors",
                                                s.session_id === createSessionId
                                                  ? "bg-primary-container text-primary"
                                                  : "text-foreground hover:bg-muted/30",
                                              )}
                                              onClick={() => setCreateSessionId(s.session_id)}
                                            >
                                              <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-60" />
                                              <span className="truncate">{s.title || s.session_id.slice(0, 8)}</span>
                                              {s.session_id === createSessionId ? (
                                                <CheckCircle2 className="ml-auto h-3.5 w-3.5 shrink-0 text-success" />
                                              ) : null}
                                            </button>
                                          ))}
                                        </CollapsibleContent>
                                      </Collapsible>
                                    );
                                  })
                                )}
                              </div>
                            </div>
                            <div className="grid gap-1">
                              <Label className="text-[11px]">目标聊天 ID</Label>
                              <Input value={createChatId} onChange={(e) => setCreateChatId(e.target.value)} placeholder="可选，留空会自动认领" className="h-8 text-xs" />
                            </div>
                            <div className="grid gap-1">
                              <Label className="text-[11px]">目标聊天备注</Label>
                              <Input value={createChatLabel} onChange={(e) => setCreateChatLabel(e.target.value)} placeholder="可选" className="h-8 text-xs" />
                            </div>
                            <div className="flex gap-2 justify-end">
                              <Button variant="ghost" size="sm" disabled={isBindingSaving} onClick={() => {
                                setCreatingForChannelId(null);
                                setBindingError(null);
                                setBindingNotice(null);
                              }}>取消</Button>
                              <Button size="sm" disabled={isBindingSaving || !createSessionId} onClick={async () => {
                                setIsBindingSaving(true);
                                setBindingError(null);
                                setBindingNotice(null);
                                try {
                                  await saveSessionClawBinding(createSessionId, {
                                    channel_id: channel.channel_id,
                                    connector_id: channel.channel_id,
                                    chat_id: createChatId.trim() || null,
                                    chat_label: createChatLabel.trim() || null,
                                  });
                                  setBindingNotice("绑定已保存。");
                                  setCreatingForChannelId(null);
                                  // Refresh channel bindings
                                  try {
                                    const resp = await getChannelClawBindings(channel.channel_id);
                                    setChannelBindingsMap((prev) => ({ ...prev, [channel.channel_id]: resp.bindings }));
                                  } catch { /* ignore */ }
                                } catch (err) {
                                  setBindingError(getClawErrorMessage(err, "保存绑定失败"));
                                } finally {
                                  setIsBindingSaving(false);
                                }
                              }}>
                                {isBindingSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                                保存绑定
                              </Button>
                            </div>
                          </div>
                        ) : (
                          <Button variant="ghost" size="sm" className="h-7 w-full text-xs" onClick={() => {
                            setCreateSessionId(sessionId || "");
                            setCreateChatId("");
                            setCreateChatLabel("");
                            setBindingError(null);
                            setBindingNotice(null);
                            setCreatingForChannelId(channel.channel_id);
                          }}>
                            <Link2 className="h-3 w-3 mr-1" />
                            新增绑定
                          </Button>
                        )}
                      </CollapsibleContent>
                    </Collapsible>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-border bg-muted/10 px-3 py-3 text-xs leading-5 text-muted-foreground text-center">
            还没有可用的频道。扫码登录或手动录入来创建微信、飞书或钉钉频道。
          </div>
        )}
      </div>

      {/* Platform Directory */}
      <div className="mt-4 grid gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-sm font-medium text-foreground">平台目录</div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              已接入 {readyPlatforms.length} 个，待接入 {futurePlatformCount} 个。
            </div>
          </div>
        </div>
        <div className={PLATFORM_CARD_GRID_CLASS}>
          {visiblePlatforms.map((platform) => {
            const Icon = getPlatformIcon(platform.platform);
            const configuredCount = countConfiguredChannels(channels, platform.platform);
            const platformChannels = channels.filter((c) => c.platform === platform.platform);
            const hasEnabled = platformChannels.some((c) => c.enabled);
            const supportsQr = platform.supports_qr_login ?? false;
            const supportsManual = platform.runtime_enabled && (platform.auth_fields?.length ?? 0) > 0;
            return (
              <div
                key={platform.platform}
                className={cn(
                  "min-w-0 rounded-md border p-3",
                  hasEnabled
                    ? "border-success/30 bg-success-container/20 shadow-sm"
                    : "border-border/70 bg-background shadow-sm",
                )}
              >
                <div className="grid min-w-0 gap-3">
                  <div className="flex min-w-0 items-center justify-between gap-2">
                    <div
                      className={cn(
                        "flex h-10 w-10 shrink-0 items-center justify-center rounded-md",
                        PLATFORM_ACCENT[platform.platform] || "bg-muted text-muted-foreground",
                      )}
                    >
                      <Icon className="h-5 w-5" />
                    </div>
                    {hasEnabled ? (
                      <Plug className="h-4 w-4 shrink-0 text-success" />
                    ) : platform.runtime_enabled ? (
                      <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />
                    ) : (
                      <Clock3 className="h-4 w-4 shrink-0 text-muted-foreground" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="text-sm font-medium text-foreground">{platform.display_name}</div>
                      {hasEnabled ? (
                        <span className="max-w-full rounded-full border border-success/20 bg-success-container px-2 py-0.5 text-[11px] text-success">
                          已连接
                        </span>
                      ) : configuredCount > 0 ? (
                        <span className="max-w-full rounded-full border border-warning/20 bg-warning-container px-2 py-0.5 text-[11px] text-warning">
                          已保存 {configuredCount} 个
                        </span>
                      ) : (
                        <span
                          className={cn(
                            "max-w-full rounded-full border px-2 py-0.5 text-[11px]",
                            getSupportStatusClass(platform),
                          )}
                        >
                          {getSupportStatusLabel(platform.support_status)}
                        </span>
                      )}
                    </div>
                    <div className="mt-1 text-xs leading-5 text-muted-foreground">
                      {platform.description}
                    </div>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                  {platform.transport ? (
                    <span className="max-w-full break-words rounded-full border border-border bg-muted/20 px-2 py-0.5">
                      {platform.transport}
                    </span>
                  ) : null}
                  {platform.entry_hint ? (
                    <span className="max-w-full break-words rounded-full border border-border bg-muted/20 px-2 py-0.5">
                      {platform.entry_hint}
                    </span>
                  ) : null}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {supportsQr ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className={supportsManual ? "min-w-[88px] flex-1 shrink-0 justify-center" : "w-full shrink-0 justify-center"}
                      disabled={isQrLoginStarting}
                      onClick={() => {
                        setQrDialogPlatform(platform.platform);
                        setQrDialogOpen(true);
                        void onStartQrLogin(platform.platform);
                      }}
                    >
                      {isQrLoginStarting ? <Loader2 className="h-4 w-4 shrink-0 animate-spin" /> : <QrCode className="h-4 w-4 shrink-0" />}
                      扫码登录
                    </Button>
                  ) : null}
                  {supportsManual ? (
                    <Button
                      type="button"
                      variant="default"
                      size="sm"
                      className={supportsQr ? "min-w-[80px] flex-1 shrink-0 justify-center" : "w-full shrink-0 justify-center"}
                      disabled={isMutating}
                      onClick={() => openCreateFormForPlatform(platform.platform)}
                      title="手动录入凭据"
                    >
                      手动录入
                    </Button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* QR Login Dialog */}
      <Dialog
        open={qrDialogOpen}
        onOpenChange={(open) => {
          setQrDialogOpen(open);
          if (!open) onClearQrLogin?.();
        }}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <QrCode className="h-5 w-5 text-primary" />
              {getPlatformName(qrDialogPlatform)}扫码登录
            </DialogTitle>
            <DialogDescription>
              生成扫码链接，浏览器打开后扫码确认，成功后会自动创建或更新对应频道。
            </DialogDescription>
          </DialogHeader>

          {qrLoginError ? (
            <div className="rounded-md border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive">
              {qrLoginError}
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="min-w-[96px] flex-1 shrink-0 justify-center"
              disabled={isQrLoginStarting}
              onClick={() => {
                void onStartQrLogin(qrDialogPlatform || "weixin");
              }}
            >
              {isQrLoginStarting ? <Loader2 className="h-4 w-4 shrink-0 animate-spin" /> : <QrCode className="h-4 w-4 shrink-0" />}
              {qrStartButtonLabel}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="min-w-[96px] flex-1 shrink-0 justify-center"
              disabled={!qrLogin || isQrLoginPolling || qrLogin.status === "confirmed"}
              onClick={() => void onPollQrLogin(qrDialogPlatform || "weixin")}
            >
              {isQrLoginPolling ? <Loader2 className="h-4 w-4 shrink-0 animate-spin" /> : <RefreshCw className="h-4 w-4 shrink-0" />}
              立即检查
            </Button>
          </div>

          {qrLogin?.qrcode || qrLogin?.qrcode_url ? (
            <div className={QR_PROGRESS_GRID_CLASS}>
              <div className="flex items-center justify-center rounded-md border border-border/60 bg-white p-3">
                <QRCodeSVG
                  value={qrDisplayValue}
                  size={180}
                  level="M"
                  includeMargin
                />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-medium text-foreground">{qrProgressTitle}</div>
                <div className="mt-1 text-xs leading-5 text-muted-foreground">{qrProgressDetail}</div>
                {isQrAutoPolling ? (
                  <div className="mt-2 inline-flex items-center gap-2 text-xs text-muted-foreground">
                    <Loader2 className={cn("h-3.5 w-3.5", isQrLoginPolling ? "animate-spin" : "")} />
                    页面每 2.5 秒自动检查一次扫码状态。
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}

          <div className="mt-3 grid grid-cols-4 gap-2">
            {qrJourneySteps.map((step) => (
              <div
                key={step.key}
                className="flex items-start gap-2 rounded-md border border-border/60 bg-background px-2 py-2"
              >
                <span
                  className={cn(
                    "mt-1 h-2.5 w-2.5 shrink-0 rounded-full",
                    getQrJourneyDotClass(step.state),
                  )}
                />
                <div className="min-w-0">
                  <div className={cn("text-xs font-medium", getQrJourneyTextClass(step.state))}>
                    {step.label}
                  </div>
                  <div className="text-[11px] leading-5 text-muted-foreground">{step.detail}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap gap-2 text-[11px]">
            <span className="rounded-full border border-border bg-background px-2 py-0.5 text-foreground">
              状态：{qrStatusText}
            </span>
            <span className="rounded-full border border-border bg-background px-2 py-0.5 text-foreground">
              预计过期：{formatDateTime(qrLogin?.expires_at)}
            </span>
            {isQrAutoPolling ? (
              <span className="rounded-full border border-border bg-background px-2 py-0.5 text-foreground">
                自动检查：开启
              </span>
            ) : null}
          </div>

          {qrLogin?.message ? (
            <div className="text-xs leading-5 text-muted-foreground">
              {qrLogin.message}
            </div>
          ) : null}

          {qrLogin?.qrcode || qrLogin?.qrcode_url ? (
            <div className="text-xs leading-5 text-muted-foreground">
              请使用{getPlatformName(qrDialogPlatform)}扫描上方二维码。页面会自动检查扫码状态。
            </div>
          ) : (
            <div className="text-xs leading-5 text-muted-foreground">
              还没有二维码。点击"获取二维码"后，这里会直接展示可扫描的二维码。
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Create Form */}
      {showCreateForm ? (
        <div className="mt-4 grid gap-3 rounded-md border border-border/60 bg-muted/10 p-3">
          <div className="grid gap-2">
            <Label htmlFor="channel-platform">平台</Label>
            <Select
              value={createPlatform}
              onValueChange={(value) => {
                if (!isManualChannelPlatform(value)) {
                  return;
                }
                setCreatePlatform(value);
                setCreateBaseUrl(PLATFORM_PRESETS[value].defaultBaseUrl);
              }}
            >
              <SelectTrigger id="channel-platform">
                <SelectValue placeholder="选择一个平台" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="weixin">微信</SelectItem>
                <SelectItem value="feishu">飞书</SelectItem>
                <SelectItem value="dingtalk">钉钉</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="channel-name">频道名称</Label>
            <Input
              id="channel-name"
              value={createName}
              onChange={(event) => setCreateName(event.target.value)}
              placeholder={preset.namePlaceholder}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="channel-account-id">{preset.accountLabel}</Label>
            <Input
              id="channel-account-id"
              value={createAccountId}
              onChange={(event) => setCreateAccountId(event.target.value)}
              placeholder={preset.accountPlaceholder}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="channel-token">{preset.tokenLabel}</Label>
            <Input
              id="channel-token"
              type="password"
              value={createToken}
              onChange={(event) => setCreateToken(event.target.value)}
              placeholder={preset.tokenPlaceholder}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="channel-base-url">{preset.baseLabel}</Label>
            <Input
              id="channel-base-url"
              value={createBaseUrl}
              onChange={(event) => setCreateBaseUrl(event.target.value)}
              placeholder={preset.basePlaceholder}
            />
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="shrink-0"
              onClick={() => {
                resetCreateForm();
                setShowCreateForm(false);
              }}
            >
              取消
            </Button>
            <Button
              type="button"
              size="sm"
              className="shrink-0"
              disabled={
                isMutating ||
                !createName.trim() ||
                !createAccountId.trim() ||
                !createToken.trim()
              }
              onClick={() => {
                const payload: CreateChannelPayload = {
                  channel_id: `${createPlatform}_${Date.now()}`,
                  platform: createPlatform,
                  name: createName.trim(),
                  token: createToken.trim(),
                  base_url: createBaseUrl.trim(),
                };
                if (createPlatform === "weixin") {
                  payload.account_id = createAccountId.trim();
                } else {
                  payload.app_id = createAccountId.trim();
                  payload.app_secret = createToken.trim();
                }
                void onCreateChannel(payload);
                resetCreateForm();
                setShowCreateForm(false);
              }}
            >
              {isMutating ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              保存频道
            </Button>
          </div>
        </div>
      ) : null}

      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              {selectedChannel
                ? `确定要删除频道「${selectedChannel.name}」吗？`
                : "确定要删除此频道吗？"}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeletingChannel}>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void confirmDelete()}
              disabled={isDeletingChannel}
            >
              {isDeletingChannel ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : null}
              确认
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {toasts.map((toast) => (
        <FileUploadToast
          key={toast.id}
          message={toast.message}
          type={toast.type}
        />
      ))}
    </div>
  );
}
