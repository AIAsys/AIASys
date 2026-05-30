import {
  formatConversationRoleLabel,
  formatExecutionDuration,
  formatExecutionEnvLabel,
  formatExecutionFullTime,
  formatExecutionSandboxLabel,
  formatExecutionShortTime,
  formatExecutionStatusLabel,
  getConversationRoleBadgeClass,
  getConversationTextContent,
} from "./formatters";
import {
  getExecutionRiskBadgeClass,
  getExecutionRiskLabel,
  getExecutionRiskTagLabel,
} from "../../executionRecordRisk";
import type { SessionExecutionRecord, SessionHistoryMessage } from "../../types";

export function ExecutionRecordRows({
  records,
  highlightedExecutionSequence,
}: {
  records: SessionExecutionRecord[];
  highlightedExecutionSequence: number | null;
}) {
  return (
    <div className="divide-y divide-border/60">
      {records.map((record) => {
        const durationLabel = formatExecutionDuration(record.started_at, record.finished_at);
        const hasDetailMetadata =
          Boolean(record.record_id) ||
          Boolean(record.runtime?.sandbox_mode) ||
          Boolean(record.runtime?.env_id);

        return (
          <div
            key={record.record_id}
            className={`px-4 py-3 ${
              highlightedExecutionSequence === record.sequence
                ? "bg-muted/60 ring-1 ring-border"
                : ""
            }`}
            data-testid={`execution-record-row-${record.sequence}`}
            data-highlighted={
              highlightedExecutionSequence === record.sequence ? "true" : "false"
            }
          >
            <div className="flex flex-wrap items-start justify-between gap-2 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-foreground">执行 #{record.sequence}</span>
                <span className="rounded bg-muted px-2 py-0.5">
                  {formatExecutionStatusLabel(record.status)}
                </span>
                <span
                  className={`rounded border px-2 py-0.5 ${getExecutionRiskBadgeClass(record)}`}
                >
                  {getExecutionRiskLabel(record)}
                </span>
              </div>
              <span className="rounded border border-border/60 bg-background px-2 py-0.5 text-[10px] text-muted-foreground">
                {formatExecutionShortTime(record.finished_at || record.started_at)}
              </span>
            </div>
            <div className="mt-2 text-xs text-muted-foreground">
              {formatExecutionFullTime(record.started_at)} {"->"}{" "}
              {formatExecutionFullTime(record.finished_at)}
              {durationLabel ? ` · ${durationLabel}` : ""}
            </div>
            <pre className="mt-3 overflow-x-auto rounded-md bg-muted/50 p-3 text-xs leading-5 text-foreground">
              <code>{record.code}</code>
            </pre>
            {record.result_preview?.text ? (
              <div className="mt-2 rounded-md border border-border/60 bg-background px-3 py-2 text-sm">
                {record.result_preview.text}
              </div>
            ) : null}
            {record.replay_risk?.tags?.length ? (
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                {record.replay_risk.tags.map((tag) => (
                  <span
                    key={`${record.record_id}-${tag}`}
                    className="rounded border border-border/60 bg-muted/30 px-2 py-1"
                  >
                    {getExecutionRiskTagLabel(tag)}
                  </span>
                ))}
              </div>
            ) : null}
            {record.replay_risk?.reasons?.length ? (
              <div className="mt-2 text-xs text-muted-foreground">
                副作用风险提示: {record.replay_risk.reasons.join("；")}
              </div>
            ) : null}
            {record.error ? (
              <div className="mt-2 text-sm text-foreground">错误: {record.error}</div>
            ) : null}
            {hasDetailMetadata ? (
              <details className="mt-3 rounded-md border border-border/60 bg-background/70 px-3 py-2">
                <summary className="cursor-pointer text-xs text-muted-foreground">
                  执行环境与记录细节
                </summary>
                <div className="mt-2 grid gap-1 text-xs text-muted-foreground">
                  <div>记录标识: {record.record_id}</div>
                  <div>执行方式: {formatExecutionSandboxLabel(record.runtime?.sandbox_mode)}</div>
                  <div>执行环境: {formatExecutionEnvLabel(record.runtime?.env_id)}</div>
                </div>
              </details>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

export function ConversationHistoryRows({
  messages,
}: {
  messages: SessionHistoryMessage[];
}) {
  return (
    <div className="divide-y divide-border/60">
      {messages.map((message, index) => {
        const displayText = getConversationTextContent(
          message.display_content ?? message.content,
        );
        const toolCalls = message.tool_calls || [];
        const timestampLabel = formatExecutionShortTime(message.timestamp);
        const hasTimestamp = Boolean(message.timestamp);

        return (
          <div key={`${message.id || message.role}-${index}`} className="px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`rounded border px-2 py-0.5 ${getConversationRoleBadgeClass(message.role)}`}
                >
                  {formatConversationRoleLabel(message.role)}
                </span>
                {toolCalls.length > 0 ? (
                  <span className="rounded border border-border/60 bg-background px-2 py-0.5 text-muted-foreground">
                    工具调用 {toolCalls.length} 次
                  </span>
                ) : null}
              </div>
              {hasTimestamp ? (
                <span className="rounded border border-border/60 bg-background px-2 py-0.5 text-[10px] text-muted-foreground">
                  {timestampLabel}
                </span>
              ) : null}
            </div>

            {displayText ? (
              <div className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-foreground">
                {displayText}
              </div>
            ) : (
              <div className="mt-2 text-sm text-muted-foreground">
                当前消息没有可直接展示的文本内容。
              </div>
            )}

            {toolCalls.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                {toolCalls.map((toolCall) => (
                  <span
                    key={toolCall.id}
                    className="rounded border border-border/60 bg-muted/30 px-2 py-1 text-muted-foreground"
                  >
                    {toolCall.function?.name || "unknown"}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
