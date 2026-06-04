import { Bot, CircleAlert, FileText, Loader2, MessageSquare, Terminal } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { SubAgentDetail } from "@/hooks/useExecutionTree";
import { cn } from "@/lib/utils";

interface AgentExecutionViewProps {
  subagent: SubAgentDetail | null;
  isLoading?: boolean;
  className?: string;
}

function formatRole(role?: string | null) {
  switch (role) {
    case "user":
      return "用户";
    case "assistant":
      return "专家";
    case "tool":
      return "工具";
    default:
      return role || "消息";
  }
}

function toDisplayText(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "空";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value, null, 2);
}

export function AgentExecutionView({
  subagent,
  isLoading = false,
  className,
}: AgentExecutionViewProps) {
  if (isLoading) {
    return (
      <section className={cn("rounded-2xl border border-border bg-background px-4 py-4", className)}>
        <div className="flex min-h-48 items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在读取节点详情...
        </div>
      </section>
    );
  }

  if (!subagent) {
    return (
      <section className={cn("rounded-2xl border border-border bg-background px-4 py-4", className)}>
        <div className="flex min-h-48 items-center justify-center px-4 text-center">
          <div>
            <Bot className="mx-auto h-5 w-5 text-muted-foreground" />
            <div className="mt-3 text-sm font-medium text-foreground">
              选择一个协作节点
            </div>
            <div className="mt-2 text-xs leading-5 text-muted-foreground">
              点击左侧节点后，这里会显示该节点的对话记录、工具调用和产出摘要。
            </div>
          </div>
        </div>
      </section>
    );
  }

  const toolEvents = subagent.events.filter((event) =>
    ["tool_call", "tool_result"].includes(String(event.type || "")),
  );

  return (
    <section className={cn("rounded-2xl border border-border bg-background px-4 py-4", className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Bot className="h-4 w-4 text-tertiary" />
            <span className="truncate">{subagent.nickname || subagent.name}</span>
          </div>
          <div className="mt-1 text-xs leading-5 text-muted-foreground">
            {subagent.subagent_type || "协作节点"}
          </div>
        </div>
        <Badge variant="outline" className="shrink-0 rounded-full text-[11px]">
          {subagent.status}
        </Badge>
      </div>

      <div className="mt-4 grid gap-2 text-xs">
        <div className="rounded-xl border border-border bg-muted/20 px-3 py-2">
          <div className="text-[11px] text-muted-foreground">节点路径</div>
          <div className="mt-1 break-all font-mono text-foreground">
            {subagent.agent_path || (subagent.meta.agent_path as string | undefined) || subagent.id}
          </div>
        </div>
        <div className="rounded-xl border border-border bg-muted/20 px-3 py-2">
          <div className="text-[11px] text-muted-foreground">父级</div>
          <div className="mt-1 break-all font-mono text-foreground">
            {subagent.parent_agent_id || (subagent.meta.parent_agent_id as string | undefined) || "主控"}
          </div>
        </div>
      </div>

      <div className="mt-4">
        <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
          <MessageSquare className="h-3.5 w-3.5 text-muted-foreground" />
          对话记录
        </div>
        <div className="mt-2 max-h-72 space-y-2 overflow-y-auto pr-1">
          {subagent.context.length > 0 ? (
            subagent.context.map((message: unknown, index) => {
              const msg = message as Record<string, unknown>;
              return (
                <div
                  key={`${(msg.role as string | undefined) ?? "msg"}-${index}-${String((msg.content as string | undefined) ?? "").slice(0, 16)}`}
                  className="rounded-xl border border-border bg-muted/20 px-3 py-2"
                >
                  <div className="text-[11px] font-medium text-muted-foreground">
                    {formatRole(msg.role as string | undefined)}
                  </div>
                  <pre className="mt-1 whitespace-pre-wrap break-words font-sans text-xs leading-5 text-foreground">
                    {toDisplayText(msg.content || msg.tool_calls || msg)}
                  </pre>
                </div>
              );
            })
          ) : (
            <div className="rounded-xl border border-dashed border-border bg-muted/10 px-3 py-4 text-center text-xs text-muted-foreground">
              暂无可读取的对话记录
            </div>
          )}
        </div>
      </div>

      <div className="mt-4">
        <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
          <Terminal className="h-3.5 w-3.5 text-muted-foreground" />
          工具调用
        </div>
        <div className="mt-2 max-h-56 space-y-2 overflow-y-auto pr-1">
          {toolEvents.length > 0 ? (
            toolEvents.map((event, index) => (
              <div
                key={`${event.type}:${event.tool_call_id || index}`}
                className="rounded-xl border border-border bg-muted/20 px-3 py-2"
              >
                <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                  <span>{event.type === "tool_call" ? "调用" : "结果"}</span>
                  <span className="font-mono">{(event.tool_name as string | undefined) || (event.tool_call_id as string | undefined) || "unknown"}</span>
                </div>
                <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-foreground">
                  {toDisplayText(event.arguments || event.content || event)}
                </pre>
              </div>
            ))
          ) : (
            <div className="rounded-xl border border-dashed border-border bg-muted/10 px-3 py-4 text-center text-xs text-muted-foreground">
              暂无工具调用记录
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-border bg-muted/20 px-3 py-2">
        <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
          <FileText className="h-3.5 w-3.5 text-muted-foreground" />
          产出文件
        </div>
        <div className="mt-2 space-y-1">
          {subagent.output_files.length > 0 ? (
            subagent.output_files.map((file) => (
              <div key={file.path} className="truncate font-mono text-[11px] text-muted-foreground">
                {file.name}
              </div>
            ))
          ) : (
            <div className="flex items-start gap-2 text-xs text-muted-foreground">
              <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              当前节点还没有可读取的产出文件。
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
