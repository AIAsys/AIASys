import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ExternalLink, Globe, Loader2, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiRequest } from "@/lib/api/httpClient";
import { API_ENDPOINTS } from "@/config/api";
import { cn } from "@/lib/utils";

interface UvMirrorConfig {
  installer_mirror: string;
}

export function UvMirrorSettings() {
  const [config, setConfig] = useState<UvMirrorConfig>({
    installer_mirror: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tipsOpen, setTipsOpen] = useState(false);
  const [message, setMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  const loadConfig = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiRequest<UvMirrorConfig>(
        API_ENDPOINTS.UV_MIRROR_CONFIG,
      );
      setConfig(data);
    } catch {
      // 首次加载失败静默处理
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setMessage(null);
    try {
      const data = await apiRequest<UvMirrorConfig>(
        API_ENDPOINTS.UV_MIRROR_CONFIG,
        {
          method: "PUT",
          body: config,
        },
      );
      setConfig(data);
      setMessage({ type: "success", text: "已保存" });
    } catch (err) {
      setMessage({
        type: "error",
        text: err instanceof Error ? err.message : "保存失败",
      });
    } finally {
      setSaving(false);
    }
  }, [config]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-fg" />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-2xl space-y-6">
        <div>
          <h2 className="text-lg font-semibold text-main">
            uv 包管理器镜像
          </h2>
          <p className="mt-1 text-sm text-muted-fg">
            仅配置安装 uv 本身的下载源。PyPI 包和 Python 二进制镜像由 uv
            自身处理。
          </p>
        </div>

        {/* 可折叠的配置参考 */}
        <div className="rounded-lg border">
          <button
            type="button"
            onClick={() => setTipsOpen((v) => !v)}
            className="flex w-full items-center justify-between rounded-lg px-4 py-3 text-left text-sm transition-colors hover:bg-muted/50"
          >
            <span className="text-main font-medium">
              PyPI 和 Python 二进制镜像怎么配？
            </span>
            <ChevronDown
              className={cn(
                "h-4 w-4 text-muted-fg transition-transform",
                tipsOpen && "rotate-180",
              )}
            />
          </button>
          {tipsOpen && (
            <div className="border-t px-4 py-3 space-y-3 text-sm">
              <p className="text-muted-fg">
                这两个镜像 uv 原生支持，不需要通过 AIASys 配置。
                请在终端或 uv 配置文件中直接设置：
              </p>

              <div className="space-y-2.5">
                <div>
                  <p className="font-medium text-xs text-muted-fg mb-1">
                    PyPI 包镜像（影响 uv sync / uv pip install）
                  </p>
                  <code className="block text-xs text-muted-fg mb-1">
                    编辑 ~/.config/uv/config.toml
                  </code>
                  <pre className="rounded bg-muted px-3 py-1.5 text-xs overflow-x-auto">
                    {`[registries.pypi]
index = "https://mirrors.aliyun.com/pypi/simple/"`}
                  </pre>
                </div>
                <div>
                  <p className="font-medium text-xs text-muted-fg mb-1">
                    Python 二进制镜像（影响 uv python install）
                  </p>
                  <pre className="rounded bg-muted px-3 py-1.5 text-xs overflow-x-auto break-all whitespace-pre-wrap">
                    {`export UV_PYTHON_INSTALL_MIRROR=https://mirror.nju.edu.cn/github-release/astral-sh/python-build-standalone/`}
                  </pre>
                </div>
              </div>

              <a
                href="https://docs.astral.sh/uv/configuration/"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline dark:text-blue-400"
              >
                <ExternalLink className="h-3 w-3" />
                uv 官方配置文档
              </a>
            </div>
          )}
        </div>

        {/* 安装器镜像输入 */}
        <div className="space-y-2">
          <Label
            htmlFor="installer-mirror"
            className="flex items-center gap-1.5"
          >
            <Globe className="h-3.5 w-3.5 text-muted-fg" />
            uv 安装器镜像
          </Label>
          <Input
            id="installer-mirror"
            placeholder="留空从 astral.sh 下载"
            value={config.installer_mirror}
            onChange={(e) =>
              setConfig((prev) => ({
                ...prev,
                installer_mirror: e.target.value,
              }))
            }
          />
          <p className="text-xs text-muted-fg">
            系统在安装 uv 时会优先使用此地址。示例：
            https://gh.chjina.com/https://github.com/astral-sh
          </p>
        </div>

        {message && (
          <div
            className={`rounded-md px-4 py-2 text-sm ${
              message.type === "success"
                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400"
                : "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-400"
            }`}
          >
            {message.text}
          </div>
        )}

        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={saving}>
            {saving ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            保存
          </Button>
        </div>
      </div>
    </div>
  );
}
