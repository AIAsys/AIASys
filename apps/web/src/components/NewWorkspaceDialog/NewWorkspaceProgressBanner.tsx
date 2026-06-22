import { AlertCircle, Loader2 } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

interface NewTaskProgressBannerProps {
  showProgress: boolean;
  isError: boolean;
  stageLabel: string;
  errorMessage?: string | null;
  progress?: number;
  message?: string;
}

export function NewWorkspaceProgressBanner({
  showProgress,
  isError,
  stageLabel,
  errorMessage,
  progress,
  message,
}: NewTaskProgressBannerProps) {
  if (!showProgress && !isError) {
    return null;
  }

  return (
    <div
      className={cn(
        "mt-6 rounded-lg border px-4 py-3",
        isError
          ? "border-destructive/40 bg-destructive/5"
          : "border-border bg-muted dark:border-foreground dark:bg-foreground/70",
      )}
    >
      <div className="flex items-start gap-3">
        {isError ? (
          <AlertCircle className="mt-0.5 h-4 w-4 text-destructive" />
        ) : (
          <Loader2 className="mt-0.5 h-4 w-4 animate-spin text-muted-foreground dark:text-muted-foreground" />
        )}
        <div className="flex-1 space-y-2">
          <div
            className={cn(
              "text-sm font-medium",
              isError ? "text-destructive" : "text-foreground",
            )}
          >
            {isError ? "新任务初始化失败" : stageLabel}
            {!isError && typeof progress === "number" && progress > 0 && (
              <span className="ml-2 text-xs text-muted-foreground">
                {progress}%
              </span>
            )}
          </div>
          {!isError && typeof progress === "number" && progress > 0 && (
            <Progress value={progress} className="h-1.5" />
          )}
          <p className="text-xs text-muted-foreground">
            {isError
              ? errorMessage || "请检查当前工作区创建状态后重试。"
              : message || "当前会话会保持可见，待目标会话准备完成后再切换。"}
          </p>
        </div>
      </div>
    </div>
  );
}
