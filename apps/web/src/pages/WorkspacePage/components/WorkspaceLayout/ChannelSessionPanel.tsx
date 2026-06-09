import { useEffect, useMemo, useState } from "react";
import { FolderOpen, GitBranch, Link2, RefreshCw, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
} from "@/components/ui/select";
import type {
  ClawQrLoginSession,
  SessionClawBinding,
} from "@/types/claw";
import type {
  Channel,
  ChannelPlatformCatalogItem,
  CreateChannelPayload,
} from "@/types/channel";

import { ChannelAssetsSection } from "./ChannelAssetsSection";


interface ChannelSessionPanelProps {
  sessionId?: string;
  mode?: "session";
  platforms: ChannelPlatformCatalogItem[];
  channels: Channel[];
  binding: SessionClawBinding | null;
  qrLogin: ClawQrLoginSession | null;
  isLoading: boolean;
  isMutating: boolean;
  isQrLoginStarting: boolean;
  isQrLoginPolling: boolean;
  error: string | null;
  notice: string | null;
  onReload: () => void | Promise<void>;
  onCreateChannel: (payload: CreateChannelPayload) => void | Promise<void>;
  onDeleteChannel?: (channelId: string) => void | Promise<void>;
  onUpdateChannelEnabled?: (channelId: string, enabled: boolean) => void | Promise<void>;
  onSaveBinding: (payload: {
    channel_id?: string | null;
    connector_id?: string | null;
    chat_id?: string | null;
    chat_label?: string | null;
  }) => void | Promise<void>;
  onClearBinding: () => void | Promise<void>;
  onStartLink: () => void | Promise<void>;
  onStopLink: () => void | Promise<void>;
  onStartQrLogin: (platform: string) => Promise<ClawQrLoginSession | null>;
  onPollQrLogin: (platform: string) => Promise<ClawQrLoginSession | null>;
  onClearQrLogin?: () => void;
  onClose?: () => void;
  availableSessionGroups?: Array<{
    workspace_id: string;
    workspace_title: string;
    sessions: Array<{ session_id: string; title?: string | null }>;
  }>;
  allSessions?: Array<{ session_id: string; title?: string | null }>;
  onSelectSession?: (sessionId: string) => void;
}

