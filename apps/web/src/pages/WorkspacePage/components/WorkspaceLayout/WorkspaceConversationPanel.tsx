import {
  Download,
  GitBranchPlus,
  MessageSquare,
  MessageSquarePlus,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  PenSquare,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import * as React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { exportConversation } from "@/lib/api/sessions";
import { useAuthContext } from "@/contexts/AuthContext";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { TaskWorkspaceSummary, WorkspaceConversationSummary } from "../../types";

function toMillis(value?: string | null): number {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function formatConversationTimestamp(value?: string | null): string {
  if (!value) {
    return "未知";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "未知";
  }
  return parsed.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

interface WorkspaceConversationPanelProps {
  workspace?: TaskWorkspaceSummary;
  currentSessionId?: string;
  embedded?: boolean;
  placement?: "left" | "right";
  hideHeader?: boolean;
  hideCreateButton?: boolean;
  onSelectConversation: (sessionId: string) => void;
  onNewConversation: () => void;
  onForkConversation: (sessionId: string) => void;
  onRenameConversation: (sessionId: string, title: string) => Promise<void>;
  onDeleteConversation?: (sessionId: string) => Promise<void>;
}

interface ConversationItemProps {
  conversation: WorkspaceConversationSummary;
  currentSessionId?: string;
  pendingSwitchSessionId?: string | null;
  switchSucceededSessionId?: string | null;
  onSelectConversation: (sessionId: string) => void;
  onForkConversation: (sessionId: string) => void;
  onDeleteConversation?: (sessionId: string) => Promise<void>;
  onExportConversation: (
    event: React.MouseEvent,
    sessionId: string,
    title: string,
  ) => void;
  onStartRename: (sessionId: string, title: string) => void;
  currentUserId?: string;
  style?: React.CSSProperties;
  measureRef?: (element: HTMLElement | null) => void;
}

const ConversationItem = React.memo(function ConversationItem({
  conversation,
  currentSessionId,
  pendingSwitchSessionId,
  switchSucceededSessionId,
  onSelectConversation,
  onForkConversation,
  onDeleteConversation,
  onExportConversation,
  onStartRename,
  currentUserId,
  style,
  measureRef,
}: ConversationItemProps) {
  const isCurrentConversation = conversation.session_id === currentSessionId;
  const isSwitchPending = conversation.session_id === pendingSwitchSessionId;
  const isSwitchSucceeded = conversation.session_id === switchSucceededSessionId;

  const handleSelect = () => {
    onSelectConversation(conversation.session_id);
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handleSelect();
    }
  };

  const handleRenameClick = (event: React.MouseEvent) => {
    event.stopPropagation();
    onStartRename(conversation.session_id, conversation.title || "未命名对话");
  };

  const handleForkClick = (event: React.MouseEvent) => {
    event.stopPropagation();
    onForkConversation(conversation.session_id);
  };

  const handleExportClick = (event: React.MouseEvent) => {
    onExportConversation(
      event,
      conversation.session_id,
      conversation.title || "conversation",
    );
  };

  const handleDeleteClick = (event: React.MouseEvent) => {
    event.stopPropagation();
    void onDeleteConversation?.(conversation.session_id);
  };

  return (
    <div
      ref={measureRef}
      role="button"
      tabIndex={0}
      onClick={handleSelect}
      onKeyDown={handleKeyDown}
      style={style}
      className={cn(
        "group w-full rounded-xl border px-3 py-3 text-left transition-colors",
        isSwitchSucceeded
          ? "border-success/20 bg-success-container shadow-sm"
          : isCurrentConversation
            ? "border-border bg-muted/70 shadow-sm"
            : "border-transparent bg-background/70 hover:border-border hover:bg-background",
      )}
    >
      <div className="flex items-start gap-2">
        <div
          className={cn(
            "mt-0.5 rounded-md p-1.5",
            isSwitchSucceeded
              ? "bg-success-container text-success"
              : isCurrentConversation
                ? "bg-muted-foreground/10 text-muted-foreground"
                : "bg-muted text-muted-foreground",
          )}
        >
          <MessageSquare className="h-3.5 w-3.5" />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <div
              className="truncate text-sm font-medium text-foreground"
              title={conversation.title || "未命名对话"}
            >
              {conversation.title || "未命名对话"}
            </div>
            {isSwitchPending ? (
              <span className="rounded-full bg-info-container px-2 py-0.5 text-[10px] font-medium text-info">
                切换中...
              </span>
            ) : null}
            {isSwitchSucceeded ? (
              <span className="rounded-full bg-success-container px-2 py-0.5 text-[10px] font-medium text-success">
                切换成功
              </span>
            ) : null}
            {conversation.branched_from_conversation_id ? (
              <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                Fork
              </span>
            ) : null}
          </div>

          <div className="mt-1 text-[11px] text-muted-foreground">
            创建{" "}
            {formatConversationTimestamp(conversation.created_at)}
            {" · "}
            最近使用{" "}
            {formatConversationTimestamp(conversation.updated_at)}
          </div>

          <div className="mt-1 text-[11px] text-muted-foreground">
            {conversation.message_count} 条消息
            {" · "}
            {conversation.execution_record_count ?? 0} 次执行
          </div>
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
              onClick={(event) => event.stopPropagation()}
            >
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={handleRenameClick}>
              <PenSquare className="mr-2 h-4 w-4" />
              重命名对话
            </DropdownMenuItem>
            <DropdownMenuItem onClick={handleForkClick}>
              <GitBranchPlus className="mr-2 h-4 w-4" />
              Fork 为新对话
            </DropdownMenuItem>
            {currentUserId ? (
              <DropdownMenuItem onClick={handleExportClick}>
                <Download className="mr-2 h-4 w-4" />
                导出对话
              </DropdownMenuItem>
            ) : null}
            {onDeleteConversation ? (
              <DropdownMenuItem
                onClick={handleDeleteClick}
                className="text-error focus:text-error"
              >
                <Trash2 className="mr-2 h-4 w-4" />
                删除对话
              </DropdownMenuItem>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
});

export function WorkspaceConversationPanel({
  workspace,
  currentSessionId,
  embedded = false,
  placement = "left",
  hideHeader = false,
  hideCreateButton = false,
  onSelectConversation,
  onNewConversation,
  onForkConversation,
  onRenameConversation,
  onDeleteConversation,
}: WorkspaceConversationPanelProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [pendingSwitchSessionId, setPendingSwitchSessionId] = useState<
    string | null
  >(null);
  const [switchSucceededSessionId, setSwitchSucceededSessionId] = useState<
    string | null
  >(null);
  const [showRenameDialog, setShowRenameDialog] = useState(false);
  const [renameTarget, setRenameTarget] = useState<{
    sessionId: string;
    title: string;
  } | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const { user } = useAuthContext();
  const currentUserId = user?.id;
  const isCollapsed = embedded ? false : collapsed;
  const edgeBorderClass =
    placement === "right"
      ? "border-l border-border"
      : "border-r border-border";

  useEffect(() => {
    if (
      !pendingSwitchSessionId ||
      currentSessionId !== pendingSwitchSessionId
    ) {
      return;
    }

    setPendingSwitchSessionId(null);
    setSwitchSucceededSessionId(currentSessionId);
  }, [currentSessionId, pendingSwitchSessionId]);

  useEffect(() => {
    if (!switchSucceededSessionId) {
      return;
    }

    const timer = window.setTimeout(() => {
      setSwitchSucceededSessionId((previous) =>
        previous === switchSucceededSessionId ? null : previous,
      );
    }, 1800);

    return () => {
      window.clearTimeout(timer);
    };
  }, [switchSucceededSessionId]);

  useEffect(() => {
    if (!pendingSwitchSessionId) {
      return;
    }

    const timer = window.setTimeout(() => {
      setPendingSwitchSessionId((previous) =>
        previous === pendingSwitchSessionId ? null : previous,
      );
    }, 8000);

    return () => {
      window.clearTimeout(timer);
    };
  }, [pendingSwitchSessionId]);

  const handleSelectConversation = (sessionId: string) => {
    if (sessionId === currentSessionId) {
      return;
    }

    setSwitchSucceededSessionId(null);
    setPendingSwitchSessionId(sessionId);
    onSelectConversation(sessionId);
  };

  const handleExportConversation = async (
    event: React.MouseEvent,
    sessionId: string,
    title: string,
  ) => {
    event.stopPropagation();
    if (!currentUserId) return;
    try {
      const blob = await exportConversation(currentUserId, sessionId);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      const safeTitle = (title || "conversation")
        .replace(/[^\w\-\u4e00-\u9fa5]/g, "_")
        .slice(0, 50);
      link.download = `${safeTitle}_${sessionId}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch {
      // 静默失败，不打扰用户
    }
  };

  const conversations = useMemo(
    () => workspace?.conversations ?? [],
    [workspace?.conversations],
  );
  const sortedConversations = useMemo(
    () =>
      [...conversations].sort((left, right) => {
        const updatedDiff =
          toMillis(right.updated_at) - toMillis(left.updated_at);
        if (updatedDiff !== 0) {
          return updatedDiff;
        }
        return toMillis(right.created_at) - toMillis(left.created_at);
      }),
    [conversations],
  );
  const isSyncingConversations = Boolean(
    workspace &&
      workspace.conversation_count > 0 &&
      conversations.length < workspace.conversation_count,
  );

  const listRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: sortedConversations.length,
    getScrollElement: () => listRef.current,
    estimateSize: () => 88,
    measureElement:
      typeof window !== "undefined" &&
      "ResizeObserver" in window
        ? (element) => element.getBoundingClientRect().height
        : undefined,
    overscan: 8,
  });

  const handleStartRename = useCallback(
    (sessionId: string, title: string) => {
      setRenameTarget({ sessionId, title });
      setRenameValue(title);
      setShowRenameDialog(true);
    },
    [],
  );

  if (!workspace) {
    return (
      <div
        className={cn(
          "bg-card/30 flex flex-col",
          embedded ? "h-full min-w-0 w-full" : "w-[272px] min-w-[272px]",
          edgeBorderClass,
        )}
      >
        <div className="px-4 py-4 border-b border-border">
          <div className="text-sm font-medium text-foreground">当前工作区</div>
          <div className="text-xs text-muted-foreground mt-1">
            正在加载工作区，或请先在左侧新建工作区开始。
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "bg-card/30 flex min-h-0 flex-col transition-[width,min-width] duration-200",
        embedded
          ? "h-full min-w-0 w-full"
          : isCollapsed
            ? "w-[64px] min-w-[64px]"
            : "w-[272px] min-w-[272px]",
        embedded ? "" : edgeBorderClass,
      )}
    >
      {!hideHeader ? (
        <div
          className={cn(
            "border-b border-border",
            isCollapsed ? "px-2 py-3" : "px-4 py-4",
          )}
        >
          <div
            className={cn(
              "flex",
              isCollapsed ? "justify-center" : "justify-between",
            )}
          >
            {!isCollapsed ? (
              <div className="text-xs font-medium text-muted-foreground">
                {embedded ? "当前工作区对话" : "对话列表"}
              </div>
            ) : null}
            {!embedded ? (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0 text-muted-foreground"
                onClick={() => setCollapsed((prev) => !prev)}
                title={isCollapsed ? "展开对话列表" : "收起对话列表"}
              >
                {isCollapsed ? (
                  <PanelLeftOpen className="h-4 w-4" />
                ) : (
                  <PanelLeftClose className="h-4 w-4" />
                )}
              </Button>
            ) : null}
          </div>

          {!isCollapsed ? (
            <div className="mt-2 min-w-0">
              <div className="text-sm font-semibold text-foreground truncate">
                {workspace.title || "未命名工作区"}
              </div>
              {workspace.description?.trim() ? (
                <div className="mt-1 text-xs leading-5 text-muted-foreground">
                  {workspace.description.trim()}
                </div>
              ) : null}
            </div>
          ) : null}

          {!hideCreateButton ? (
            <div className={cn("mt-3", isCollapsed ? "" : "grid gap-2")}>
              <button
                type="button"
                onClick={onNewConversation}
                title="新建对话"
                className={cn(
                  "rounded-lg border border-border bg-background font-medium text-foreground transition-colors hover:bg-accent",
                  isCollapsed
                    ? "mx-auto flex h-10 w-10 items-center justify-center"
                    : "flex w-full items-center justify-center gap-2 px-3 py-2 text-sm",
                )}
              >
                <MessageSquarePlus className="w-4 h-4" />
                {!isCollapsed ? <span>新建对话</span> : null}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      {isCollapsed ? (
        <div className="flex-1" />
      ) : (
        <div
          ref={listRef}
          className={cn(
            "min-h-0 flex-1 overflow-y-auto",
            hideHeader ? "px-2 py-2" : "px-3 py-3",
          )}
        >
          {conversations.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border/80 bg-background/70 px-3 py-3 text-xs text-muted-foreground">
              {isSyncingConversations
                ? "正在同步当前工作区的对话列表..."
                : "当前工作区还没有对话。你可以直接新建对话开始，或从左侧切到别的工作区。"}
            </div>
          ) : (
            <div
              style={{
                height: `${rowVirtualizer.getTotalSize()}px`,
                width: "100%",
                position: "relative",
              }}
            >
              {rowVirtualizer.getVirtualItems().map((virtualItem) => {
                const conversation = sortedConversations[virtualItem.index];
                return (
                  <ConversationItem
                    key={conversation.conversation_id}
                    conversation={conversation}
                    currentSessionId={currentSessionId}
                    pendingSwitchSessionId={pendingSwitchSessionId}
                    switchSucceededSessionId={switchSucceededSessionId}
                    onSelectConversation={handleSelectConversation}
                    onForkConversation={onForkConversation}
                    onDeleteConversation={onDeleteConversation}
                    onExportConversation={handleExportConversation}
                    onStartRename={handleStartRename}
                    currentUserId={currentUserId}
                    measureRef={rowVirtualizer.measureElement}
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      width: "100%",
                      transform: `translateY(${virtualItem.start}px)`,
                      paddingBottom: "4px",
                    }}
                  />
                );
              })}
            </div>
          )}
        </div>
      )}
    <Dialog open={showRenameDialog} onOpenChange={setShowRenameDialog}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>重命名对话</DialogTitle>
          <DialogDescription>请输入新的对话名称</DialogDescription>
        </DialogHeader>
        <div className="py-2">
          <Input
            value={renameValue}
            onChange={(event) => setRenameValue(event.target.value)}
            placeholder="未命名对话"
          />
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => setShowRenameDialog(false)}
          >
            取消
          </Button>
          <Button
            onClick={() => {
              if (!renameTarget || !renameValue.trim()) {
                setShowRenameDialog(false);
                setRenameTarget(null);
                return;
              }
              void onRenameConversation(
                renameTarget.sessionId,
                renameValue.trim(),
              );
              setShowRenameDialog(false);
              setRenameTarget(null);
            }}
          >
            确认
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </div>
  );
}
