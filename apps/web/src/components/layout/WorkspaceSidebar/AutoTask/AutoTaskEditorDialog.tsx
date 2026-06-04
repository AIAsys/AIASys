import { CheckCircle2 } from "lucide-react";
import { useEffect, useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { LLMModelConfig } from "@/lib/api/llm";
import { cn } from "@/lib/utils";

import type {
  AutoTaskDraft,
  AutoTaskSessionOption,
  AutoTaskTemplate,
  SetAutoTaskDraft,
} from "./types";
import {
  FIRST_RUN_POLICY_LABEL,
  TASK_CATEGORY_LABEL,
  formatDraftSchedule,
  parseFixedTimeScheduleValue,
  parseIntervalScheduleValue,
  shouldShowFirstRunPolicy,
} from "./scheduleFormat";
import { AutoTaskEditorPreview } from "./AutoTaskEditorPreview";
import {
  DEFAULT_AUTO_TASK_MODEL_VALUE,
  getSessionOptionLabel,
  type ScheduledTriggerType,
} from "./AutoTaskEditorOptions";
import {
  AutomationModeSection,
  BasicInfoSection,
  ContinuousRunSection,
  RunSettingsSection,
  SessionStrategySection,
  TargetWorkspaceSection,
  TriggerRuleSection,
} from "./AutoTaskEditorSections";
import { AutoTaskTemplateRail } from "./AutoTaskTemplateRail";

interface AutoTaskEditorDialogProps {
  open: boolean;
  editingTaskId: string | null;
  selectedTemplateId: string | null;
  draft: AutoTaskDraft;
  setDraft: SetAutoTaskDraft;
  isSaving: boolean;
  submitLabel: string;
  templates: AutoTaskTemplate[];
  sessionOptions?: AutoTaskSessionOption[];
  availableModels?: LLMModelConfig[];
  targetWorkspaceId?: string;
  availableWorkspaces?: Array<{ id: string; title: string }>;
  onTargetWorkspaceChange?: (workspaceId: string) => void;
  feedback?: { tone: "success" | "error"; message: string } | null;
  onOpenChange: (open: boolean) => void;
  onApplyTemplate: (template: AutoTaskTemplate) => void;
  onSubmit: () => void;
}

function toDatetimeLocalNow(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const localDate = new Date(now.getTime() - offset * 60_000);
  return localDate.toISOString().slice(0, 16);
}

export function AutoTaskEditorDialog({
  open,
  editingTaskId,
  selectedTemplateId,
  draft,
  setDraft,
  isSaving,
  submitLabel,
  templates,
  sessionOptions = [],
  availableModels = [],
  targetWorkspaceId,
  availableWorkspaces,
  onTargetWorkspaceChange,
  feedback,
  onOpenChange,
  onApplyTemplate,
  onSubmit,
}: AutoTaskEditorDialogProps) {
  const isScheduled = draft.taskCategory === "scheduled";
  const currentSessionOption = sessionOptions.find((option) => option.isCurrent);
  const selectedSessionLabel = getSessionOptionLabel(
    sessionOptions,
    draft.bindSessionId,
  );
  const intervalDraft = useMemo(
    () => parseIntervalScheduleValue(draft.triggerValue),
    [draft.triggerValue],
  );
  const fixedTimeDraft = useMemo(
    () => parseFixedTimeScheduleValue(draft.triggerValue),
    [draft.triggerValue],
  );
  const scheduleSummary = useMemo(() => formatDraftSchedule(draft), [draft]);
  const chatModels = useMemo(
    () =>
      availableModels.filter(
        (m) => m.enabled !== false && (m.model_type ?? "chat") === "chat",
      ),
    [availableModels],
  );
  const selectedModelId = draft.modelId.trim();
  const selectedModel = selectedModelId
    ? chatModels.find((m) => m.id === selectedModelId)
    : null;
  const modelByRawName = selectedModelId
    ? chatModels.find((m) => m.model === selectedModelId)
    : null;
  const previewModel = selectedModel || modelByRawName;
  const modelSelectValue = selectedModelId || DEFAULT_AUTO_TASK_MODEL_VALUE;
  const modelPreviewLabel = selectedModelId
    ? previewModel?.name || `当前配置：${selectedModelId}`
    : "跟随任务默认模型";
  const modelPreviewHint = previewModel
    ? `${previewModel.model} · local`
    : selectedModelId
      ? `${selectedModelId} · local`
      : "local";
  const activeTemplate = selectedTemplateId
    ? templates.find((template) => template.id === selectedTemplateId)
    : null;
  const stopSummary = [
    draft.stopOnSignal ? "AI 可自主结束" : null,
    draft.maxContinuations > 0 ? `最多 ${draft.maxContinuations} 轮` : null,
    draft.maxContinuations < 0 ? "不限制轮次" : null,
    `${draft.stopOnConsecutiveErrors} 次错误禁用`,
  ]
    .filter(Boolean)
    .join(" · ");

  const handleTriggerTypeChange = (value: ScheduledTriggerType) => {
    setDraft((prev) => ({
      ...prev,
      taskCategory: "scheduled",
      triggerType: value,
      triggerValue:
        value === "interval"
          ? prev.triggerType === "interval"
            ? prev.triggerValue
            : "86400"
          : value === "cron"
            ? prev.triggerType === "cron"
              ? prev.triggerValue
              : "0 8 * * *"
          : prev.triggerType === "once"
            ? prev.triggerValue
            : toDatetimeLocalNow(),
      firstRunPolicy:
        value === "interval" || value === "cron"
          ? prev.firstRunPolicy
          : "next_scheduled",
    }));
  };

  const handleSessionStrategyChange = (
    value: AutoTaskDraft["sessionStrategy"],
  ) => {
    setDraft((prev) => ({
      ...prev,
      sessionStrategy: value,
      bindSessionId:
        value === "bind_session"
          ? prev.bindSessionId.trim() || currentSessionOption?.sessionId || ""
          : "",
      overlapPolicy:
        value === "bind_session" && prev.overlapPolicy === "parallel"
          ? "skip"
          : prev.overlapPolicy,
    }));
  };

  const handleAutomationModeChange = (
    value: AutoTaskDraft["taskCategory"],
  ) => {
    setDraft((prev) => {
      if (value === "continuous") {
        return {
          ...prev,
          taskCategory: "continuous",
          triggerType: "continuous",
          triggerValue: "",
          sessionStrategy: "bind_session",
          bindSessionId:
            prev.bindSessionId.trim() || currentSessionOption?.sessionId || "",
          overlapPolicy: prev.overlapPolicy === "parallel" ? "skip" : prev.overlapPolicy,
          maxContinuations:
            prev.maxContinuations === 0 ? -1 : prev.maxContinuations,
          firstRunPolicy: "immediate",
        };
      }

      return {
        ...prev,
        taskCategory: "scheduled",
        triggerType:
          prev.triggerType === "continuous" ? "interval" : prev.triggerType,
        triggerValue:
          prev.triggerType === "continuous" ? "86400" : prev.triggerValue,
        firstRunPolicy:
          prev.triggerType === "continuous" ? "next_scheduled" : prev.firstRunPolicy,
      };
    });
  };

  const footerHint = isScheduled
    ? shouldShowFirstRunPolicy(draft)
      ? `保存后${draft.enabled ? FIRST_RUN_POLICY_LABEL[draft.firstRunPolicy] : "先暂停任务"}，之后按执行模式继续运行。`
      : "保存后按执行模式启动自动化任务。"
    : "保存后按停止条件持续推进目标。";

  useEffect(() => {
    if (!open || !currentSessionOption) {
      return;
    }
    if (
      draft.sessionStrategy !== "bind_session" ||
      draft.bindSessionId.trim()
    ) {
      return;
    }
    setDraft((prev) => {
      if (
        prev.sessionStrategy !== "bind_session" ||
        prev.bindSessionId.trim()
      ) {
        return prev;
      }
      return {
        ...prev,
        bindSessionId: currentSessionOption.sessionId,
      };
    });
  }, [
    currentSessionOption,
    draft.bindSessionId,
    draft.sessionStrategy,
    open,
    setDraft,
  ]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-[900px] p-0 overflow-hidden">
        <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] bg-background">
          <SheetHeader className="border-b border-border px-6 py-4 pr-12">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <SheetTitle className="text-xl">
                    {editingTaskId
                      ? `编辑${TASK_CATEGORY_LABEL[draft.taskCategory]}自动化`
                      : `新建${TASK_CATEGORY_LABEL[draft.taskCategory]}自动化`}
                  </SheetTitle>
                  <Badge
                    variant="outline"
                    className={cn(
                      "rounded-full px-2.5 py-1",
                      draft.enabled
                        ? "border-success/20 bg-success-container text-success"
                        : "border-warning/20 bg-warning-container text-warning",
                    )}
                  >
                    {draft.enabled ? "保存后启用" : "保存为暂停"}
                  </Badge>
                </div>
                <SheetDescription className="mt-1">
                  配置执行模式、目标会话、停止条件和运行模型。
                </SheetDescription>
              </div>
              {feedback ? (
                <div
                  className={cn(
                    "max-w-md rounded-xl border px-3 py-2 text-[12px] leading-5",
                    feedback.tone === "success"
                      ? "border-success/20 bg-success-container text-success"
                      : "border-error/20 bg-error-container text-error",
                  )}
                >
                  {feedback.message}
                </div>
              ) : null}
            </div>
          </SheetHeader>

          <div className="grid min-h-0 grid-cols-1 lg:grid-cols-[236px_minmax(0,1fr)_300px]">
            <AutoTaskTemplateRail
              editingTaskId={editingTaskId}
              isScheduled={isScheduled}
              taskCategory={draft.taskCategory}
              selectedTemplateId={selectedTemplateId}
              templates={templates}
              onApplyTemplate={onApplyTemplate}
            />

            <main className="min-h-0 overflow-y-auto px-5 py-5">
              <div className="mx-auto max-w-[680px] space-y-4">
                <TargetWorkspaceSection
                  editingTaskId={editingTaskId}
                  targetWorkspaceId={targetWorkspaceId}
                  availableWorkspaces={availableWorkspaces}
                  onTargetWorkspaceChange={onTargetWorkspaceChange}
                />

                <BasicInfoSection
                  isScheduled={isScheduled}
                  draft={draft}
                  setDraft={setDraft}
                />

                <AutomationModeSection
                  draft={draft}
                  onAutomationModeChange={handleAutomationModeChange}
                />

                {isScheduled ? (
                  <>
                    <TriggerRuleSection
                      draft={draft}
                      setDraft={setDraft}
                      intervalDraft={intervalDraft}
                      fixedTimeDraft={fixedTimeDraft}
                      onTriggerTypeChange={handleTriggerTypeChange}
                    />

                    <SessionStrategySection
                      draft={draft}
                      setDraft={setDraft}
                      sessionOptions={sessionOptions}
                      onSessionStrategyChange={handleSessionStrategyChange}
                    />
                  </>
                ) : (
                  <ContinuousRunSection
                    draft={draft}
                    setDraft={setDraft}
                    sessionOptions={sessionOptions}
                  />
                )}

                <RunSettingsSection
                  draft={draft}
                  setDraft={setDraft}
                  modelSelectValue={modelSelectValue}
                  selectedModelId={selectedModelId}
                  selectedModel={selectedModel}
                  chatModels={chatModels}
                />
              </div>
            </main>

            <AutoTaskEditorPreview
              draft={draft}
              isScheduled={isScheduled}
              scheduleSummary={scheduleSummary}
              activeTemplate={activeTemplate}
              modelPreviewLabel={modelPreviewLabel}
              modelPreviewHint={modelPreviewHint}
              stopSummary={stopSummary}
              selectedSessionLabel={selectedSessionLabel}
            />
          </div>

          <div className="border-t border-border bg-background px-6 py-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2 text-[12px] text-muted-foreground">
                <CheckCircle2 className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="truncate">{footerHint}</span>
              </div>
              <div className="flex items-center justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => onOpenChange(false)}
                  disabled={isSaving}
                >
                  取消
                </Button>
                <Button type="button" onClick={onSubmit} disabled={isSaving}>
                  {isSaving ? "保存中..." : submitLabel}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
