/**
 * SetupChecklist — 首次使用快速设置清单
 *
 * 在空工作区首页展示 3 步设置清单，引导新用户完成基本配置。
 * 所有步骤完成后清单自动隐藏。
 */
import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Server,
  Terminal,
  FolderKanban,
  ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiRequest } from "@/lib/api/httpClient";
import { API_ENDPOINTS } from "@/config/api";
import { getModels } from "@/lib/api/llm";
import { cn } from "@/lib/utils";

type StepStatus = "loading" | "ok" | "warning";

interface Step {
  id: string;
  label: string;
  icon: typeof Server;
  status: StepStatus;
  detail: string;
  actionLabel: string;
  actionSection: string;
}

function dispatchOpenSettings(section: string) {
  window.dispatchEvent(
    new CustomEvent("aiasys:open-global-settings", { detail: section }),
  );
}

export function SetupChecklist({
  onCreateWorkspace,
}: {
  onCreateWorkspace: () => void;
}) {
  const [steps, setSteps] = useState<Step[]>([
    {
      id: "model",
      label: "配置 AI 模型",
      icon: Server,
      status: "loading",
      detail: "检查中...",
      actionLabel: "去配置",
      actionSection: "llm",
    },
    {
      id: "shell",
      label: "检查 Shell 环境",
      icon: Terminal,
      status: "loading",
      detail: "检查中...",
      actionLabel: "去检查",
      actionSection: "shell-environment",
    },
    {
      id: "workspace",
      label: "创建第一个工作区",
      icon: FolderKanban,
      status: "warning",
      detail: "还没有工作区",
      actionLabel: "去创建",
      actionSection: "",
    },
  ]);

  const runChecks = useCallback(async () => {
    // Check 1: Model config
    try {
      const res = await getModels(true);
      const chatModels = res.models.filter(
        (m) => m.enabled !== false && (m.model_type ?? "chat") === "chat",
      );
      setSteps((prev) =>
        prev.map((s) =>
          s.id === "model"
            ? chatModels.length > 0
              ? { ...s, status: "ok", detail: `${chatModels.length} 个可用模型` }
              : { ...s, status: "warning", detail: "未配置可用模型" }
            : s,
        ),
      );
    } catch {
      setSteps((prev) =>
        prev.map((s) =>
          s.id === "model" ? { ...s, status: "warning", detail: "无法检查" } : s,
        ),
      );
    }

    // Check 2: Shell environment
    try {
      const res = await apiRequest<{
        recommended_family: string;
        is_windows: boolean;
      }>(API_ENDPOINTS.SHELL_ENVIRONMENT);
      const family = res.recommended_family;
      if (res.is_windows && (family === "powershell" || family === "cmd")) {
        setSteps((prev) =>
          prev.map((s) =>
            s.id === "shell"
              ? {
                  ...s,
                  status: "warning",
                  detail: `当前为 ${family}，建议增强`,
                }
              : s,
          ),
        );
      } else {
        setSteps((prev) =>
          prev.map((s) =>
            s.id === "shell"
              ? { ...s, status: "ok", detail: `推荐: ${family}` }
              : s,
          ),
        );
      }
    } catch {
      setSteps((prev) =>
        prev.map((s) =>
          s.id === "shell" ? { ...s, status: "ok", detail: "已就绪" } : s,
        ),
      );
    }
  }, []);

  useEffect(() => {
    void runChecks();
  }, [runChecks]);

  const allOk = steps.every((s) => s.status === "ok");
  if (allOk) return null;

  const completedCount = steps.filter((s) => s.status === "ok").length;

  return (
    <section className="rounded-2xl border border-border bg-card p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-foreground">
            快速设置（{completedCount}/{steps.length}）
          </div>
          <div className="mt-0.5 text-xs text-muted-foreground">
            完成以下设置后再开始使用 AIASys
          </div>
        </div>
      </div>

      <div className="space-y-2">
        {steps.map((step, index) => {
          const Icon = step.icon;
          return (
            <div
              key={step.id}
              className={cn(
                "flex items-center gap-3 rounded-xl border px-4 py-3 transition-colors",
                step.status === "ok"
                  ? "border-success/20 bg-success-container/30"
                  : step.status === "warning"
                    ? "border-warning/20 bg-warning-container/20"
                    : "border-border bg-background",
              )}
            >
              <div className="flex items-center gap-2.5">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-[11px] font-semibold text-muted-foreground">
                  {index + 1}
                </span>
                <Icon className="h-4 w-4 text-muted-foreground" />
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-foreground">
                    {step.label}
                  </span>
                  {step.status === "loading" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                  ) : step.status === "ok" ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                  ) : (
                    <AlertTriangle className="h-3.5 w-3.5 text-warning" />
                  )}
                </div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  {step.detail}
                </div>
              </div>

              {step.status !== "ok" ? (
                <Button
                  type="button"
                  size="sm"
                  variant={step.status === "warning" ? "default" : "outline"}
                  onClick={() => {
                    if (step.id === "workspace") {
                      onCreateWorkspace();
                    } else {
                      dispatchOpenSettings(step.actionSection);
                    }
                  }}
                >
                  {step.actionLabel}
                  <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
                </Button>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}
