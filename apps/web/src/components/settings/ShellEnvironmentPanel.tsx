import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  Download,
  ExternalLink,
  Loader2,
  AlertCircle,
  Terminal,
  Info,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { apiRequest } from "@/lib/api/httpClient";
import { API_ENDPOINTS, API_BASE_URL } from "@/config/api";
import { cn } from "@/lib/utils";
import {
  FileUploadToast,
  useFileUploadToast,
} from "@/components/file/FileUploadToast";

interface ShellComponent {
  id: string;
  name: string;
  installed: boolean;
  path: string | null;
  version: string | null;
  description: string;
  download_url: string;
  license: string;
  bundled: boolean;
  optional: boolean;
}

interface ShellEnvironmentData {
  platform: string;
  is_windows: boolean;
  recommended_family: string;
  components: ShellComponent[];
  guidance: string;
}

const FAMILY_LABELS: Record<string, string> = {
  posix: "POSIX (Git Bash / Bash)",
  wsl: "WSL",
  busybox: "busybox-w32 (ash)",
  powershell: "PowerShell",
  cmd: "CMD",
};

export function ShellEnvironmentPanel() {
  const [data, setData] = useState<ShellEnvironmentData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { toasts, showSuccess, showError } = useFileUploadToast();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiRequest<ShellEnvironmentData>(
        API_ENDPOINTS.SHELL_ENVIRONMENT,
      );
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-fg" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <AlertCircle className="h-8 w-8 text-error" />
        <p className="text-sm text-muted-fg">{error || "未能获取环境信息"}</p>
        <Button variant="outline" size="sm" onClick={load}>
          重试
        </Button>
      </div>
    );
  }

  const recommended = FAMILY_LABELS[data.recommended_family] || data.recommended_family;

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-3xl space-y-6">
        <div>
          <h2 className="text-lg font-semibold text-main">环境增强</h2>
          <p className="mt-1 text-sm text-muted-fg">
            查看当前系统可用的 shell 环境，并安装可选的跨平台组件。
          </p>
        </div>

        {/* 当前推荐 shell */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Terminal className="h-4 w-4" />
              当前推荐 Shell
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center gap-3">
              <Badge variant="info">{recommended}</Badge>
              <span className="text-xs text-muted-fg capitalize">
                平台：{data.platform}
              </span>
            </div>
            <p className="text-sm text-muted-fg">{data.guidance}</p>
          </CardContent>
        </Card>

        {/* 组件列表 */}
        <div className="space-y-3">
          <h3 className="text-sm font-medium text-main">组件状态</h3>
          {data.components.map((component) => (
            <ComponentCard
              key={component.id}
              component={component}
              onRefresh={load}
              onSuccess={showSuccess}
              onError={showError}
            />
          ))}
        </div>

        {/* 协议说明 */}
        <div className="rounded-lg border border-border bg-muted/40 p-4">
          <div className="flex items-start gap-2">
            <Info className="mt-0.5 h-4 w-4 text-muted-fg" />
            <p className="text-xs text-muted-fg">
              标有“已内置”的组件随 AIASys 桌面安装包一起分发；标有“可选”的组件需用户自行下载安装。
              GPL 类组件的许可证文本已随包提供，可在安装目录的 LICENSES/ 文件夹中查看。
            </p>
          </div>
        </div>
      </div>
      {toasts.map((toast) => (
        <FileUploadToast
          key={toast.id}
          message={toast.message}
          type={toast.type}
        />
      ))}
    </div>
  );
}

function ComponentCard({
  component,
  onRefresh,
  onSuccess,
  onError,
}: {
  component: ShellComponent;
  onRefresh: () => void;
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}) {
  const [installing, setInstalling] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);

  const handleDownload = useCallback(() => {
    if (component.download_url) {
      window.open(component.download_url, "_blank", "noopener,noreferrer");
    }
  }, [component.download_url]);

  const handleAutoInstall = useCallback(async () => {
    if (component.id !== "busybox_w32") return;
    setInstalling(true);
    setProgress(null);
    try {
      const url = `${API_BASE_URL}${API_ENDPOINTS.SHELL_ENVIRONMENT_INSTALL_BUSYBOX_STREAM}`;
      const response = await fetch(url, { credentials: "include" });
      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status}`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let done = false;
      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const event = JSON.parse(line.slice(6));
                if (event.type === "progress" && event.total > 0) {
                  setProgress(Math.round((event.downloaded / event.total) * 100));
                } else if (event.type === "done") {
                  setProgress(100);
                  onSuccess("busybox-w32 安装成功，Shell 环境已增强");
                  onRefresh();
                } else if (event.type === "error") {
                  throw new Error(event.message);
                }
              } catch {
                // skip malformed lines
              }
            }
          }
        }
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "下载失败");
    } finally {
      setInstalling(false);
      setProgress(null);
    }
  }, [component.id, onRefresh, onSuccess, onError]);

  const canAutoInstall = component.id === "busybox_w32" && !component.installed;

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-foreground">
                {component.name}
              </span>
              <StatusBadge component={component} />
            </div>
            <p className="text-xs text-muted-fg">{component.description}</p>
            {component.version && (
              <p className="text-xs text-muted-fg">版本：{component.version}</p>
            )}
            {component.path && (
              <p className="truncate text-xs text-muted-fg" title={component.path}>
                路径：{component.path}
              </p>
            )}
            {component.license && (
              <p className="text-xs text-muted-fg">许可证：{component.license}</p>
            )}
          </div>
          <div className="shrink-0 flex flex-col items-end gap-2">
            {canAutoInstall && (
              <>
                <Button
                  size="sm"
                  variant="default"
                  onClick={handleAutoInstall}
                  disabled={installing}
                >
                  {installing ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Download className="mr-1.5 h-3.5 w-3.5" />
                  )}
                  {installing
                    ? progress !== null
                      ? `${progress}%`
                      : "下载中..."
                    : "自动下载"}
                </Button>
                {installing && progress !== null ? (
                  <div className="w-28 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full bg-primary transition-all duration-200"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                ) : null}
              </>
            )}
            {component.optional && !component.installed && component.download_url && !canAutoInstall && (
              <Button size="sm" variant="outline" onClick={handleDownload}>
                <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                官网下载
              </Button>
            )}
            {component.optional && component.installed && component.download_url && (
              <Button size="sm" variant="ghost" onClick={handleDownload}>
                <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                官网
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function StatusBadge({ component }: { component: ShellComponent }) {
  if (component.installed) {
    return (
      <Badge variant="success" className="gap-1">
        <CheckCircle2 className="h-3 w-3" />
        已安装
      </Badge>
    );
  }
  if (component.bundled) {
    return (
      <Badge variant="warning" className="gap-1">
        <AlertCircle className="h-3 w-3" />
        未就绪
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className={cn("gap-1", component.optional && "text-muted-fg")}>
      {component.optional ? "可选" : "未安装"}
    </Badge>
  );
}
