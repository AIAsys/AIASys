import {
  AlertCircle,
  Plus,
  RefreshCw,
  Zap,
} from "lucide-react";
import { useMemo, useState, lazy, Suspense } from "react";

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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { LLMModelConfig } from "@/lib/api/llm";
import type { TaskExecutionPolicySummary } from "@/types/autoTask";
import type { WorkspaceConversationSummary } from "@/pages/DataAnalysisPage/types";

import {
  AutoTaskCategorySelector,
  AutoTaskList,
} from "./AutoTask";

const LazyAutoTaskEditorDialog = lazy(() =>
  import("./AutoTask/AutoTaskEditorDialog").then((module) => ({
    default: module.AutoTaskEditorDialog,
  })),
);
import { useWorkspaceAutoTasks } from "./AutoTask/hooks/useWorkspaceAutoTasks";
import { getAutoTaskTitle } from "./AutoTask/scheduleFormat";
import {
  getDefaultAutoTaskTemplate,
  getAutoTaskTemplates,
} from "./AutoTask/templates";
import type { AutoTaskSessionOption } from "./AutoTask/types";

interface WorkspaceAutoTaskPanelProps {
  workspaceId?: string;
  executionPolicy?: TaskExecutionPolicySummary | null;
  availableModels?: LLMModelConfig[];
  currentSessionId?: string | null;
  currentSessionTitle?: string | null;
  conversations?: WorkspaceConversationSummary[];
  currentConversation?: WorkspaceConversationSummary | null;
}

