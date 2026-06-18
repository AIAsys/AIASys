/**
 * UserMessageContent - 用户消息内容
 *
 * 专门处理用户消息的渲染，包括文本和附件
 */
import { Check, ChevronDown, FileText, Pencil, X, Hash } from "lucide-react";
import { useState, useMemo } from "react";
import { MarkdownImage } from "../MarkdownImage";
import { useChatAreaContext } from "./context";
import { TableIcon } from "./chatAreaIcons";
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
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

function AttachmentIcon({ filename }: { filename: string }) {
  const ext = filename.split(".").pop()?.toLowerCase();
  if (["csv", "xlsx", "xls", "tsv", "parquet"].includes(ext || "")) {
    return <TableIcon className="h-3 w-3 text-muted-foreground" />;
  }
  return <FileText size={12} className="text-muted-foreground" />;
}

const FILE_MENTION_RE = /@(\/(?:workspace|global)\/[^\s]+)/g;

/** 超过此行数的用户消息自动折叠 */
const COLLAPSE_LINE_THRESHOLD = 15;
/** 折叠状态下的最大高度 */
const COLLAPSED_MAX_HEIGHT = "max-h-[300px]";

interface MentionSegment {
  type: "text" | "mention";
  content: string;
  fullPath?: string;
  scope?: "workspace" | "global";
}

function splitMentions(content: string): MentionSegment[] {
  const segments: MentionSegment[] = [];
  let lastIndex = 0;
  for (const match of content.matchAll(FILE_MENTION_RE)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      segments.push({ type: "text", content: content.slice(lastIndex, index) });
    }
    const fullPath = match[1];
    segments.push({
      type: "mention",
      content: fullPath.split("/").pop() || fullPath,
      fullPath,
      scope: fullPath.startsWith("/global/") ? "global" : "workspace",
    });
    lastIndex = index + match[0].length;
  }
  if (lastIndex < content.length) {
    segments.push({ type: "text", content: content.slice(lastIndex) });
  }
  return segments;
}

function MentionTag({ segment }: { segment: MentionSegment }) {
  return (
    <span
      className="inline-flex items-center gap-1 align-middle bg-accent/60 border border-border/60 rounded px-1.5 py-0.5 text-xs text-foreground mx-0.5"
      title={segment.fullPath}
    >
      {segment.scope === "global" ? (
        <Hash size={10} className="text-muted-foreground" />
      ) : (
        <FileText size={10} className="text-muted-foreground" />
      )}
      <span className="truncate max-w-[160px]">{segment.content}</span>
    </span>
  );
}

