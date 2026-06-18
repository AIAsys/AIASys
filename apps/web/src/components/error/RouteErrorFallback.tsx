import { AlertTriangle, Home, RefreshCw } from "lucide-react";

interface RouteErrorFallbackProps {
  error: Error;
  reset: () => void;
}

/**
 * 路由级错误回退组件。
 *
 * 当某个懒加载路由的 chunk 加载失败或路由组件渲染崩溃时，
 * 用此组件替代整页白屏 / 全屏错误页，让用户可以就地重试或返回首页，
 * 而不必刷新整个应用。
 */
export function RouteErrorFallback({ error, reset }: RouteErrorFallbackProps) {
  // chunk 加载失败通常是网络问题或部署后旧 chunk 失效，
  // 提示用户重试或返回首页即可恢复
  const isChunkLoadError =
    error.name === "ChunkLoadError" ||
    /Loading chunk|Failed to fetch dynamically imported module/i.test(
      error.message,
    );

  const title = isChunkLoadError ? "页面资源加载失败" : "页面加载出错";
  const description = isChunkLoadError
    ? "可能是网络波动或页面版本已更新，重试通常可以恢复。"
    : error.message || "发生未知错误，请重试或返回首页。";

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
      <div className="w-full max-w-md space-y-4 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-error/30 bg-error-container/20">
          <AlertTriangle className="h-6 w-6 text-error" />
        </div>
        <div className="space-y-1.5">
          <h1 className="text-base font-semibold">{title}</h1>
          <p className="break-words text-sm text-muted-foreground">
            {description}
          </p>
        </div>
        <div className="flex items-center justify-center gap-3">
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center justify-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <RefreshCw className="h-4 w-4" />
            重试
          </button>
          <button
            type="button"
            onClick={() => {
              window.location.href = "/";
            }}
            className="inline-flex items-center justify-center gap-1.5 rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            <Home className="h-4 w-4" />
            返回首页
          </button>
        </div>
      </div>
    </div>
  );
}
