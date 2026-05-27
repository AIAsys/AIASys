import { useState } from "react";
import { ChevronDown, Loader2, Unplug, Wifi } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { formatDateTime } from "./ChannelSessionPanel.utils";
import type { SessionClawBinding } from "@/types/claw";
import type { Channel, ChannelPlatformCatalogItem } from "@/types/channel";

interface ChannelBindingSectionProps {
  sessionId?: string;
  channels: Channel[];
  binding: SessionClawBinding | null;
  selectedChannelId: string;
  onSelectChannel: (id: string) => void;
  chatId: string;
  setChatId: (value: string) => void;
  chatLabel: string;
  setChatLabel: (value: string) => void;
  isMutating: boolean;
  canSaveBinding: boolean;
  canStartLink: boolean;
  canStopLink: boolean;
  scopeLabelShort: string;
  boundPlatformMeta: ChannelPlatformCatalogItem | null;
  getPlatformName: (platform?: string | null) => string;
  onSaveBinding: (payload: {
    channel_id?: string | null;
    connector_id?: string | null;
    chat_id?: string | null;
    chat_label?: string | null;
  }) => void | Promise<void>;
  onClearBinding: () => void | Promise<void>;
  onStartLink: () => void | Promise<void>;
  onStopLink: () => void | Promise<void>;
}

export function ChannelBindingSection({
  sessionId,
  channels,
  binding,
  selectedChannelId,
  onSelectChannel,
  chatId,
  setChatId,
  chatLabel,
  setChatLabel,
  isMutating,
  canSaveBinding,
  canStartLink,
  canStopLink,
  scopeLabelShort,
  boundPlatformMeta,
  getPlatformName,
  onSaveBinding,
  onClearBinding,
  onStartLink,
  onStopLink,
}: ChannelBindingSectionProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false);

  if (!sessionId) return null;
  const hasChatId = Boolean(binding?.chat_id);
  const selectedChannel = channels.find((c) => c.channel_id === selectedChannelId) || null;

  return (
    <>
      <div className="rounded-lg border border-border bg-background p-3">
        <div className="text-sm font-medium text-foreground">当前会话绑定</div>
        <div className="mt-1 text-xs leading-5 text-muted-foreground">
          这里决定当前会话把最后一条 assistant 可见回复回发到哪个远端聊天。
        </div>

        {/* Channel selector */}
        <div className="mt-3 grid gap-2">
          <Label htmlFor="claw-channel-select">选择频道</Label>
          <Select
            value={selectedChannelId}
            onValueChange={onSelectChannel}
            disabled={channels.length === 0 || isMutating}
          >
            <SelectTrigger id="claw-channel-select">
              <SelectValue placeholder="选择一个已保存频道" />
            </SelectTrigger>
            <SelectContent>
              {channels.map((channel) => (
                <SelectItem key={channel.channel_id} value={channel.channel_id}>
                  {getPlatformName(channel.platform)} · {channel.name}
                  {channel.enabled ? "" : "（已禁用）"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {selectedChannel ? (
            <div className="text-[11px] leading-5 text-muted-foreground">
              已选：{getPlatformName(selectedChannel.platform)} · {selectedChannel.name}
              {selectedChannel.enabled ? " · 已启用" : " · 已禁用"}
              {!selectedChannel.is_configured ? " · 未配置" : ""}
            </div>
          ) : (
            <div className="text-[11px] leading-5 text-muted-foreground">
              还没有可用的频道。请先从顶部「频道」入口创建微信、飞书或钉钉频道。
            </div>
          )}
        </div>

        {/* Primary actions */}
        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            type="button"
            variant={binding?.link_status === "running" ? "outline" : "default"}
            size="sm"
            className="flex-1 shrink-0 justify-center"
            disabled={!canStartLink}
            onClick={() => void onStartLink()}
          >
            <Wifi className="h-4 w-4" />
            {hasChatId ? "启动链接" : "开始监听"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="flex-1 shrink-0 justify-center"
            disabled={!canStopLink}
            onClick={() => void onStopLink()}
          >
            <Unplug className="h-4 w-4" />
            停止链接
          </Button>
        </div>

        {/* Status */}
        <div className="mt-2 text-xs text-muted-foreground">
          最近启动：{formatDateTime(binding?.last_started_at)}
        </div>

        {/* Advanced config */}
        <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen} className="mt-3">
          <CollapsibleTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 w-full justify-between px-2 text-xs text-muted-foreground hover:text-foreground"
            >
              <span>高级配置</span>
              <ChevronDown
                className={cn(
                  "h-4 w-4 shrink-0 transition-transform duration-200",
                  advancedOpen && "rotate-180"
                )}
              />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2 grid gap-3">
            <div className="grid gap-2">
              <Label htmlFor="claw-chat-id">目标聊天 ID</Label>
              <Input
                id="claw-chat-id"
                value={chatId}
                onChange={(event) => setChatId(event.target.value)}
                placeholder="例如：微信 wxid_xxx / 飞书 oc_xxx"
              />
              <div className="text-[11px] leading-5 text-muted-foreground">
                微信和飞书都可以先留空并直接启动监听。第一条入站消息会自动认领到
                {scopeLabelShort}。
              </div>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="claw-chat-label">目标聊天备注</Label>
              <Input
                id="claw-chat-label"
                value={chatLabel}
                onChange={(event) => setChatLabel(event.target.value)}
                placeholder="例如：客户群 / 我的手机"
              />
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={isMutating}
                onClick={() => void onClearBinding()}
              >
                <Unplug className="h-4 w-4" />
                清除绑定
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={!canSaveBinding}
                onClick={() =>
                  void onSaveBinding({
                    channel_id: selectedChannelId,
                    connector_id: selectedChannelId,
                    chat_id: chatId.trim() || null,
                    chat_label: chatLabel.trim() || null,
                  })
                }
              >
                {isMutating ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                保存绑定
              </Button>
            </div>
          </CollapsibleContent>
        </Collapsible>

        {boundPlatformMeta && !boundPlatformMeta.runtime_enabled ? (
          <div className="mt-2 text-[11px] leading-5 text-muted-foreground">
            {boundPlatformMeta.display_name} 已列入平台目录，但当前 runtime 还没接通；现在可直接使用微信和飞书。
          </div>
        ) : null}
      </div>
    </>
  );
}