export function WorkspaceAutoTaskPanel({
  workspaceId,
  executionPolicy,
  availableModels = [],
  currentSessionId,
  currentSessionTitle,
  conversations = [],
  currentConversation = null,
}: WorkspaceAutoTaskPanelProps) {
  const isAutoExploreWorkspace = executionPolicy?.mode === "auto_explore";
  const templates = useMemo(() => getAutoTaskTemplates(), []);
  const defaultTemplate = useMemo(() => getDefaultAutoTaskTemplate(), []);
  const sessionOptions = useMemo<AutoTaskSessionOption[]>(() => {
    const optionMap = new Map<string, AutoTaskSessionOption>();
    const addConversation = (
      conversation: WorkspaceConversationSummary | null | undefined,
    ) => {
      if (!conversation?.session_id) {
        return;
      }
      const sessionId = conversation.session_id;
      optionMap.set(sessionId, {
        sessionId,
        title: conversation.title || "未命名会话",
        isCurrent:
          sessionId === currentSessionId ||
          conversation.conversation_id === currentConversation?.conversation_id,
        updatedAt: conversation.updated_at,
        messageCount: conversation.message_count,
      });
    };

    addConversation(currentConversation);
    conversations.forEach(addConversation);

    if (currentSessionId && !optionMap.has(currentSessionId)) {
      optionMap.set(currentSessionId, {
        sessionId: currentSessionId,
        title:
          currentSessionTitle?.trim() ||
          currentConversation?.title ||
          "当前会话",
        isCurrent: true,
        updatedAt: currentConversation?.updated_at ?? null,
        messageCount: currentConversation?.message_count ?? null,
      });
    }

    return [...optionMap.values()].sort((left, right) => {
      if (left.isCurrent !== right.isCurrent) {
        return left.isCurrent ? -1 : 1;
      }
      return (right.updatedAt || "").localeCompare(left.updatedAt || "");
    });
  }, [
    conversations,
    currentConversation,
    currentSessionId,
    currentSessionTitle,
  ]);
  const autoTask = useWorkspaceAutoTasks({
    workspaceId,
    defaultBindSessionId:
      sessionOptions.find((option) => option.isCurrent)?.sessionId ??
      currentSessionId ??
      currentConversation?.session_id ??
      "",
  });
  const [categorySelectorOpen, setCategorySelectorOpen] = useState(false);

  if (!workspaceId) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center">
        <div className="max-w-lg space-y-3">
          <div className="text-base font-semibold text-foreground">
            当前没有绑定工作区
          </div>
          <div className="text-sm leading-6 text-muted-foreground">
            自动化任务属于工作区，先进入一个工作区才能查看或管理。
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <div className="border-b border-border bg-background px-5 py-3.5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-2 text-base font-semibold tracking-tight text-foreground">
                <Zap className="h-4 w-4 text-muted-foreground" />
                自动化任务
              </div>
              <Badge
                variant="outline"
                className="border-border bg-background text-muted-foreground"
              >
                {autoTask.taskSummary.total} 条
              </Badge>
              {autoTask.taskSummary.active > 0 ? (
                <Badge
                  variant="outline"
                  className="border-success/20 bg-success-container text-success"
                >
                  {autoTask.taskSummary.active} 运行中
                </Badge>
              ) : null}
              {autoTask.taskSummary.idle > 0 ? (
                <Badge
                  variant="outline"
                  className="border-warning/20 bg-warning-container text-warning"
                >
                  {autoTask.taskSummary.idle} 已停用
                </Badge>
              ) : null}
              {autoTask.taskSummary.error > 0 ? (
                <Badge
                  variant="outline"
                  className="border-error/20 bg-error-container text-error"
                >
                  {autoTask.taskSummary.error} 异常
                </Badge>
              ) : null}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="sm"
              className="h-8 gap-1.5 rounded-xl px-3 text-[12px]"
              onClick={() => setCategorySelectorOpen(true)}
            >
              <Plus className="h-3.5 w-3.5" />
              新建自动化任务
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 gap-1.5 rounded-xl px-3 text-[12px]"
              onClick={() => void autoTask.loadAutoTasks()}
              disabled={autoTask.isLoading}
            >
              <RefreshCw
                className={cn(
                  "h-3.5 w-3.5",
                  autoTask.isLoading && "animate-spin",
                )}
              />
              刷新
            </Button>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <div className="space-y-4">
          {autoTask.feedback ? (
            <div
              className={cn(
                "rounded-2xl border px-4 py-3 text-sm",
                autoTask.feedback.tone === "success"
                  ? "border-success/20 bg-success-container text-success"
                  : "border-error/20 bg-error-container text-error",
              )}
            >
              {autoTask.feedback.message}
            </div>
          ) : null}

          {autoTask.loadError ? (
            <div className="rounded-2xl border border-warning/20 bg-warning-container/70 px-4 py-3 text-sm text-warning">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4" />
                {autoTask.loadError}
              </div>
            </div>
          ) : null}

          {isAutoExploreWorkspace ? (
            <div className="rounded-2xl border border-info/20 bg-info-container/80 px-4 py-3 text-sm text-info">
              当前工作区支持自动推进，自动化任务每次只会在工作区里新建一条普通会话；
              它不会直接接管你当前正在看的会话，也不会改写你手头这条会话。
            </div>
          ) : null}

          <AutoTaskList
            tasks={autoTask.sortedTasks}
            latestTaskEvents={autoTask.latestTaskEvents}
            pendingActionTaskId={autoTask.pendingActionTaskId}
            availableModels={availableModels}
            onRunNow={(task) => void autoTask.handleRunNow(task)}
            onToggleTask={(task) => void autoTask.handleToggleTask(task)}
            onEditTask={autoTask.openEditDialog}
            onDeleteTask={(task) => autoTask.setPendingDeleteTask(task)}
            onCreateFromTemplate={() =>
              autoTask.openCreateDialog(defaultTemplate)
            }
          />
        </div>
      </div>

      <AutoTaskCategorySelector
        open={categorySelectorOpen}
        onOpenChange={setCategorySelectorOpen}
        onSelectCategory={(category) => {
          setCategorySelectorOpen(false);
          autoTask.openCreateDialog(undefined, category);
        }}
      />

      <Suspense fallback={null}>
        <LazyAutoTaskEditorDialog
          open={autoTask.isEditorOpen}
          editingTaskId={autoTask.editingTaskId}
          selectedTemplateId={autoTask.selectedTemplateId}
          draft={autoTask.draft}
          setDraft={autoTask.setDraft}
          isSaving={autoTask.isSaving}
          submitLabel={autoTask.draftSubmitLabel}
          templates={templates}
          sessionOptions={sessionOptions}
          availableModels={availableModels}
          onOpenChange={(open) => {
            if (!open) {
              autoTask.closeEditor();
            }
          }}
          onApplyTemplate={autoTask.applyTemplate}
          onSubmit={() => void autoTask.handleSubmit()}
        />
      </Suspense>

      <AlertDialog
        open={Boolean(autoTask.pendingDeleteTask)}
        onOpenChange={(open) => {
          if (!open) {
            autoTask.setPendingDeleteTask(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除自动化任务</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除 “
              {autoTask.pendingDeleteTask
                ? getAutoTaskTitle(autoTask.pendingDeleteTask)
                : ""}
              ” 吗？
              这会移除后续自动触发计划，但不会回滚已经写入工作区自动化记录的
              trigger 历史。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              disabled={
                autoTask.pendingActionTaskId === autoTask.pendingDeleteTask?.task_id
              }
            >
              取消
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault();
                void autoTask.confirmDeleteTask();
              }}
              disabled={
                autoTask.pendingActionTaskId === autoTask.pendingDeleteTask?.task_id
              }
            >
              {autoTask.pendingActionTaskId === autoTask.pendingDeleteTask?.task_id
                ? "删除中..."
                : "确认删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default WorkspaceAutoTaskPanel;