export function UserMessageContent() {
  const {
    state: { item },
    actions: { onRewriteUserMessage },
    meta: { sessionId, isRunning = false },
  } = useChatAreaContext();
  // UserMessageContent 只在 MessageItem 内部渲染 type="message" 的用户消息
  const msgItem = item as import("@/pages/WorkspacePage/types").MessageChatItem;
  const attachments = msgItem.attachments || [];
  const imageAttachments = attachments.filter((value: string) =>
    /\.(png|jpe?g|gif|webp)$/i.test(value),
  );
  const otherAttachments = attachments.filter(
    (value: string) => !imageAttachments.includes(value),
  );
  // 确保 content 是字符串
  const content =
    typeof msgItem.content === "string"
      ? msgItem.content
      : String(msgItem.content ?? "");
  const canRewrite = Boolean(onRewriteUserMessage && msgItem.id && content.trim());
  const [isEditing, setIsEditing] = useState(false);
  const [draftContent, setDraftContent] = useState(content);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const segments = useMemo(() => splitMentions(content), [content]);

  // 长消息折叠：超过阈值行数时默认折叠，提供展开/收起切换
  const isCollapsible = useMemo(
    () => content.split("\n").length > COLLAPSE_LINE_THRESHOLD,
    [content],
  );
  const [isCollapsed, setIsCollapsed] = useState(isCollapsible);

  const handleStartEdit = () => {
    if (!canRewrite || isRunning) {
      return;
    }
    setDraftContent(content);
    setIsEditing(true);
  };

  const handleCancelEdit = () => {
    if (isSubmitting) {
      return;
    }
    setDraftContent(content);
    setIsConfirmOpen(false);
    setIsEditing(false);
  };

  const handleRequestSubmitEdit = () => {
    const nextContent = draftContent.trim();
    if (!onRewriteUserMessage || !nextContent || nextContent === content.trim()) {
      setIsEditing(false);
      return;
    }
    setIsConfirmOpen(true);
  };

  const handleConfirmSubmitEdit = async () => {
    const nextContent = draftContent.trim();
    if (!onRewriteUserMessage || !nextContent) {
      setIsConfirmOpen(false);
      setIsEditing(false);
      return;
    }
    setIsConfirmOpen(false);
    setIsSubmitting(true);
    try {
      await onRewriteUserMessage(msgItem.id, nextContent, content.trim());
      setIsEditing(false);
    } catch {
      // 编辑失败时保持编辑状态，让用户可以重试
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-2">
      {isEditing ? (
        <div className="space-y-2">
          <Textarea
            value={draftContent}
            onChange={(event) => setDraftContent(event.target.value)}
            disabled={isSubmitting}
            className="min-h-24 resize-y bg-background text-sm"
            autoFocus
          />
          <div className="flex items-center justify-end gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              title="取消编辑"
              onClick={handleCancelEdit}
              disabled={isSubmitting}
            >
              <X className="h-3.5 w-3.5" />
              <span className="sr-only">取消编辑</span>
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="icon-sm"
              title="确认并重发"
              onClick={handleRequestSubmitEdit}
              disabled={isSubmitting || !draftContent.trim()}
            >
              <Check className="h-3.5 w-3.5" />
              <span className="sr-only">确认并重发</span>
            </Button>
          </div>
          <AlertDialog
            open={isConfirmOpen}
            onOpenChange={(open) => {
              if (!isSubmitting) {
                setIsConfirmOpen(open);
              }
            }}
          >
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>确认编辑并重发这条消息？</AlertDialogTitle>
                <AlertDialogDescription>
                  这会移除它之后的当前聊天上下文。文件、工具执行结果和外部操作不会回滚。
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={isSubmitting}>
                  取消
                </AlertDialogCancel>
                <AlertDialogAction
                  disabled={isSubmitting}
                  onClick={(event) => {
                    event.preventDefault();
                    void handleConfirmSubmitEdit();
                  }}
                >
                  确认并重发
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      ) : content ? (
        <div className="group/user-message relative">
          <div className="relative">
            <div
              className={`whitespace-pre-wrap break-words pr-7 [overflow-wrap:anywhere] ${
                isCollapsed ? `${COLLAPSED_MAX_HEIGHT} overflow-hidden` : ""
              }`}
            >
              {segments.map((segment, idx) =>
                segment.type === "mention" ? (
                  <MentionTag key={`${segment.fullPath}-${idx}`} segment={segment} />
                ) : (
                  <span key={`${idx}`}>{segment.content}</span>
                ),
              )}
            </div>
            {/* 折叠时的底部渐变遮罩 */}
            {isCollapsed && (
              <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-muted to-transparent" />
            )}
          </div>
          {/* 展开/收起按钮 */}
          {isCollapsible && (
            <button
              type="button"
              onClick={() => setIsCollapsed(!isCollapsed)}
              className="mt-1 flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              <span>{isCollapsed ? "展开全部" : "收起"}</span>
              <ChevronDown
                className={`h-3.5 w-3.5 transition-transform ${isCollapsed ? "" : "rotate-180"}`}
              />
            </button>
          )}
          {canRewrite ? (
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              data-testid="chat-message-edit-resend"
              title={isRunning ? "当前对话正在执行，稍后可编辑重发" : "编辑并重发"}
              onClick={handleStartEdit}
              disabled={isRunning}
              className="absolute right-0 top-0 h-6 w-6 border border-border/60 bg-background/85 text-muted-foreground opacity-80 shadow-sm transition hover:bg-background hover:text-foreground hover:opacity-100 focus-visible:opacity-100 disabled:opacity-40"
            >
              <Pencil className="h-3.5 w-3.5" />
              <span className="sr-only">编辑并重发</span>
            </Button>
          ) : null}
        </div>
      ) : null}
      {imageAttachments.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {imageAttachments.map((src, idx) => (
            <MarkdownImage
              key={`${src}-${idx}`}
              src={src}
              sessionId={sessionId}
              containerClassName="my-0 justify-start"
              className="max-h-56 max-w-[220px] rounded-md border border-border object-cover"
            />
          ))}
        </div>
      )}
      {otherAttachments.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {otherAttachments.map((name, idx) => (
            <div
              key={`${name}-${idx}`}
              className="flex items-center gap-1 bg-background/70 border border-border px-2 py-1 rounded text-[11px] text-muted-foreground"
            >
              <AttachmentIcon filename={name} />
              <span className="truncate max-w-[180px]">
                {name.split("/").pop() || name}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
