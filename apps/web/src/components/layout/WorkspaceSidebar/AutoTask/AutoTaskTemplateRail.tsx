import { CheckCircle2, Infinity as InfinityIcon, Timer } from "lucide-react";

import { cn } from "@/lib/utils";

import type { AutoTaskDraft, AutoTaskTemplate } from "./types";
import {
  TASK_CATEGORY_LABEL,
  formatFixedTimeExpression,
  formatTimestamp,
} from "./scheduleFormat";

function formatTemplateTrigger(template: AutoTaskTemplate) {
  if (template.triggerType === "interval") {
    return `每 ${template.triggerValue} 秒`;
  }
  if (template.triggerType === "cron") {
    return formatFixedTimeExpression(template.triggerValue);
  }
  return formatTimestamp(template.triggerValue);
}

export function AutoTaskTemplateRail({
  editingTaskId,
  isScheduled,
  taskCategory,
  selectedTemplateId,
  templates,
  onApplyTemplate,
}: {
  editingTaskId: string | null;
  isScheduled: boolean;
  taskCategory: AutoTaskDraft["taskCategory"];
  selectedTemplateId: string | null;
  templates: AutoTaskTemplate[];
  onApplyTemplate: (template: AutoTaskTemplate) => void;
}) {
  return (
    <aside className="min-h-0 border-b border-border bg-muted/10 lg:border-b-0 lg:border-r">
      <div className="max-h-[210px] overflow-y-auto px-5 py-4 lg:h-full lg:max-h-none lg:px-4 lg:py-5">
        {!editingTaskId && isScheduled ? (
          <div className="space-y-3">
            <div>
              <div className="text-sm font-semibold text-foreground">模板</div>
              <div className="mt-1 text-[12px] leading-5 text-muted-foreground">
                先选一个起点，再调整细节。
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-1">
              {templates.map((template) => {
                const selected = selectedTemplateId === template.id;
                return (
                  <button
                    key={template.id}
                    type="button"
                    className={cn(
                      "rounded-xl border px-3 py-3 text-left transition",
                      selected
                        ? "border-foreground bg-background shadow-sm"
                        : "border-border bg-background/70 hover:border-foreground/30 hover:bg-background",
                    )}
                    onClick={() => onApplyTemplate(template)}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 text-sm font-semibold leading-5 text-foreground">
                        {template.name}
                      </div>
                      {selected ? (
                        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                      ) : null}
                    </div>
                    <div className="mt-2 inline-flex rounded-full border border-border bg-muted/20 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                      {formatTemplateTrigger(template)}
                    </div>
                    <div className="mt-2 text-[12px] leading-5 text-muted-foreground">
                      {template.summary}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div>
              <div className="text-sm font-semibold text-foreground">
                当前配置
              </div>
              <div className="mt-1 text-[12px] leading-5 text-muted-foreground">
                {editingTaskId ? "正在编辑已有自动化任务。" : "正在新建自动化任务。"}
              </div>
            </div>
            <div className="rounded-xl border border-border bg-background px-3 py-3">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                {isScheduled ? (
                  <Timer className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <InfinityIcon className="h-4 w-4 text-muted-foreground" />
                )}
                {TASK_CATEGORY_LABEL[taskCategory]}
              </div>
              <div className="mt-2 text-[12px] leading-5 text-muted-foreground">
                {isScheduled
                  ? "按时间规则启动自动化任务。"
                  : "按停止条件连续推进目标。"}
              </div>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
