import {
  FileText,
  GitBranch,
  Infinity as InfinityIcon,
  PlayCircle,
  Settings2,
  Timer,
} from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { LLMModelConfig } from "@/lib/api/llm";
import { cn } from "@/lib/utils";

import {
  AUTOMATION_MODE_OPTIONS,
  DEFAULT_AUTO_TASK_MODEL_VALUE,
  NO_AUTO_TASK_MODEL_VALUE,
  OVERLAP_POLICY_OPTIONS,
  SESSION_STRATEGY_OPTIONS,
  TRIGGER_TYPE_OPTIONS,
  formatSessionOptionLabel,
  getSessionOptionLabel,
  type ScheduledTriggerType,
} from "./AutoTaskEditorOptions";
import {
  ChoiceButton,
  SectionBlock,
  ToggleRow,
} from "./AutoTaskEditorPrimitives";
import type {
  AutoTaskDraft,
  AutoTaskSessionOption,
  SetAutoTaskDraft,
} from "./types";
import {
  MIN_INTERVAL_SECONDS,
  buildFixedTimeScheduleValue,
  buildIntervalScheduleValue,
  parseFixedTimeScheduleValue,
  parseIntervalScheduleValue,
  shouldShowFirstRunPolicy,
} from "./scheduleFormat";

type IntervalDraft = ReturnType<typeof parseIntervalScheduleValue>;
type FixedTimeDraft = ReturnType<typeof parseFixedTimeScheduleValue>;

export function AutomationModeSection({
  draft,
  onAutomationModeChange,
}: {
  draft: AutoTaskDraft;
  onAutomationModeChange: (value: AutoTaskDraft["taskCategory"]) => void;
}) {
  return (
    <SectionBlock
      title="自动化类型"
      description="先选择它靠时间触发，还是围绕一个目标连续推进。"
      icon={Timer}
    >
      <div className="grid gap-3 md:grid-cols-2">
        {AUTOMATION_MODE_OPTIONS.map((option) => (
          <ChoiceButton
            key={option.value}
            value={option.value}
            selected={draft.taskCategory === option.value}
            label={option.label}
            description={option.description}
            icon={option.icon}
            onSelect={onAutomationModeChange}
          />
        ))}
      </div>
    </SectionBlock>
  );
}

