import { useCallback } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Circle,
  CircleDot,
  ListTodo,
  Map,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useLocalStorageState } from "@/hooks/useLocalStorageState";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SessionTaskItem {
  id: string;
  content: string;
  status: "pending" | "in_progress" | "completed" | "cancelled";
  dependencies?: string[];
}

export interface SessionPlanState {
  mode?: "active" | "inactive";
  approval_status?: "draft" | "pending_approval" | "approved" | "rejected";
  current_plan_file?: string | null;
  pre_plan_permission_mode?: string | null;
}

export interface SessionTaskPanelProps {
  tasks?: SessionTaskItem[];
  planState?: SessionPlanState | null;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_VISIBLE = 5;

const STORAGE_KEY = "aiasys:ui:taskPanelExpanded";

// ---------------------------------------------------------------------------
// Visible-task selector (ported from kimi-code todo-panel.ts)
//
// Strategy:
// 1. Include every in_progress item (capped at MAX_VISIBLE).
// 2. Fill remaining slots with "what's next" — earliest pending — while
//    reserving one slot for "what just finished" — latest done.
// ---------------------------------------------------------------------------

function selectVisibleTasks(
  tasks: readonly SessionTaskItem[],
): { visible: SessionTaskItem[]; hidden: number } {
  if (tasks.length <= MAX_VISIBLE) {
    return { visible: [...tasks], hidden: 0 };
  }

  const inProgress: number[] = [];
  const pending: number[] = [];
  const done: number[] = [];

  for (const [i, task] of tasks.entries()) {
    if (task.status === "in_progress") inProgress.push(i);
    else if (task.status === "pending") pending.push(i);
    else done.push(i);
  }

  const picked = new Set<number>();
  for (const i of inProgress.slice(0, MAX_VISIBLE)) picked.add(i);

  if (picked.size < MAX_VISIBLE) {
    const doneCandidates = [...done].reverse();
    const pendingCandidates = pending;
    const remaining = MAX_VISIBLE - picked.size;

    let doneCount: number;
    let pendingCount: number;

    if (doneCandidates.length === 0) {
      doneCount = 0;
      pendingCount = Math.min(remaining, pendingCandidates.length);
    } else if (pendingCandidates.length === 0) {
      pendingCount = 0;
      doneCount = Math.min(remaining, doneCandidates.length);
    } else {
      doneCount = 1;
      pendingCount = Math.min(remaining - 1, pendingCandidates.length);
      if (pendingCount < remaining - 1) {
        doneCount = Math.min(doneCandidates.length, remaining - pendingCount);
      }
    }

    for (let i = 0; i < doneCount; i++) picked.add(doneCandidates[i] as number);
    for (let i = 0; i < pendingCount; i++)
      picked.add(pendingCandidates[i] as number);
  }

  const sortedIdx = [...picked].sort((a, b) => a - b);
  return {
    visible: sortedIdx.map((i) => tasks[i] as SessionTaskItem),
    hidden: tasks.length - sortedIdx.length,
  };
}

// ---------------------------------------------------------------------------
// Row render helpers
// ---------------------------------------------------------------------------

function TaskStatusIcon({ status }: { status: SessionTaskItem["status"] }) {
  switch (status) {
    case "in_progress":
      return <CircleDot className="h-3.5 w-3.5 shrink-0 text-primary" />;
    case "completed":
      return <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-success" />;
    case "cancelled":
      return <XCircle className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" />;
    case "pending":
    default:
      return <Circle className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" />;
  }
}

function TaskRow({ task }: { task: SessionTaskItem }) {
  const isDone = task.status === "completed" || task.status === "cancelled";
  const isActive = task.status === "in_progress";

  return (
    <div className="flex items-start gap-2">
      <div className="mt-0.5 shrink-0">
        <TaskStatusIcon status={task.status} />
      </div>
      <span
        className={cn(
          "min-w-0 flex-1 truncate text-[11px] leading-4",
          isActive && "font-medium text-foreground",
          isDone && "text-muted-foreground line-through",
          !isActive && !isDone && "text-foreground",
        )}
        title={task.content}
      >
        {task.content}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SessionTaskPanel({ tasks = [], planState }: SessionTaskPanelProps) {
  const [isExpanded, setIsExpanded] = useLocalStorageState(STORAGE_KEY, true);

  const isPlanModeActive = planState?.mode === "active";
  const isPlanPendingApproval = planState?.approval_status === "pending_approval";
  const hasPlanFile = Boolean(planState?.current_plan_file);

  // Nothing to show
  const hasContent =
    tasks.length > 0 || isPlanModeActive || isPlanPendingApproval || hasPlanFile;
  if (!hasContent) return null;

  const completedCount = tasks.filter((t) => t.status === "completed").length;
  const inProgressTask = tasks.find((t) => t.status === "in_progress");
  const activeCount = tasks.filter(
    (t) => t.status === "pending" || t.status === "in_progress",
  ).length;

  const { visible, hidden } = selectVisibleTasks(tasks);

  const toggleExpanded = useCallback(() => {
    setIsExpanded((v) => !v);
  }, [setIsExpanded]);

  // Collapsed mode — single-line summary
  if (!isExpanded) {
    let summaryText: string;
    if (isPlanModeActive) {
      summaryText = `规划模式: ${planState?.current_plan_file || "未命名计划"}`;
    } else if (inProgressTask) {
      summaryText = inProgressTask.content;
    } else if (activeCount > 0) {
      summaryText = `待处理 ${activeCount} 项`;
    } else {
      summaryText = `已完成 ${completedCount}/${tasks.length}`;
    }

    return (
      <div className="shrink-0 border-b border-border/50 bg-background px-3 py-1.5">
        <button
          type="button"
          onClick={toggleExpanded}
          className="flex w-full items-center gap-2 text-left"
        >
          {isPlanModeActive ? (
            <Map className="h-3.5 w-3.5 shrink-0 text-primary" />
          ) : (
            <ListTodo className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          )}
          <span className="min-w-0 flex-1 truncate text-[11px] text-muted-foreground">
            {isPlanModeActive ? summaryText : `当前任务: ${summaryText}`}
          </span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        </button>
      </div>
    );
  }

  // Expanded mode
  return (
    <div className="shrink-0 border-b border-border/50 bg-background px-3 py-2">
      {/* Header row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          {isPlanModeActive ? (
            <Map className="h-3.5 w-3.5 shrink-0 text-primary" />
          ) : (
            <ListTodo className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          )}
          <span className="shrink-0 text-[11px] font-medium text-foreground">
            {isPlanModeActive ? "规划模式" : "当前任务"}
          </span>
          {!isPlanModeActive && tasks.length > 0 && (
            <span className="text-[11px] tabular-nums text-muted-foreground">
              ({completedCount}/{tasks.length})
            </span>
          )}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0 text-muted-foreground hover:text-foreground"
          onClick={toggleExpanded}
        >
          <ChevronUp className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Plan mode content */}
      {isPlanModeActive && (
        <div className="mt-2 space-y-1.5">
          {planState?.current_plan_file && (
            <div className="text-[11px] text-muted-foreground">
              计划文件:{" "}
              <span className="font-medium text-foreground">
                {planState.current_plan_file}
              </span>
            </div>
          )}
          <div className="flex items-center gap-1.5">
            <span
              className={cn(
                "inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium",
                isPlanPendingApproval
                  ? "border border-warning/20 bg-warning-container text-on-warning-container"
                  : "border border-primary/20 bg-primary-container text-on-primary-container",
              )}
            >
              {isPlanPendingApproval ? "待审批" : "规划中"}
            </span>
          </div>
        </div>
      )}

      {/* Task list */}
      {!isPlanModeActive && visible.length > 0 && (
        <div className="mt-2 space-y-1">
          {visible.map((task) => (
            <TaskRow key={task.id} task={task} />
          ))}
          {hidden > 0 && (
            <div className="pl-[22px] text-[11px] text-muted-foreground">
              +{hidden} 更多
            </div>
          )}
        </div>
      )}

      {/* Approved plan but no tasks yet */}
      {!isPlanModeActive &&
        tasks.length === 0 &&
        planState?.approval_status === "approved" &&
        hasPlanFile && (
          <div className="mt-2 text-[11px] text-muted-foreground">
            计划已批准:{" "}
            <span className="text-foreground">{planState.current_plan_file}</span>
          </div>
        )}
    </div>
  );
}

export default SessionTaskPanel;