export function ChannelSessionPanel({
  sessionId,
  platforms,
  channels,
  binding,
  qrLogin,
  isLoading,
  isMutating,
  isQrLoginStarting,
  isQrLoginPolling,
  error,
  notice,
  onReload,
  onCreateChannel,
  onDeleteChannel,
  onUpdateChannelEnabled,
  onSaveBinding,
  onClearBinding,
  onStartLink,
  onStopLink,
  onStartQrLogin,
  onPollQrLogin,
  onClearQrLogin,
  onClose,
  availableSessionGroups = [],
  allSessions = [],
  onSelectSession,
}: ChannelSessionPanelProps) {
  const scopeLabel = "当前会话";
  const scopeLabelShort = "会话";
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [selectedChannelId, setSelectedChannelId] = useState("");

  useEffect(() => {
    setSelectedChannelId(binding?.channel_id || binding?.connector_id || channels[0]?.channel_id || "");
  }, [binding?.channel_id, binding?.connector_id, channels]);

  const selectedChannel = useMemo(
    () =>
      channels.find((item) => item.channel_id === selectedChannelId) ||
      null,
    [channels, selectedChannelId],
  );
  const platformMap = useMemo(
    () => new Map<string, ChannelPlatformCatalogItem>(platforms.map((item) => [item.platform, item])),
    [platforms],
  );
  const getPlatformName = (platform?: string | null) =>
    (platform ? platformMap.get(platform as string)?.display_name : null) ||
    platform ||
    "未标记";



  // ── QR journey state ──
  const qrStatus = qrLogin?.status ?? null;
  const isQrAutoPolling = Boolean(qrLogin && ["wait", "scaned"].includes(qrLogin.status));
  const isLinkReady = binding?.link_status === "running" || Boolean(binding?.runtime_active);
  const qrStatusText =
    qrStatus === "confirmed"
      ? "已确认"
      : qrStatus === "scaned"
        ? "已扫码"
        : qrStatus === "expired"
          ? "已过期"
          : qrStatus === "error"
            ? "异常"
            : qrLogin
              ? "待扫码"
              : "未开始";
  const qrStartButtonLabel = qrLogin
    ? qrStatus === "confirmed"
      ? "重新登录"
      : "重新获取二维码"
    : "获取二维码";
  const qrProgressTitle =
    isQrLoginStarting && !qrLogin
      ? "正在生成二维码"
      : !qrLogin
        ? "还没有开始扫码登录"
        : qrStatus === "scaned"
          ? "已扫码，等待手机确认"
          : qrStatus === "confirmed"
            ? isLinkReady
              ? "连接已保存，监听已就绪"
              : "二维码已确认，正在准备连接"
            : qrStatus === "expired"
              ? "二维码已过期"
              : "等待扫码";
  const qrProgressDetail =
    isQrLoginStarting && !qrLogin
      ? "二维码创建成功后会自动打开，并开始自动检查状态。"
      : !qrLogin
        ? "点击「获取二维码」后，这里会展示二维码预览、扫码进度和下一步提示。"
        : qrStatus === "scaned"
          ? `请在${qrLogin?.platform ? getPlatformName(qrLogin.platform) : ""}里点确认。确认后会自动保存连接，并继续推进后续监听状态。`
          : qrStatus === "confirmed"
            ? !sessionId
              ? "连接已创建。请在需要使用的会话中，从右侧频道页签进行绑定和启动。"
              : isLinkReady
                ? binding?.chat_id
                  ? `${scopeLabel} 已连接到远端聊天，可以继续交互。`
                  : `连接已经保存；收到第一条消息后会自动认领到${scopeLabelShort}。`
                : "确认已完成，系统正在保存连接或等待后续监听完成。"
            : qrStatus === "expired"
              ? "请重新获取二维码并再次扫码；如果后端已刷新，面板会自动展示新的二维码。"
              : "页面会自动检查扫码状态，不需要频繁手动刷新。";

  type QrJourneyState = "complete" | "current" | "pending" | "error";

  const qrJourneySteps = [
    {
      key: "qrcode",
      label: "二维码",
      detail: isQrLoginStarting && !qrLogin ? "生成中" : qrLogin ? "已生成" : "未开始",
      state: isQrLoginStarting && !qrLogin
        ? "current"
        : qrLogin
          ? "complete"
          : "pending" as QrJourneyState,
    },
    {
      key: "scan",
      label: "扫码",
      detail:
        qrStatus === "confirmed"
          ? "已扫码"
          : qrStatus === "scaned"
            ? "已扫码"
            : qrStatus === "wait"
              ? "等待扫码"
              : qrStatus === "expired"
                ? "请重扫"
                : "未开始",
      state:
        qrStatus === "confirmed" || qrStatus === "scaned"
          ? "complete"
          : qrStatus === "wait"
            ? "current"
            : qrStatus === "expired"
              ? "error"
              : "pending" as QrJourneyState,
    },
    {
      key: "confirm",
      label: "确认",
      detail:
        qrStatus === "confirmed"
          ? "已确认"
          : qrStatus === "scaned"
            ? "等待确认"
            : qrStatus === "expired"
              ? "已中断"
              : "未确认",
      state:
        qrStatus === "confirmed"
          ? "complete"
          : qrStatus === "scaned"
            ? "current"
            : qrStatus === "expired"
              ? "error"
              : "pending" as QrJourneyState,
    },
    {
      key: "link",
      label: "连接",
      detail:
        binding?.link_status === "error"
          ? "启动异常"
          : isLinkReady
            ? binding?.chat_id
              ? "已接入聊天"
              : "等待首聊"
            : qrStatus === "confirmed" || Boolean(binding?.channel_id || binding?.connector_id)
              ? "准备中"
              : "未连接",
      state:
        binding?.link_status === "error"
          ? "error"
          : isLinkReady
            ? "complete"
            : qrStatus === "confirmed" || Boolean(binding?.channel_id || binding?.connector_id)
              ? "current"
              : "pending" as QrJourneyState,
    },
  ];

  const qrDisplayValue = qrLogin?.qrcode_url || qrLogin?.qrcode || "";

  // ── Effects ──
  useEffect(() => {
    if (!qrLogin || !["wait", "scaned"].includes(qrLogin.status) || isQrLoginPolling) {
      return;
    }
    const timer = window.setTimeout(() => {
      void onPollQrLogin(qrLogin.platform);
    }, 2500);
    return () => window.clearTimeout(timer);
  }, [isQrLoginPolling, onPollQrLogin, qrLogin]);

  const statusLabel = binding?.link_status === "running"
    ? binding?.chat_id ? "运行中" : "等待首聊"
    : binding?.link_status === "error"
      ? "异常"
      : binding?.link_status === "stopped"
        ? "已配置"
        : "未绑定";
  const statusColor = binding?.link_status === "running"
    ? "text-success"
    : binding?.link_status === "error"
      ? "text-error"
      : binding?.link_status === "stopped"
        ? "text-tertiary"
        : "text-muted-foreground";

  // ── Render ──
  return (
    <div className="flex h-full flex-col bg-background">
      {/* Header */}
      <div className="shrink-0 border-b border-border/60 px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <Link2 className="h-4 w-4" />
              频道远程连接
            </div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              {sessionId
                ? `${scopeLabel}的 assistant 回复可按规则同步到远端会话。`
                : "管理通信渠道频道资产，创建微信、飞书或钉钉频道。"}
            </div>
            {sessionId && binding ? (
              <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
                <span className={`font-medium ${statusColor}`}>{statusLabel}</span>
                {selectedChannel?.name ? (
                  <span className="text-muted-foreground">
                    · {getPlatformName(selectedChannel.platform)} · {selectedChannel.name}
                  </span>
                ) : null}
                {binding.chat_label || binding.chat_id ? (
                  <span className="text-muted-foreground">
                    · {binding.chat_label || binding.chat_id}
                  </span>
                ) : null}
              </div>
            ) : null}
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-8 w-8 rounded-xl border-border bg-background text-muted-foreground shadow-sm"
              disabled={isLoading}
              onClick={() => void onReload()}
              title="刷新"
            >
              <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
            </Button>
            {onClose ? (
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-8 w-8 rounded-xl border-border bg-background text-muted-foreground shadow-sm"
                onClick={onClose}
                title="关闭"
              >
                <X className="h-4 w-4" />
              </Button>
            ) : null}
          </div>
        </div>

        {error ? (
          <div className="mt-3 rounded-lg border border-warning/20 bg-warning-container px-3 py-2 text-xs leading-5 text-warning">
            {error}
          </div>
        ) : null}

        {notice ? (
          <div className="mt-3 rounded-lg border border-border bg-muted/20 px-3 py-2 text-xs leading-5 text-foreground">
            {notice}
          </div>
        ) : null}
      </div>

      {/* Body */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {/* Session Selector */}
        {onSelectSession ? (
          <CompactSessionSelector
            sessionId={sessionId}
            availableSessionGroups={availableSessionGroups}
            onSelectSession={onSelectSession}
          />
        ) : null}

        <Accordion type="multiple" defaultValue={["assets"]} className="space-y-3">
            {/* Block 1: Channel Assets */}
            <AccordionItem value="assets" className="rounded-lg border border-border bg-background px-3 py-1">
              <AccordionTrigger className="text-sm font-medium hover:no-underline py-3">
                频道资产
              </AccordionTrigger>
              <AccordionContent>
                <ChannelAssetsSection
                  channels={channels}
                  platforms={platforms}
                  qrLogin={qrLogin}
                  selectedChannelId={selectedChannelId}
                  isMutating={isMutating}
                  isQrLoginStarting={isQrLoginStarting}
                  isQrLoginPolling={isQrLoginPolling}
                  onSelectChannel={setSelectedChannelId}
                  onCreateChannel={onCreateChannel}
                  onDeleteChannel={onDeleteChannel}
                  onUpdateChannelEnabled={onUpdateChannelEnabled}
                  onStartQrLogin={onStartQrLogin}
                  onPollQrLogin={onPollQrLogin}
                  onClearQrLogin={onClearQrLogin}
                  getPlatformName={getPlatformName}
                  sessionId={sessionId}
                  binding={binding}
                  allSessions={allSessions}
                  availableSessionGroups={availableSessionGroups}
                  onSaveBinding={onSaveBinding}
                  onClearBinding={onClearBinding}
                  onStartLink={onStartLink}
                  onStopLink={onStopLink}
                  qrDisplayValue={qrDisplayValue}
                  qrStatusText={qrStatusText}
                  qrStartButtonLabel={qrStartButtonLabel}
                  qrProgressTitle={qrProgressTitle}
                  qrProgressDetail={qrProgressDetail}
                  isQrAutoPolling={isQrAutoPolling}
                  qrJourneySteps={qrJourneySteps}
                  showCreateForm={showCreateForm}
                  setShowCreateForm={setShowCreateForm}
                  selectedChannel={selectedChannel}
                />
              </AccordionContent>
            </AccordionItem>



          </Accordion>
      </div>
    </div>
  );
}

function CompactSessionSelector({
  sessionId,
  availableSessionGroups,
  onSelectSession,
}: {
  sessionId?: string;
  availableSessionGroups: Array<{
    workspace_id: string;
    workspace_title: string;
    sessions: Array<{ session_id: string; title?: string | null }>;
  }>;
  onSelectSession: (id: string) => void;
}) {
  const currentSession = availableSessionGroups
    .flatMap((g) => g.sessions)
    .find((s) => s.session_id === sessionId);
  const currentWorkspace = availableSessionGroups.find((g) =>
    g.sessions.some((s) => s.session_id === sessionId),
  );
  return (
    <div className="mb-3 rounded-md border border-border">
      <div className="flex items-center gap-1.5 px-3 py-2 text-xs text-muted-foreground border-b border-border bg-muted/20">
        <GitBranch className="h-3.5 w-3.5" /> 绑定会话
      </div>
      <Select value={sessionId || ""} onValueChange={onSelectSession}>
        <SelectTrigger className="border-0 rounded-none bg-transparent h-9 text-sm focus:ring-0">
          <div className="flex items-center gap-2 min-w-0">
            <FolderOpen className="h-4 w-4 text-warning shrink-0" />
            <span className="truncate">
              {currentSession?.title || currentSession?.session_id?.slice(0, 8) || "选择会话"}
            </span>
            {currentWorkspace ? (
              <span className="text-xs text-muted-foreground shrink-0">
                · {currentWorkspace.workspace_title}
              </span>
            ) : null}
          </div>
        </SelectTrigger>
        <SelectContent>
          {availableSessionGroups.map((group) => (
            <SelectGroup key={group.workspace_id}>
              <SelectLabel className="flex items-center gap-1 text-xs font-medium text-muted-foreground px-2 py-1.5">
                <FolderOpen className="h-3 w-3" /> {group.workspace_title}
              </SelectLabel>
              {group.sessions.map((s) => (
                <SelectItem key={s.session_id} value={s.session_id} className="pl-6 text-sm">
                  {s.title || s.session_id.slice(0, 8)}
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
