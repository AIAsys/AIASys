import {
  Pause,
  PencilLine,
  Play,
  Plus,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { LLMModelConfig } from "@/lib/api/llm";
import type {
  TriggerEventDocument,
  WorkspaceAutoTask,
} from "@/types/autoTask";

import {
  FIRST_RUN_POLICY_LABEL,
  OVERLAP_POLICY_LABEL,
  STATUS_BADGE_CLASS,
  STATUS_LABEL,
  TASK_CATEGORY_LABEL,
  formatScheduleValue,
  formatStopConditionsSummary,
  formatTimestamp,
  getAutoTaskTitle,
  shouldShowTaskFirstRunPolicy,
  summarizeText,
} from "./scheduleFormat";

interface AutoTaskListProps {
  tasks: WorkspaceAutoTask[];
  latestTaskEvents: ReadonlyMap<string, TriggerEventDocument>;
  pendingActionTaskId: string | null;
  availableModels?: LLMModelConfig[];
  onRunNow: (task: WorkspaceAutoTask) => void;
  onToggleTask: (task: WorkspaceAutoTask) => void;
  onEditTask: (task: WorkspaceAutoTask) => void;
  onDeleteTask: (task: WorkspaceAutoTask) => void;
  onCreateFromTemplate?: () => void;
}

export function AutoTaskList({
  tasks,
  latestTaskEvents,
  pendingActionTaskId,
  availableModels = [],
  onRunNow,
  onToggleTask,
  onEditTask,
  onDeleteTask,
  onCreateFromTemplate,
}: AutoTaskListProps) {
  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-background">
      {tasks.length > 0 ? (
        <div className="divide-y divide-border/70">
          {tasks.map((task) => {
            const latestTaskEvent = latestTaskEvents.get(task.task_id) ?? null;
            const isMutating = pendingActionTaskId === task.task_id;
            const hasError =
              task.consecutive_errors > 0 || Boolean(task.last_error);
            const modelId = task.model_id || task.model || "";
            const configuredModel = modelId
              ? availableModels.find(
                  (model) => model.id === modelId || model.model === modelId,
                )
              : null;
            const modelLabel = configuredModel?.name || modelId || "跟随默认模型";

            return (
              <div
                key={task.task_id}
                className="px-3.5 py-3 transition-colors hover:bg-muted/20"
              >
                <div className="flex min-w-0 flex-col gap-3">
                  <div className="min-w-0 space-y-2">
                    <div className="flex min-w-0 items-start justify-between gap-2">
                      <div className="min-w-0 flex-1 truncate text-sm font-semibold tracking-tight text-foreground">
                        {getAutoTaskTitle(task)}
                      </div>
                      <Badge
                        variant="outline"
                        className={taskStatusBadgeClass(task.status)}
                      >
                        {STATUS_LABEL[task.status]}
                      </Badge>
                    </div>

                    <div className="grid min-w-0 gap-1.5 text-[11px] leading-5 text-muted-foreground">
                      <AutoTaskMetaRow
                        label="触发"
                        value={formatScheduleValue(task)}
                      />
                      {shouldShowTaskFirstRunPolicy(task) ? (
                        <AutoTaskMetaRow
                          label="首次"
                          value={
                            FIRST_RUN_POLICY_LABEL[
                              task.first_run_policy ?? "next_scheduled"
                            ]
                          }
                        />
                      ) : null}
                      <AutoTaskMetaRow
                        label="策略"
                        value={`${TASK_CATEGORY_LABEL[task.task_category ?? "scheduled"]} · ${OVERLAP_POLICY_LABEL[task.overlap_policy]}`}
                      />
                      <AutoTaskMetaRow
                        label="会话"
                        value={task.bind_session_id ? "绑定会话" : "每次新建会话"}
                      />
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge
                        variant="outline"
                        className="shrink-0 border-border bg-muted/15 text-muted-foreground"
                      >
                        {modelLabel}
                      </Badge>
                      {hasError ? (
                        <Badge
                          variant="outline"
                          className="shrink-0 border-error/20 bg-error-container text-error"
                        >
                          异常 {task.consecutive_errors || 1}
                        </Badge>
                      ) : null}
                      {task.pending_run_count > 0 ? (
                        <Badge
                          variant="outline"
                          className="shrink-0 border-warning/20 bg-warning-container text-warning"
                        >
                          排队 {task.pending_run_count}
                        </Badge>
                      ) : null}
                    </div>

                    <div className="mt-1 truncate text-[12px] leading-5 text-muted-foreground">
                      {summarizeText(task.prompt, 88)}
                    </div>

                    <div className="mt-2 grid gap-1 text-[11px] leading-5 text-muted-foreground sm:grid-cols-2">
                      <span className="min-w-0 truncate">
                        下次 {formatTimestamp(task.next_run_at)}
                      </span>
                      <span className="min-w-0 truncate">
                        上次 {formatTimestamp(task.last_run_at)}
                      </span>
                      <span className="min-w-0 truncate">
                        已触发 {task.fired_count} 次
                      </span>
                      <span className="min-w-0 truncate">
                        事件{" "}
                        {latestTaskEvent
                          ? formatTimestamp(latestTaskEvent.created_at)
                          : "未触发"}
                      </span>
                      {task.attachments.length > 0 ? (
                        <span className="min-w-0 truncate">
                          {task.attachments.length} 个附件
                        </span>
                      ) : null}
                    </div>
                    {task.task_category === "continuous" ? (
                      <div className="mt-1 text-[11px] leading-5 text-muted-foreground">
                        {formatStopConditionsSummary(task)}
                      </div>
                    ) : null}

                    {task.last_error ? (
                      <div className="mt-2 truncate text-[11px] leading-5 text-error">
                        最近错误：{task.last_error}
                      </div>
                    ) : null}
                  </div>

                  <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center">
                    <Button
                      type="button"
                      size="sm"
                      className="h-8 gap-1.5 rounded-xl px-3 text-[11px]"
                      onClick={() => onRunNow(task)}
                      disabled={isMutating}
                    >
                      <Play className="h-3.5 w-3.5" />
                      立即运行
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="h-8 gap-1.5 rounded-xl px-3 text-[11px]"
                      onClick={() => onToggleTask(task)}
                      disabled={isMutating || task.status === "completed"}
                    >
                      {task.status === "active" ? (
                        <Pause className="h-3.5 w-3.5" />
                      ) : (
                        <Play className="h-3.5 w-3.5" />
                      )}
                      {task.status === "active" ? "暂停" : "启用"}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="h-8 gap-1.5 rounded-xl px-3 text-[11px]"
                      onClick={() => onEditTask(task)}
                      disabled={isMutating}
                    >
                      <PencilLine className="h-3.5 w-3.5" />
                      编辑
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="h-8 gap-1.5 rounded-xl border-error/20 px-3 text-[11px] text-error hover:bg-error-container hover:text-error"
                      onClick={() => onDeleteTask(task)}
                      disabled={isMutating}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      删除
                    </Button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="px-4 py-10 text-center">
          <div className="text-sm font-medium text-foreground">
            当前工作区还没有自动化任务
          </div>
          {onCreateFromTemplate ? (
            <Button
              type="button"
              size="sm"
              className="mt-4 h-8 gap-1.5 rounded-xl px-4 text-[11px]"
              onClick={onCreateFromTemplate}
            >
              <Plus className="h-3.5 w-3.5" />
              从模板开始
            </Button>
          ) : null}
        </div>
      )}
    </section>
  );
}

function taskStatusBadgeClass(status: WorkspaceAutoTask["status"]): string {
  return `shrink-0 whitespace-nowrap ${STATUS_BADGE_CLASS[status]}`;
}

function AutoTaskMetaRow({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <span className="shrink-0 text-muted-foreground/70">{label}</span>
      <span className="min-w-0 truncate font-medium text-foreground/80">
        {value}
      </span>
    </div>
  );
}
