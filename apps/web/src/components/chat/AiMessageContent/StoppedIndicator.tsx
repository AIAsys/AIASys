/**
 * StoppedIndicator - 终止状态提示
 *
 * 显示任务已被终止的提示
 */
import { Ban } from "lucide-react";

export function StoppedIndicator() {
  return (
    <div className="flex items-center gap-2 text-sm text-warning py-2 px-3 bg-warning-container rounded-lg border border-warning/20">
      <Ban size={16} className="text-warning" />
      <span className="font-medium">任务已终止</span>
    </div>
  );
}
