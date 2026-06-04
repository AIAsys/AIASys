import { PauseCircle, PlayCircle } from "lucide-react";

import type { AutoTaskDraft, AutoTaskTemplate } from "./types";
import {
  FIRST_RUN_POLICY_LABEL,
  OVERLAP_POLICY_LABEL,
  shouldShowFirstRunPolicy,
  summarizeText,
} from "./scheduleFormat";
import { PreviewRow } from "./AutoTaskEditorPrimitives";

export function AutoTaskEditorPreview({
  draft,
  isScheduled,
  scheduleSummary,
  activeTemplate,
  modelPreviewLabel,
  modelPreviewHint,
  stopSummary,
  selectedSessionLabel,
}: {
  draft: AutoTaskDraft;
  isScheduled: boolean;
  scheduleSummary: string;
  activeTemplate: AutoTaskTemplate | null | undefined;
  modelPreviewLabel: string;
  modelPreviewHint: string;
  stopSummary: string;
  selectedSessionLabel: string;
}) {
  return (
    <aside className="min-h-0 border-t border-border bg-muted/10 lg:border-l lg:border-t-0">
      <div className="h-full overflow-y-auto px-5 py-5">
        <div className="rounded-xl border border-border bg-background p-4 shadow-sm">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-foreground">
                发布前检查
              </div>
              <div className="mt-1 text-[12px] leading-5 text-muted-foreground">
                确认这条自动化任务会怎么运行。
              </div>
            </div>
            {draft.enabled ? (
              <PlayCircle className="h-5 w-5 text-success" />
            ) : (
              <PauseCircle className="h-5 w-5 text-warning" />
            )}
          </div>

          <div className="mt-4">
            <PreviewRow
              label="任务名称"
              value={draft.title.trim() || "未命名任务"}
              hint={activeTemplate ? `来自模板：${activeTemplate.name}` : undefined}
            />
            {isScheduled ? (
              <>
                <PreviewRow
                  label="触发规则"
                  value={scheduleSummary}
                  hint={
                    draft.triggerType === "interval"
                      ? "按间隔重复启动"
                      : draft.triggerType === "cron"
                        ? "按固定时间启动"
                        : "只启动一次"
                  }
                />
                {shouldShowFirstRunPolicy(draft) ? (
                  <PreviewRow
                    label="首次执行"
                    value={FIRST_RUN_POLICY_LABEL[draft.firstRunPolicy]}
                    hint={
                      draft.firstRunPolicy === "immediate"
                        ? "保存并启用后先触发一次"
                        : "等第一个计划时间点触发"
                    }
                  />
                ) : null}
                <PreviewRow
                  label="会话策略"
                  value={
                    draft.sessionStrategy === "bind_session"
                      ? "绑定已有会话"
                      : "每次新建普通会话"
                  }
                  hint={
                    draft.sessionStrategy === "bind_session"
                      ? draft.bindSessionId.trim()
                        ? selectedSessionLabel
                        : "还没有选择会话"
                      : "新会话完成后可继续正常对话"
                  }
                />
                <PreviewRow
                  label="上次未结束时"
                  value={OVERLAP_POLICY_LABEL[draft.overlapPolicy]}
                />
              </>
            ) : (
              <>
                <PreviewRow
                  label="续推方式"
                  value={
                    draft.continuationPrompt.trim()
                      ? summarizeText(draft.continuationPrompt, 52)
                      : "使用默认续推提示词"
                  }
                />
                <PreviewRow label="停止条件" value={stopSummary} />
                <PreviewRow
                  label="绑定会话"
                  value={
                    draft.bindSessionId.trim()
                      ? selectedSessionLabel
                      : "还没有选择会话"
                  }
                  hint="连续推进会在这条会话上下文里继续运行"
                />
              </>
            )}
            <PreviewRow
              label="运行模型"
              value={modelPreviewLabel}
              hint={modelPreviewHint}
            />
            <PreviewRow
              label="提示词摘要"
              value={summarizeText(draft.prompt, 72)}
            />
          </div>
        </div>
      </div>
    </aside>
  );
}
