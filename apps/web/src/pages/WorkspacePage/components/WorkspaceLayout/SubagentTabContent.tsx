import { useState, useEffect, useCallback, useRef } from "react";
import { Loader2, Send, Square, RotateCcw, X, ChevronDown, ChevronUp } from "lucide-react";
import { apiRequest } from "@/lib/api/httpClient";
import { ChatArea } from "@/components/chat/ChatArea";
import { SubAgentDetailDrawer } from "@/components/layout/WorkspaceSidebar/SubAgentDetailDrawer";
import { statusConfig } from "@/components/layout/WorkspaceSidebar/SubAgentCallCard";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { useSubagentStream } from "@/hooks/useSubagentStream";
import type { SubAgentDetail } from "@/hooks/useExecutionTree";

interface SubagentTabContentProps {
  subagentId: string;
  userId?: string;
  sessionId?: string;
  onOpenWorkspaceFile?: (file: { name: string }) => void;
  onOpenInBrowserTab?: (url: string) => void;
}

export function SubagentTabContent({
  subagentId,
  userId,
  sessionId,
  onOpenWorkspaceFile,
  onOpenInBrowserTab,
}: SubagentTabContentProps) {
  const [detail, setDetail] = useState<SubAgentDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const {
    chatItems,
    isRunning,
    error: streamError,
    sendMessage,
    close,
    resume,
  } = useSubagentStream({ userId, sessionId, agentId: subagentId });

  const [inputValue, setInputValue] = useState("");
  const [detailExpanded, setDetailExpanded] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchDetail = useCallback(async () => {
    if (!userId || !sessionId) return;
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    try {
      const data = await apiRequest<SubAgentDetail>(
        `/api/sessions/${userId}/${sessionId}/subagents/${subagentId}`,
        { signal: controller.signal },
      );
      setDetail(data);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      console.error("加载 Sub Agent 详情失败:", err);
    } finally {
      setIsLoading(false);
    }
  }, [subagentId, userId, sessionId]);

  useEffect(() => {
    fetchDetail();
    return () => {
      if (abortRef.current) {
        abortRef.current.abort();
      }
    };
  }, [fetchDetail]);

  const handleSubmit = useCallback(async () => {
    const message = inputValue.trim();
    if (!message || isRunning) return;
    setInputValue("");
    await sendMessage(message);
  }, [inputValue, isRunning, sendMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
        e.preventDefault();
        void handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handleClose = useCallback(async () => {
    await close();
    await fetchDetail();
  }, [close, fetchDetail]);

  const handleResume = useCallback(async () => {
    await resume();
    await fetchDetail();
  }, [resume, fetchDetail]);

  if (!userId || !sessionId) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 text-sm text-muted-foreground">
        缺少会话信息
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center gap-2 px-6 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        正在加载协作节点详情...
      </div>
    );
  }

  const canInteract = detail && detail.status !== "closed" && detail.status !== "cancelled";
  const canResume = detail && (detail.status === "completed" || detail.status === "closed" || detail.status === "cancelled");
  const statusLabel = detail?.status ? statusConfig[detail.status]?.label ?? detail.status : null;

  return (
    <div className="flex flex-1 flex-col min-h-0 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="truncate font-medium">{detail?.name || subagentId}</span>
          {statusLabel && (
            <Badge variant="outline" className="shrink-0">
              {statusLabel}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {canResume && (
            <Button variant="ghost" size="sm" onClick={handleResume}>
              <RotateCcw className="h-4 w-4 mr-1" />
              恢复对话
            </Button>
          )}
          {canInteract && (
            <Button variant="ghost" size="sm" onClick={handleClose}>
              <X className="h-4 w-4 mr-1" />
              关闭
            </Button>
          )}
        </div>
      </div>

      {/* Main content */}
      <div className="flex flex-1 flex-col min-h-0 overflow-hidden">
        {/* Execution history toggle */}
        <button
          type="button"
          onClick={() => setDetailExpanded((v) => !v)}
          className="flex items-center justify-between w-full px-4 py-1.5 text-xs text-muted-foreground hover:bg-muted/50 border-b transition-colors"
        >
          <span>{detailExpanded ? "隐藏执行详情" : "查看执行详情"}</span>
          {detailExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>

        {/* Execution history (collapsible, fixed max height) */}
        {detailExpanded && (
          <div className="border-b max-h-[40%] overflow-auto">
            <SubAgentDetailDrawer
              subagent={detail}
              inline
              isLoading={false}
              userId={userId}
              sessionId={sessionId}
              onOpenWorkspaceFile={onOpenWorkspaceFile}
              onOpenInBrowserTab={onOpenInBrowserTab}
            />
          </div>
        )}

        {/* Continue dialog */}
        <div className="flex flex-1 flex-col min-h-0">
          <div className="flex-1 overflow-auto px-4 py-2">
            <ChatArea items={chatItems} sessionId={sessionId} isRunning={isRunning} />
          </div>

          {streamError && (
            <div className="px-4 py-2 text-sm text-destructive bg-destructive/10">
              {streamError}
            </div>
          )}

          <div className="border-t p-3">
            <div className="flex items-end gap-2">
              <Textarea
                ref={textareaRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  canInteract
                    ? "输入消息继续对话..."
                    : "该协作节点已结束，无法继续对话"
                }
                disabled={!canInteract || isRunning}
                rows={2}
                className="min-h-[60px] resize-none"
              />
              <Button
                type="button"
                size="icon"
                onClick={handleSubmit}
                disabled={!canInteract || isRunning || !inputValue.trim()}
                className="shrink-0"
              >
                {isRunning ? (
                  <Square className="h-4 w-4" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
