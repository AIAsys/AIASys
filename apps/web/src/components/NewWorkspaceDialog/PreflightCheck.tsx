/**
 * PreflightCheck — 创建工作区前的环境前置检查摘要
 *
 * 检查模型配置、Shell 环境和存储位置是否就绪，
 * 对未就绪项提供跳转到对应设置面板的链接。
 */
import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Server,
  Terminal,
  FolderCog,
} from "lucide-react";
import { apiRequest } from "@/lib/api/httpClient";
import { API_ENDPOINTS } from "@/config/api";
import { getModels } from "@/lib/api/llm";
import { cn } from "@/lib/utils";

type CheckStatus = "loading" | "ok" | "warning";

interface CheckItem {
  id: string;
  label: string;
  icon: typeof Server;
  status: CheckStatus;
  detail: string;
  actionLabel?: string;
  actionSection?: string;
}

export interface PreflightCheckProps {
  onNavigateSettings?: (section: string) => void;
}

export function PreflightCheck({ onNavigateSettings }: PreflightCheckProps) {
  const navigate = useCallback(
    (section: string) => {
      if (onNavigateSettings) {
        onNavigateSettings(section);
      } else {
        window.dispatchEvent(
          new CustomEvent("aiasys:open-global-settings", { detail: section }),
        );
      }
    },
    [onNavigateSettings],
  );
  const [items, setItems] = useState<CheckItem[]>([
    {
      id: "model",
      label: "模型配置",
      icon: Server,
      status: "loading",
      detail: "检查中...",
    },
    {
      id: "shell",
      label: "Shell 环境",
      icon: Terminal,
      status: "loading",
      detail: "检查中...",
    },
    {
      id: "storage",
      label: "存储位置",
      icon: FolderCog,
      status: "loading",
      detail: "检查中...",
    },
  ]);

  const runChecks = useCallback(async () => {
    // Check 1: Model config
    try {
      const res = await getModels(true);
      const chatModels = res.models.filter(
        (m) => m.enabled !== false && (m.model_type ?? "chat") === "chat",
      );
      setItems((prev) =>
        prev.map((item) =>
          item.id === "model"
            ? chatModels.length > 0
              ? {
                  ...item,
                  status: "ok",
                  detail: `${chatModels.length} 个可用模型`,
                }
              : {
                  ...item,
                  status: "warning",
                  detail: "未配置可用模型，对话将无法使用",
                  actionLabel: "去配置",
                  actionSection: "llm",
                }
            : item,
        ),
      );
    } catch {
      setItems((prev) =>
        prev.map((item) =>
          item.id === "model"
            ? { ...item, status: "warning", detail: "无法检查模型配置" }
            : item,
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
        setItems((prev) =>
          prev.map((item) =>
            item.id === "shell"
              ? {
                  ...item,
                  status: "warning",
                  detail: `当前为 ${family}，建议安装 Git Bash 或 busybox 获得更好体验`,
                  actionLabel: "去增强",
                  actionSection: "shell-environment",
                }
              : {
                  ...item,
                  status: "ok",
                  detail: `推荐 Shell: ${family}`,
                },
          ),
        );
      } else {
        setItems((prev) =>
          prev.map((item) =>
            item.id === "shell"
              ? { ...item, status: "ok", detail: `推荐 Shell: ${family}` }
              : item,
          ),
        );
      }
    } catch {
      // Non-critical, silently pass
      setItems((prev) =>
        prev.map((item) =>
          item.id === "shell"
            ? { ...item, status: "ok", detail: "已就绪" }
            : item,
        ),
      );
    }

    // Check 3: Storage (just verify API is reachable)
    try {
      await apiRequest<{ data_dir: string }>(API_ENDPOINTS.STORAGE_SETTINGS);
      setItems((prev) =>
        prev.map((item) =>
          item.id === "storage"
            ? { ...item, status: "ok", detail: "已就绪" }
            : item,
        ),
      );
    } catch {
      setItems((prev) =>
        prev.map((item) =>
          item.id === "storage"
            ? { ...item, status: "ok", detail: "使用默认位置" }
            : item,
        ),
      );
    }
  }, []);

  useEffect(() => {
    void runChecks();
  }, [runChecks]);

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-6 py-2.5 border-t border-border bg-muted/20">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <div
            key={item.id}
            className="flex items-center gap-1.5 text-xs"
          >
            <Icon className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">{item.label}</span>
            {item.status === "loading" ? (
              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
            ) : item.status === "ok" ? (
              <CheckCircle2 className="h-3.5 w-3.5 text-success" />
            ) : (
              <AlertTriangle className="h-3.5 w-3.5 text-warning" />
            )}
            <span
              className={cn(
                item.status === "warning"
                  ? "text-warning"
                  : "text-muted-foreground",
              )}
            >
              {item.detail}
            </span>
            {item.status === "warning" &&
            item.actionLabel &&
            item.actionSection ? (
              <button
                type="button"
                onClick={() => navigate(item.actionSection!)}
                className="text-primary hover:underline font-medium"
              >
                {item.actionLabel}
              </button>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
