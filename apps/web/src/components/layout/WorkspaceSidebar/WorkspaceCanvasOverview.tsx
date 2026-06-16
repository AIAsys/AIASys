/**
 * WorkspaceCanvasOverview — 当前工作区画布概览。
 *
 * 从 WorkspaceContextPanel.tsx 提取的纯展示组件，显示会话信息、指标卡片、快捷操作和最近文件。
 */

import { CheckCircle2, Circle, FileText, FolderOpen, ListTodo, Map, Plus, ScrollText, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  CenterCanvasHero,
  ResourceMetricCard,
  SummaryChip,
} from "./WorkspaceSummaryCards";

interface WorkspaceCanvasOverviewProps {
  workspaceTitle: string;
  sessionTitle: string;
  runtimeLabel: string;
  messageCount: number;
  executionRecordCount: number;
  fileCount: number;
  recentFiles: Array<{ name: string }>;
  planState?: {
    mode?: "active" | "inactive";
    approval_status?: "draft" | "pending_approval" | "approved" | "rejected";
    current_plan_file?: string | null;
  } | null;
  tasks?: Array<{
    id: string;
    content: string;
    status: "pending" | "in_progress" | "completed" | "cancelled";
    dependencies?: string[];
  }>;
  onNewBranch?: () => void;
  onOpenSettings?: () => void;
  onViewRecords?: () => Promise<void> | void;
  onOpenFiles: () => void;
}

export function WorkspaceCanvasOverview({
  workspaceTitle,
  sessionTitle,
  runtimeLabel,
  messageCount,
  executionRecordCount,
  fileCount,
  recentFiles,
  planState,
  tasks = [],
  onNewBranch,
  onOpenSettings,
  onViewRecords,
  onOpenFiles,
}: WorkspaceCanvasOverviewProps) {
  const activeTasks = tasks.filter((task) =>
    task.status === "pending" || task.status === "in_progress",
  );
  const completedCount = tasks.filter((task) => task.status === "completed").length;
  const isPlanModeActive = planState?.mode === "active";
  const isPlanPendingApproval = planState?.approval_status === "pending_approval";

  return (
    <div className="h-full min-h-0 overflow-y-auto overscroll-contain px-6 pb-8 pt-4">
      <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-5">
        <CenterCanvasHero
          eyebrow="工作区画布"
          title={workspaceTitle || "当前工作区"}
          description="当前工作区承接长期任务上下文，当前会话记录本轮对话、执行与文件产出。"
          badge={
            <SummaryChip className="border-tertiary/20 bg-tertiary-container text-on-tertiary-container">
              {sessionTitle}
            </SummaryChip>
          }
        />

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <ResourceMetricCard
            label="会话"
            value={0}
            hint="当前工作区内的会话数量。"
          />
          <ResourceMetricCard
            label="消息"
            value={messageCount}
            hint="当前会话已有消息数量。"
            onClick={onOpenSettings}
          />
          <ResourceMetricCard
            label="执行记录"
            value={executionRecordCount}
            hint="当前会话已有执行记录。"
            onClick={onViewRecords}
          />
          <ResourceMetricCard
            label="当前工作区"
            value={fileCount}
            hint="当前会话工作区文件数量。"
            onClick={onOpenFiles}
          />
        </div>

        <section className="rounded-2xl border border-border bg-card px-5 py-5 shadow-sm">
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="text-sm font-semibold text-foreground">
                  当前会话
                </div>
                <div className="mt-2 text-lg font-semibold text-foreground">
                  {sessionTitle}
                </div>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                  运行态状态：{runtimeLabel}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 gap-1.5 rounded-xl px-3 text-[12px]"
                  onClick={() => onNewBranch?.()}
                >
                  <Plus className="h-3.5 w-3.5" />
                  新建会话
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 gap-1.5 rounded-xl px-3 text-[12px]"
                  data-testid="workspace-context-open-settings"
                  onClick={() => onOpenSettings?.()}
                >
                  <Settings2 className="h-3.5 w-3.5" />
                  打开设置
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 gap-1.5 rounded-xl px-3 text-[12px]"
                  onClick={onOpenFiles}
                >
                  <FolderOpen className="h-3.5 w-3.5" />
                  打开文件
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 gap-1.5 rounded-xl px-3 text-[12px]"
                  onClick={() => onViewRecords?.()}
                >
                  <ScrollText className="h-3.5 w-3.5" />
                  查看记录
                </Button>
              </div>
            </div>

            {recentFiles.length > 0 && (
              <div className="border-t border-border pt-4">
                <div className="text-xs font-medium text-muted-foreground">
                  最近文件
                </div>
                <div className="mt-2 flex flex-col gap-1.5">
                  {recentFiles.map((file) => (
                    <button
                      key={file.name}
                      type="button"
                      className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm text-foreground transition-colors hover:bg-muted"
                      onClick={onOpenFiles}
                    >
                      <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      <span className="truncate">{file.name}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>

        {(tasks.length > 0 || isPlanModeActive || isPlanPendingApproval) && (
          <section className="rounded-2xl border border-border bg-card px-5 py-5 shadow-sm">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <ListTodo className="h-4 w-4 text-muted-foreground" />
                  当前任务
                </div>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  {tasks.length > 0
                    ? `已完成 ${completedCount}/${tasks.length} 项。`
                    : "当前会话还没有结构化任务。"}
                </p>
              </div>
              {(isPlanModeActive || isPlanPendingApproval) && (
                <SummaryChip
                  className={
                    isPlanPendingApproval
                      ? "border-warning/25 bg-warning-container text-on-warning-container"
                      : "border-primary/25 bg-primary-container text-on-primary-container"
                  }
                >
                  <Map className="mr-1 h-3 w-3" />
                  {isPlanPendingApproval ? "计划待批" : "规划模式"}
                </SummaryChip>
              )}
            </div>

            {planState?.current_plan_file && (
              <div className="mt-3 rounded-lg border border-border bg-muted/35 px-3 py-2 text-xs text-muted-foreground">
                {planState.current_plan_file}
              </div>
            )}

            {activeTasks.length > 0 && (
              <div className="mt-4 flex flex-col gap-2">
                {activeTasks.slice(0, 6).map((task) => (
                  <div
                    key={task.id}
                    className="flex items-start gap-2 rounded-lg border border-border/70 bg-background px-3 py-2 text-sm"
                  >
                    {task.status === "in_progress" ? (
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                    ) : (
                      <Circle className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium text-foreground">
                        {task.content}
                      </div>
                      {task.dependencies && task.dependencies.length > 0 ? (
                        <div className="mt-1 truncate text-xs text-muted-foreground">
                          依赖：{task.dependencies.join(", ")}
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
