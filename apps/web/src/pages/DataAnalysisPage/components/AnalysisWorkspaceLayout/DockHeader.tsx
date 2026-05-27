import { CheckCircle2, ChevronDown, ListTodo, Map, PanelRightClose } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import type { SessionStatusInfo, TaskWorkspaceSummary } from "../../types";
import { GitBranchPlusIcon, MessageSquareIcon } from "../chatShellIcons";
import { DockStatusChip } from "./DockComponents";
import { WorkspaceConversationPanel } from "./WorkspaceConversationPanel";

interface DockHeaderProps {
  currentSessionTitle: string;
  workspace?: TaskWorkspaceSummary;
  currentSessionId?: string;
  sessionStatus?: SessionStatusInfo | null;
  onNewConversation: () => void;
  onClose: () => void;
  onSelectConversation: (sessionId: string) => void;
  onForkConversation: (sessionId: string) => void;
  onRenameConversation: (sessionId: string, title: string) => Promise<void>;
  onDeleteConversation?: (sessionId: string) => Promise<void>;
}

export function DockHeader({
  currentSessionTitle,
  workspace,
  currentSessionId,
  sessionStatus,
  onNewConversation,
  onClose,
  onSelectConversation,
  onForkConversation,
  onRenameConversation,
  onDeleteConversation,
}: DockHeaderProps) {
  const tasks = sessionStatus?.tasks ?? [];
  const activeTasks = tasks.filter((task) =>
    task.status === "pending" || task.status === "in_progress",
  );
  const inProgressTask = tasks.find((task) => task.status === "in_progress");
  const completedTaskCount =
    sessionStatus?.task_counts?.completed ??
    tasks.filter((task) => task.status === "completed").length;
  const planState = sessionStatus?.plan_state ?? null;
  const isPlanModeActive = planState?.mode === "active";
  const isPlanPendingApproval = planState?.approval_status === "pending_approval";

  const conversationCount = workspace?.conversations?.length ?? 0;
  const conversationSummaryLabel =
    conversationCount > 0 ? `${conversationCount} 个对话` : "暂无对话";

  return (
    <div className="shrink-0 border-b border-border/60 bg-muted/20 px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        {/* Title Popover */}
        <Popover>
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

        {/* Actions */}
        <div className="flex shrink-0 items-center gap-1">
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
        <DockStatusChip
          className={
            conversationSummaryLabel.includes("暂无")
              ? ""
              : "border-tertiary/20 bg-tertiary-container text-on-tertiary-container"
          }
        >
          {conversationSummaryLabel}
        </DockStatusChip>
        {isPlanModeActive ? (
          <DockStatusChip className="border-primary/25 bg-primary-container text-on-primary-container">
            <Map className="mr-1 h-3 w-3" />
            规划模式
          </DockStatusChip>
        ) : isPlanPendingApproval ? (
          <DockStatusChip className="border-warning/25 bg-warning-container text-on-warning-container">
            <Map className="mr-1 h-3 w-3" />
            计划待批
          </DockStatusChip>
        ) : null}
        {tasks.length > 0 ? (
          <DockStatusChip>
            <ListTodo className="mr-1 h-3 w-3" />
            {completedTaskCount}/{tasks.length} 任务
          </DockStatusChip>
        ) : null}
        {inProgressTask ? (
          <DockStatusChip className="max-w-[180px]">
            <ListTodo className="mr-1 h-3 w-3 shrink-0" />
            <span className="truncate">{inProgressTask.content}</span>
          </DockStatusChip>
        ) : activeTasks.length > 0 ? (
          <DockStatusChip>
            <ListTodo className="mr-1 h-3 w-3" />
            待处理 {activeTasks.length} 项
          </DockStatusChip>
        ) : null}
        {planState?.current_plan_file ? (
          <DockStatusChip className="max-w-[180px]">
            <CheckCircle2 className="mr-1 h-3 w-3 shrink-0" />
            <span className="truncate">{planState.current_plan_file}</span>
          </DockStatusChip>
        ) : null}
      </div>
    </div>
  );
}
