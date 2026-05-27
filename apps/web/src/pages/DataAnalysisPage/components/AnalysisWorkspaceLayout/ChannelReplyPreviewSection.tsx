import { Loader2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { ClawOutboundPreview } from "@/types/claw";
import { formatDateTime, renderAttachmentList } from "./ChannelSessionPanel.utils";

interface ChannelReplyPreviewSectionProps {
  preview: ClawOutboundPreview | null;
  isDispatching: boolean;
  selectedPlatformName: string;
  scopeLabel: string;
  onDispatchLastReply: (options?: { force?: boolean }) => void | Promise<unknown>;
}

export function ChannelReplyPreviewSection({
  preview,
  isDispatching,
  selectedPlatformName,
  scopeLabel,
  onDispatchLastReply,
}: ChannelReplyPreviewSectionProps) {
  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-foreground">最近回复预览</div>
          <div className="mt-1 text-xs leading-5 text-muted-foreground">
            {scopeLabel}最近一条 assistant 可见回复会按{selectedPlatformName}的当前可用格式做轻量整理，再作为出站内容同步。
          </div>
        </div>
        <Button
          type="button"
          size="sm"
          disabled={isDispatching || !preview?.has_candidate}
          onClick={() => void onDispatchLastReply()}
        >
          {isDispatching ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
          同步最近回复
        </Button>
      </div>
      <div className="mt-3 text-[11px] text-muted-foreground">
        原始时间：{formatDateTime(preview?.source_timestamp)}
        {preview?.duplicate_of_last_dispatch ? " · 与最近一次同步重复" : ""}
      </div>
      <Textarea
        className="mt-3 min-h-[120px] text-xs"
        readOnly
        value={
          preview?.formatted_text ||
          (preview?.attachments?.length
            ? "当前这次同步没有额外文本，将只发送下方附件。"
            : null) ||
          "当前还没有可同步的 assistant 回复。"
        }
      />
      {preview?.attachments?.length ? (
        <div className="mt-3">
          <div className="text-xs font-medium text-foreground">
            本次预计外发附件 · {preview.attachments.length} 个
          </div>
          {renderAttachmentList(preview.attachments)}
        </div>
      ) : null}
      <div className="mt-2 text-[11px] leading-5 text-muted-foreground">
        预计分片 {preview?.chunks.length || 0} 段；当前只做出站同步，不会把工具调用、推理过程或系统提示发到远端。
      </div>
    </div>
  );
}
