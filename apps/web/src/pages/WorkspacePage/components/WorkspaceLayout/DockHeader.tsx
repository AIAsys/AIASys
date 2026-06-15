import {
  ChevronDown,
  PanelRightClose,
  Settings,
  Wrench,
  Brain,
  FlaskConical,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import type { TaskWorkspaceSummary } from "../../types";
import { GitBranchPlusIcon, MessageSquareIcon } from "../chatShellIcons";
import { DockStatusChip } from "./DockComponents";
import { WorkspaceConversationPanel } from "./WorkspaceConversationPanel";
import { TokenUsageBar } from "@/components/chat/TokenUsageBar";

interface DockHeaderProps {
  currentSessionTitle: string;
  workspace?: TaskWorkspaceSummary;
  currentSessionId?: string;
  onNewConversation: () => void;
  onClose: () => void;
  onSelectConversation: (sessionId: string) => void;
  onForkConversation: (sessionId: string) => void;
  onRenameConversation: (sessionId: string, title: string) => Promise<void>;
  onDeleteConversation?: (sessionId: string) => Promise<void>;
  onCompactConversation?: () => Promise<void> | void;
  isCompactingConversation?: boolean;
  isRunning?: boolean;
  tokenUsageRefreshSignal?: number | string;
  compactionState?: {
    phase: "begin" | "done";
    tokens_before?: number;
    tokens_after?: number;
    saved_tokens?: number;
    summary_tokens?: number;
  } | null;
  onOpenToolConfig?: () => void;
  onOpenLLMConfigDialog?: () => void;
  onOpenRuntimeTab?: () => void;
}

export function DockHeader({
  currentSessionTitle,
  workspace,
  currentSessionId,
  onNewConversation,
  onClose,
  onSelectConversation,
  onForkConversation,
  onRenameConversation,
  onDeleteConversation,
  onCompactConversation,
  isCompactingConversation = false,
  isRunning = false,
  tokenUsageRefreshSignal,
  compactionState,
  onOpenToolConfig,
  onOpenLLMConfigDialog,
  onOpenRuntimeTab,
}: DockHeaderProps) {
  const conversationCount = workspace?.conversations?.length ?? 0;
  const conversationSummaryLabel =
    conversationCount > 0 ? `${conversationCount} 个对话` : "暂无对话";

  return (
    <Popover>
      <div className="shrink-0 border-b border-border/60 bg-muted/20 px-3 py-2.5">
        <div className="flex items-center justify-between gap-2">
          {/* Title trigger */}
          <PopoverTrigger asChild>
            <button
              type="button"
              className="flex min-w-0 flex-1 items-center gap-1.5 rounded-lg px-1.5 py-1 text-left transition-colors hover:bg-muted/60"
            >
              <MessageSquareIcon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <span className="truncate text-sm font-semibold text-foreground">
                {currentSessionTitle}
              </span>
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            </button>
          </PopoverTrigger>

          {/* Actions */}
          <div className="flex shrink-0 items-center gap-1">
            <TokenUsageBar
              sessionId={currentSessionId}
              refreshSignal={tokenUsageRefreshSignal}
              onCompactConversation={onCompactConversation}
              isCompactingConversation={isCompactingConversation}
              isRunning={isRunning}
              compactionState={compactionState}
              variant="dropdown"
            />
            {(onOpenToolConfig || onOpenLLMConfigDialog || onOpenRuntimeTab) ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 rounded-lg text-muted-foreground"
                    title="会话设置"
                  >
                    <Settings className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" sideOffset={6}>
                  {onOpenToolConfig ? (
                    <DropdownMenuItem onClick={onOpenToolConfig}>
                      <Wrench className="mr-2 h-4 w-4" />
                      工具配置
                    </DropdownMenuItem>
                  ) : null}
                  {onOpenLLMConfigDialog ? (
                    <DropdownMenuItem onClick={onOpenLLMConfigDialog}>
                      <Brain className="mr-2 h-4 w-4" />
                      模型配置
                    </DropdownMenuItem>
                  ) : null}
                  {onOpenRuntimeTab ? (
                    <DropdownMenuItem onClick={onOpenRuntimeTab}>
                      <FlaskConical className="mr-2 h-4 w-4" />
                      执行环境
                    </DropdownMenuItem>
                  ) : null}
                </DropdownMenuContent>
              </DropdownMenu>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-7 w-7 rounded-lg text-muted-foreground"
              onClick={onNewConversation}
              title="新建对话"
            >
              <GitBranchPlusIcon className="h-4 w-4 text-tertiary" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-7 w-7 rounded-lg text-muted-foreground"
              onClick={onClose}
              title="收起右侧栏"
            >
              <PanelRightClose className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Status chips — single line, scrollable */}
        <div className="scrollbar-hide mt-1.5 flex items-center gap-1.5 overflow-x-auto pb-0.5">
          {/* 对话数量也作为触发器，点击后展开与标题按钮相同的对话列表面板 */}
          <PopoverTrigger asChild>
            <button
              type="button"
              className="rounded-full transition-colors hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
              title="查看并切换对话"
            >
              <DockStatusChip
                className={
                  conversationSummaryLabel.includes("暂无")
                    ? ""
                    : "border-tertiary/20 bg-tertiary-container text-on-tertiary-container"
                }
              >
                {conversationSummaryLabel}
              </DockStatusChip>
            </button>
          </PopoverTrigger>
        </div>
      </div>

      <PopoverContent
        className="w-[340px] p-0"
        align="start"
        sideOffset={6}
      >
        <div className="h-[420px]">
          <WorkspaceConversationPanel
            embedded
            hideHeader
            workspace={workspace}
            currentSessionId={currentSessionId}
            onSelectConversation={onSelectConversation}
            onNewConversation={onNewConversation}
            onForkConversation={onForkConversation}
            onRenameConversation={onRenameConversation}
            onDeleteConversation={onDeleteConversation}
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}