export function TargetWorkspaceSection({
  editingTaskId,
  targetWorkspaceId,
  availableWorkspaces,
  onTargetWorkspaceChange,
}: {
  editingTaskId: string | null;
  targetWorkspaceId?: string;
  availableWorkspaces?: Array<{ id: string; title: string }>;
  onTargetWorkspaceChange?: (workspaceId: string) => void;
}) {
  if (!availableWorkspaces || availableWorkspaces.length === 0) {
    return null;
  }

  return (
    <SectionBlock
      title="目标工作区"
      description="自动化任务会保存到这个工作区。"
      icon={GitBranch}
    >
      {editingTaskId ? (
        <div className="flex h-10 items-center rounded-xl border border-border bg-muted/15 px-3 text-sm text-foreground">
          {availableWorkspaces.find((w) => w.id === targetWorkspaceId)?.title ||
            targetWorkspaceId ||
            "未指定"}
        </div>
      ) : (
        <Select
          value={targetWorkspaceId || ""}
          onValueChange={(value) => onTargetWorkspaceChange?.(value)}
        >
          <SelectTrigger id="auto-task-target-workspace">
            <SelectValue placeholder="选择工作区" />
          </SelectTrigger>
          <SelectContent>
            {availableWorkspaces.map((workspace) => (
              <SelectItem key={workspace.id} value={workspace.id}>
                {workspace.title}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </SectionBlock>
  );
}

export function BasicInfoSection({
  isScheduled,
  draft,
  setDraft,
}: {
  isScheduled: boolean;
  draft: AutoTaskDraft;
  setDraft: SetAutoTaskDraft;
}) {
  return (
    <SectionBlock
      title="基础信息"
      description={isScheduled ? "写清楚这一轮要完成什么。" : "写清楚连续推进的目标。"}
      icon={FileText}
    >
      <div className="space-y-2">
        <Label htmlFor="auto-task-title">任务名称</Label>
        <Input
          id="auto-task-title"
          value={draft.title}
          onChange={(e) =>
            setDraft((prev) => ({ ...prev, title: e.target.value }))
          }
          placeholder="例如：每日自动巡检会话"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="auto-task-prompt">
          {isScheduled ? "执行提示词" : "目标提示词"}
        </Label>
        <Textarea
          id="auto-task-prompt"
          value={draft.prompt}
          onChange={(e) =>
            setDraft((prev) => ({ ...prev, prompt: e.target.value }))
          }
          placeholder={
            isScheduled
              ? "写清楚这条规则触发后要做什么"
              : "描述这个连续任务要达成的最终目标"
          }
          className="min-h-[128px] resize-y leading-6"
        />
      </div>
    </SectionBlock>
  );
}

export function TriggerRuleSection({
  draft,
  setDraft,
  intervalDraft,
  fixedTimeDraft,
  onTriggerTypeChange,
}: {
  draft: AutoTaskDraft;
  setDraft: SetAutoTaskDraft;
  intervalDraft: IntervalDraft;
  fixedTimeDraft: FixedTimeDraft;
  onTriggerTypeChange: (value: ScheduledTriggerType) => void;
}) {
  return (
    <SectionBlock
      title="执行模式"
      description="选择自动化任务什么时候启动。"
      icon={Timer}
    >
      <div className="grid gap-2 sm:grid-cols-3">
        {TRIGGER_TYPE_OPTIONS.map((option) => (
          <ChoiceButton
            key={option.value}
            value={option.value}
            selected={draft.triggerType === option.value}
            label={option.label}
            description={option.description}
            icon={option.icon}
            onSelect={onTriggerTypeChange}
          />
        ))}
      </div>
      <TriggerTimeControl
        draft={draft}
        setDraft={setDraft}
        intervalDraft={intervalDraft}
        fixedTimeDraft={fixedTimeDraft}
      />
      {shouldShowFirstRunPolicy(draft) ? (
        <FirstRunPolicyControl draft={draft} setDraft={setDraft} />
      ) : null}
    </SectionBlock>
  );
}

function TriggerTimeControl({
  draft,
  setDraft,
  intervalDraft,
  fixedTimeDraft,
}: {
  draft: AutoTaskDraft;
  setDraft: SetAutoTaskDraft;
  intervalDraft: IntervalDraft;
  fixedTimeDraft: FixedTimeDraft;
}) {
  if (draft.triggerType === "interval") {
    return (
      <div className="space-y-2">
        <Label htmlFor="auto-task-interval-amount">执行间隔</Label>
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_150px]">
          <Input
            id="auto-task-interval-amount"
            type="number"
            min={intervalDraft.unit === "second" ? MIN_INTERVAL_SECONDS : 1}
            step={1}
            value={intervalDraft.amount}
            onChange={(e) =>
              setDraft((prev) => ({
                ...prev,
                triggerValue: buildIntervalScheduleValue(
                  e.target.value,
                  intervalDraft.unit,
                ),
              }))
            }
            placeholder="1"
          />
          <Select
            value={intervalDraft.unit}
            onValueChange={(value) =>
              setDraft((prev) => ({
                ...prev,
                triggerValue: buildIntervalScheduleValue(
                  intervalDraft.amount,
                  value as typeof intervalDraft.unit,
                ),
              }))
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="minute">分钟</SelectItem>
              <SelectItem value="hour">小时</SelectItem>
              <SelectItem value="day">天</SelectItem>
              <SelectItem value="second">秒</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="text-[12px] leading-5 text-muted-foreground">
          秒级触发最短支持 {MIN_INTERVAL_SECONDS} 秒。
        </div>
      </div>
    );
  }

  if (draft.triggerType === "cron") {
    return (
      <div className="space-y-2">
        <Label htmlFor="auto-task-fixed-time">固定时间</Label>
        <div className="grid gap-3 md:grid-cols-[170px_minmax(0,1fr)]">
          <Select
            value={fixedTimeDraft.mode}
            onValueChange={(value) =>
              setDraft((prev) => ({
                ...prev,
                triggerValue: buildFixedTimeScheduleValue(
                  value as typeof fixedTimeDraft.mode,
                  fixedTimeDraft.time,
                  fixedTimeDraft.weekday,
                ),
              }))
            }
          >
            <SelectTrigger id="auto-task-fixed-time">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="daily">每天</SelectItem>
              <SelectItem value="weekday">工作日</SelectItem>
              <SelectItem value="weekly">每周</SelectItem>
            </SelectContent>
          </Select>
          <div
            className={cn(
              "grid gap-3",
              fixedTimeDraft.mode === "weekly"
                ? "md:grid-cols-[140px_minmax(0,1fr)]"
                : "md:grid-cols-[minmax(0,1fr)]",
            )}
          >
            {fixedTimeDraft.mode === "weekly" ? (
              <Select
                value={fixedTimeDraft.weekday}
                onValueChange={(value) =>
                  setDraft((prev) => ({
                    ...prev,
                    triggerValue: buildFixedTimeScheduleValue(
                      "weekly",
                      fixedTimeDraft.time,
                      value,
                    ),
                  }))
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">周一</SelectItem>
                  <SelectItem value="2">周二</SelectItem>
                  <SelectItem value="3">周三</SelectItem>
                  <SelectItem value="4">周四</SelectItem>
                  <SelectItem value="5">周五</SelectItem>
                  <SelectItem value="6">周六</SelectItem>
                  <SelectItem value="0">周日</SelectItem>
                </SelectContent>
              </Select>
            ) : null}
            <Input
              type="time"
              value={fixedTimeDraft.time}
              onChange={(e) =>
                setDraft((prev) => ({
                  ...prev,
                  triggerValue: buildFixedTimeScheduleValue(
                    fixedTimeDraft.mode,
                    e.target.value,
                    fixedTimeDraft.weekday,
                  ),
                }))
              }
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <Label htmlFor="auto-task-once-time">执行时间</Label>
      <Input
        id="auto-task-once-time"
        type="datetime-local"
        value={draft.triggerValue}
        onChange={(e) =>
          setDraft((prev) => ({
            ...prev,
            triggerValue: e.target.value,
          }))
        }
      />
      <div className="text-[12px] leading-5 text-muted-foreground">
        默认使用当前时间，保存启用后会尽快运行；也可以指定未来时间。
      </div>
    </div>
  );
}

function FirstRunPolicyControl({
  draft,
  setDraft,
}: {
  draft: AutoTaskDraft;
  setDraft: SetAutoTaskDraft;
}) {
  return (
    <div className="space-y-2">
      <Label>首次执行</Label>
      <div className="grid gap-2 sm:grid-cols-2">
        <ChoiceButton
          value="next_scheduled"
          selected={draft.firstRunPolicy === "next_scheduled"}
          label="等待计划时间"
          description="保存后等到下一次间隔或固定时间再运行"
          icon={Timer}
          onSelect={(value) =>
            setDraft((prev) => ({ ...prev, firstRunPolicy: value }))
          }
        />
        <ChoiceButton
          value="immediate"
          selected={draft.firstRunPolicy === "immediate"}
          label="立即执行一轮"
          description="保存并启用后先运行一次，之后继续按时间规则运行"
          icon={PlayCircle}
          onSelect={(value) =>
            setDraft((prev) => ({ ...prev, firstRunPolicy: value }))
          }
        />
      </div>
    </div>
  );
}

export function SessionStrategySection({
  draft,
  setDraft,
  sessionOptions,
  onSessionStrategyChange,
}: {
  draft: AutoTaskDraft;
  setDraft: SetAutoTaskDraft;
  sessionOptions: AutoTaskSessionOption[];
  onSessionStrategyChange: (value: AutoTaskDraft["sessionStrategy"]) => void;
}) {
  return (
    <SectionBlock
      title="会话策略"
      description="决定触发后进入哪条会话，以及上轮未结束时怎么处理。"
      icon={GitBranch}
    >
      <div className="grid gap-3 md:grid-cols-2">
        {SESSION_STRATEGY_OPTIONS.map((option) => (
          <ChoiceButton
            key={option.value}
            value={option.value}
            selected={draft.sessionStrategy === option.value}
            label={option.label}
            description={option.description}
            icon={option.icon}
            onSelect={onSessionStrategyChange}
          />
        ))}
      </div>

      {draft.sessionStrategy === "bind_session" ? (
        <SessionSelectControl
          id="auto-task-bind-session"
          label="绑定会话"
          draft={draft}
          setDraft={setDraft}
          sessionOptions={sessionOptions}
        />
      ) : null}

      <div className="space-y-2">
        <Label>上次未结束时</Label>
        <div className="grid gap-2 sm:grid-cols-3">
          {OVERLAP_POLICY_OPTIONS.map((option) => {
            const disabled =
              draft.sessionStrategy === "bind_session" &&
              option.value === "parallel";
            return (
              <ChoiceButton
                key={option.value}
                value={option.value}
                selected={
                  draft.sessionStrategy === "bind_session" &&
                  draft.overlapPolicy === "parallel"
                    ? option.value === "skip"
                    : draft.overlapPolicy === option.value
                }
                label={option.label}
                description={option.description}
                disabled={disabled}
                onSelect={(value) =>
                  setDraft((prev) => ({
                    ...prev,
                    overlapPolicy: value,
                  }))
                }
              />
            );
          })}
        </div>
      </div>
    </SectionBlock>
  );
}

function SessionSelectControl({
  id,
  label,
  draft,
  setDraft,
  sessionOptions,
}: {
  id: string;
  label: string;
  draft: AutoTaskDraft;
  setDraft: SetAutoTaskDraft;
  sessionOptions: AutoTaskSessionOption[];
}) {
  const selectedSessionId = draft.bindSessionId.trim();
  const selectedOption = sessionOptions.find(
    (option) => option.sessionId === selectedSessionId,
  );
  const fallbackSelectedOption: AutoTaskSessionOption | null =
    selectedSessionId && !selectedOption
      ? ({
          sessionId: selectedSessionId,
          title: getSessionOptionLabel([], selectedSessionId),
        })
      : null;
  const selectableOptions = fallbackSelectedOption
    ? [fallbackSelectedOption, ...sessionOptions]
    : sessionOptions;
  const currentOption = selectableOptions.find((option) => option.isCurrent);
  const hasOptions = selectableOptions.length > 0;

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Select
        value={selectedSessionId || currentOption?.sessionId || undefined}
        onValueChange={(value) =>
          setDraft((prev) => ({
            ...prev,
            bindSessionId: value,
            sessionStrategy: "bind_session",
            overlapPolicy: prev.overlapPolicy === "parallel" ? "skip" : prev.overlapPolicy,
          }))
        }
        disabled={!hasOptions}
      >
        <SelectTrigger id={id}>
          <SelectValue placeholder="选择要继续的会话" />
        </SelectTrigger>
        <SelectContent className="max-h-72">
          {selectableOptions.map((option) => (
            <SelectItem key={option.sessionId} value={option.sessionId}>
              {formatSessionOptionLabel(option)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <div className="text-[12px] leading-5 text-muted-foreground">
        {hasOptions
          ? selectedOption?.isCurrent || (!selectedSessionId && currentOption)
            ? "默认使用当前会话，后续会在同一条上下文里继续推进。"
            : "绑定后会回到所选会话继续推进。"
          : "当前入口没有可选择会话，请先在工作区中打开一条会话。"}
      </div>
    </div>
  );
}

export function ContinuousRunSection({
  draft,
  setDraft,
  sessionOptions,
}: {
  draft: AutoTaskDraft;
  setDraft: SetAutoTaskDraft;
  sessionOptions: AutoTaskSessionOption[];
}) {
  return (
    <SectionBlock
      title="连续推进"
      description="设置续推提示词、目标会话和停止条件。"
      icon={InfinityIcon}
    >
      <div className="space-y-2">
        <Label htmlFor="auto-task-continuation-prompt">续推提示词</Label>
        <Textarea
          id="auto-task-continuation-prompt"
          value={draft.continuationPrompt}
          onChange={(e) =>
            setDraft((prev) => ({
              ...prev,
              continuationPrompt: e.target.value,
            }))
          }
          placeholder="留空则使用默认续推提示词"
          className="min-h-[108px] resize-y leading-6"
        />
      </div>

      <SessionSelectControl
        id="auto-task-continuous-bind-session"
        label="推进会话"
        draft={draft}
        setDraft={setDraft}
        sessionOptions={sessionOptions}
      />

      <div className="space-y-2">
        <Label>结束策略</Label>
        <div className="grid gap-2 sm:grid-cols-2">
          <ChoiceButton
            value="forever"
            selected={draft.maxContinuations < 0}
            label="永久运行"
            description="不设置轮次上限，可由 AI 完成信号或用户暂停结束"
            onSelect={() =>
              setDraft((prev) => ({
                ...prev,
                maxContinuations: -1,
              }))
            }
          />
          <ChoiceButton
            value="conditional"
            selected={draft.maxContinuations >= 0}
            label="条件停止"
            description="达到轮次、完成信号或错误阈值后停止"
            onSelect={() =>
              setDraft((prev) => ({
                ...prev,
                maxContinuations: prev.maxContinuations > 0 ? prev.maxContinuations : 10,
                stopOnSignal: true,
              }))
            }
          />
        </div>
      </div>

      <div className="grid gap-3">
        <ToggleRow
          title="允许 AI 自主结束任务"
          description="Agent 标记完成时停止连续推进"
          checked={draft.stopOnSignal}
          onCheckedChange={(checked) =>
            setDraft((prev) => ({
              ...prev,
              stopOnSignal: checked,
            }))
          }
        />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="auto-task-max-continuations">最大续推次数</Label>
          <Input
            id="auto-task-max-continuations"
            type="number"
            min={-1}
            step={1}
            value={draft.maxContinuations}
            onChange={(e) =>
              setDraft((prev) => ({
                ...prev,
                maxContinuations:
                  e.target.value === "" ? -1 : Number(e.target.value),
              }))
            }
          />
          <div className="text-[12px] leading-5 text-muted-foreground">
            -1 表示不限制轮次。
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="auto-task-stop-errors">连续错误阈值</Label>
          <Input
            id="auto-task-stop-errors"
            type="number"
            min={1}
            step={1}
            value={draft.stopOnConsecutiveErrors}
            onChange={(e) =>
              setDraft((prev) => ({
                ...prev,
                stopOnConsecutiveErrors:
                  e.target.value === "" ? 10 : Number(e.target.value),
              }))
            }
          />
          <div className="text-[12px] leading-5 text-muted-foreground">
            达到阈值后自动禁用任务。
          </div>
        </div>
      </div>
    </SectionBlock>
  );
}

export function RunSettingsSection({
  draft,
  setDraft,
  modelSelectValue,
  selectedModelId,
  selectedModel,
  chatModels,
}: {
  draft: AutoTaskDraft;
  setDraft: SetAutoTaskDraft;
  modelSelectValue: string;
  selectedModelId: string;
  selectedModel: LLMModelConfig | null | undefined;
  chatModels: LLMModelConfig[];
}) {
  return (
    <SectionBlock
      title="运行设置"
      description="选择模型，并决定保存后是否启用任务。"
      icon={Settings2}
    >
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px]">
        <div className="space-y-2">
          <Label htmlFor="auto-task-model">触发模型</Label>
          <Select
            value={modelSelectValue}
            onValueChange={(value) =>
              setDraft((prev) => ({
                ...prev,
                modelId: value === DEFAULT_AUTO_TASK_MODEL_VALUE ? "" : value,
              }))
            }
          >
            <SelectTrigger id="auto-task-model">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={DEFAULT_AUTO_TASK_MODEL_VALUE}>
                跟随任务默认模型
              </SelectItem>
              {selectedModelId && !selectedModel ? (
                <SelectItem value={selectedModelId}>
                  当前配置：{selectedModelId}
                </SelectItem>
              ) : null}
              {chatModels.length > 0 ? (
                chatModels.map((model) => (
                  <SelectItem key={model.id} value={model.id}>
                    {model.name}
                  </SelectItem>
                ))
              ) : (
                <SelectItem value={NO_AUTO_TASK_MODEL_VALUE} disabled>
                  暂无已启用聊天模型
                </SelectItem>
              )}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="auto-task-enabled">启用状态</Label>
          <div className="flex h-10 items-center justify-between rounded-xl border border-border bg-muted/15 px-3">
            <div className="text-sm text-foreground">
              {draft.enabled ? "保存后启用" : "保存为暂停"}
            </div>
            <Switch
              id="auto-task-enabled"
              checked={draft.enabled}
              onCheckedChange={(checked) =>
                setDraft((prev) => ({
                  ...prev,
                  enabled: checked,
                }))
              }
            />
          </div>
        </div>
      </div>
    </SectionBlock>
  );
}
