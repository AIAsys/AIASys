/**
 * Capability Confirmation 内联卡片
 *
 * 在聊天流中展示运行时能力确认请求（工具审批）。
 * 支持：允许 / 本会话允许 / 拒绝 / 拒绝并附反馈
 * 增强：危险命令红色标记、命令预览高亮、pattern 类型展示
 */

import React, { useState, useCallback, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AlertCircle, Loader2, CheckCircle2, XCircle, Bot, ShieldAlert } from "lucide-react";

interface CapabilityConfirmationCardProps {
  tool_name: string;
  arguments: Record<string, unknown>;
  prompt: string;
  subagent_name?: string;
  pattern_key?: string;
  status: "pending" | "approved" | "rejected" | "timeout";
  onApprove: (scope: "once" | "session") => Promise<boolean>;
  onReject: (feedback: string) => Promise<boolean>;
}

// 危险 pattern 关键词：命中时显示红色警告
const DANGEROUS_PATTERN_KEYS = ["hardline", "credential_exfil", "critical"];

// Pattern key 中文描述映射
const PATTERN_LABELS: Record<string, string> = {
  shell_hardline: "破坏性命令（不可绕过）",
  shell_credential_exfil: "凭证外传风险",
  shell_command: "Shell 命令执行",
  shell_safe: "低风险 Shell 命令",
  global_write: "全局工作区写入",
  workspace_write: "工作区文件写入",
  skill_enable_global: "全局 Skill 启用",
  skill_enable_workspace: "工作区 Skill 启用",
  skill_disable: "Skill 禁用",
  mcp_install: "MCP 服务器安装",
  env_var: "环境变量变更",
  auto_task: "自动化任务操作",
  runtime_env_modify: "运行时环境变更",
  runtime_env_read: "运行时环境查看",
  subagent_create: "子 Agent 创建",
  critical_tool: "极高风险操作",
};

function isDangerousPattern(patternKey?: string): boolean {
  if (!patternKey) return false;
  return DANGEROUS_PATTERN_KEYS.some((k) => patternKey.includes(k));
}

function getPatternLabel(patternKey?: string): string | undefined {
  if (!patternKey) return undefined;
  return PATTERN_LABELS[patternKey] || patternKey;
}

function renderCommandPreview(toolName: string, args: Record<string, unknown>): string | null {
  if (toolName === "Shell") {
    const cmd = args.command;
    if (typeof cmd === "string" && cmd) return cmd;
  }
  if (toolName === "WriteFile" || toolName === "StrReplaceFile" || toolName === "CreateFile") {
    const path = args.path;
    if (typeof path === "string" && path) return path;
  }
  return null;
}

export const CapabilityConfirmationCard: React.FC<CapabilityConfirmationCardProps> = ({
  tool_name,
  arguments: toolArgs,
  prompt,
  subagent_name,
  pattern_key,
  status,
  onApprove,
  onReject,
}) => {
  const [feedback, setFeedback] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const isTerminal = status !== "pending";
  const isDangerous = useMemo(() => isDangerousPattern(pattern_key), [pattern_key]);
  const patternLabel = useMemo(() => getPatternLabel(pattern_key), [pattern_key]);
  const commandPreview = useMemo(() => renderCommandPreview(tool_name, toolArgs), [tool_name, toolArgs]);

  const handleApprove = useCallback(
    async (scope: "once" | "session") => {
      if (isTerminal || isSubmitting) return;
      setIsSubmitting(true);
      setErrorMessage(null);
      try {
        const success = await onApprove(scope);
        if (!success) {
          setErrorMessage("提交失败，请重试");
        }
      } catch (_e) {
        setErrorMessage("提交异常，请重试");
      } finally {
        setIsSubmitting(false);
      }
    },
    [isTerminal, isSubmitting, onApprove],
  );

  const handleReject = useCallback(async () => {
    if (isTerminal || isSubmitting) return;
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      const success = await onReject(feedback);
      if (!success) {
        setErrorMessage("提交失败，请重试");
      }
    } catch (_e) {
      setErrorMessage("提交异常，请重试");
    } finally {
      setIsSubmitting(false);
    }
  }, [isTerminal, isSubmitting, onReject, feedback]);

  const renderStatus = () => {
    if (status === "approved") {
      return (
        <div className="flex items-center gap-2 py-2">
          <CheckCircle2 className="h-4 w-4 text-green-600" />
          <span className="text-sm text-green-600">已批准</span>
        </div>
      );
    }
    if (status === "timeout") {
      return (
        <div className="flex items-center gap-2 py-2 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" />
          请求已超时
        </div>
      );
    }
    if (status === "rejected") {
      return (
        <div className="flex items-center gap-2 py-2">
          <XCircle className="h-4 w-4 text-amber-600" />
          <span className="text-sm text-amber-600">已拒绝</span>
        </div>
      );
    }
    return null;
  };

  // 参数摘要（非命令预览的其他参数）
  const argsSummary = useMemo(() => {
    const entries = Object.entries(toolArgs);
    if (tool_name === "Shell" && entries.length === 1 && entries[0][0] === "command") {
      return "";
    }
    return entries
      .map(([k, v]) => `${k}: ${JSON.stringify(v).slice(0, 200)}`)
      .join("\n");
  }, [toolArgs, tool_name]);

  const borderColor = isDangerous ? "border-red-300" : "border-amber-200";
  const bgColor = isDangerous ? "bg-red-50/50" : "bg-amber-50/50";
  const iconColor = isDangerous ? "text-red-600" : "text-amber-600";

  return (
    <div className={`rounded-xl border ${borderColor} ${bgColor} p-4 space-y-3 my-2`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isDangerous ? (
            <ShieldAlert className={`h-4 w-4 ${iconColor}`} />
          ) : (
            <AlertCircle className={`h-4 w-4 ${iconColor}`} />
          )}
          <h4 className="text-sm font-semibold">
            {subagent_name ? (
              <span className="flex items-center gap-1">
                <Bot className="h-3 w-3" />
                {subagent_name} 请求执行
              </span>
            ) : (
              "请求确认"
            )}
          </h4>
        </div>
        {renderStatus()}
      </div>

      {/* Pattern 类型标签 */}
      {patternLabel && (
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${
              isDangerous
                ? "bg-red-100 text-red-700"
                : "bg-amber-100 text-amber-700"
            }`}
          >
            {patternLabel}
          </span>
        </div>
      )}

      <div className="text-sm text-foreground/80">
        <span className="font-medium">{tool_name}</span>
        {prompt ? ` — ${prompt}` : null}
      </div>

      {/* 命令/路径预览 */}
      {commandPreview && (
        <div className="rounded-md bg-muted/60 p-2">
          <div className="text-xs text-muted-foreground mb-1">
            {tool_name === "Shell" ? "命令预览" : "目标路径"}
          </div>
          <pre className="text-xs overflow-x-auto whitespace-pre-wrap break-all">
            <code>{commandPreview}</code>
          </pre>
        </div>
      )}

      {/* 其他参数摘要 */}
      {argsSummary && (
        <pre className="text-xs bg-muted/50 rounded-md p-2 overflow-x-auto max-h-32">
          <code>{argsSummary}</code>
        </pre>
      )}

      {errorMessage && (
        <div className="flex items-center gap-2 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" />
          {errorMessage}
        </div>
      )}

      {status === "pending" && (
        <>
          <Input
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="拒绝时可填写反馈（可选）"
            className="w-full text-sm"
            onKeyDown={(e) => {
              if (e.key === "Enter" && e.ctrlKey) {
                handleReject();
              }
            }}
          />
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="outline" size="sm" onClick={handleReject} disabled={isSubmitting}>
              {isSubmitting ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
              拒绝
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleApprove("once")}
              disabled={isSubmitting}
            >
              允许
            </Button>
            <Button size="sm" onClick={() => handleApprove("session")} disabled={isSubmitting}>
              {isSubmitting ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
              本会话允许
            </Button>
          </div>
        </>
      )}
    </div>
  );
};
