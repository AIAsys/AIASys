/**
 * WorkerIndicators - Worker 活动指示器
 *
 * 显示当前活动的 Worker 列表及其状态
 */
import { Ban, CheckCircle2, Code2, Cpu } from "lucide-react";
import { useAiMessageContext, type WorkerRecord } from "./context";

const formatDuration = (ms?: number) => {
  if (!ms) return "";
  if (ms < 1000) return `${ms}ms`;
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m${remainingSeconds}s`;
};

interface WorkerIndicatorItemProps {
  worker: WorkerRecord;
  onClick?: (name: string) => void;
}

function WorkerIndicatorItem({ worker, onClick }: WorkerIndicatorItemProps) {
  return (
    <div
      onClick={() => onClick?.(worker.name)}
      className="flex items-center space-x-1.5 px-2 py-0.5 bg-muted border border-border rounded-full text-[10px] text-muted-foreground group hover:border-border/80 transition-colors cursor-pointer hover:bg-accent"
    >
      {worker.status === "running" ? (
        <Cpu size={10} className="text-warning" />
      ) : (
        <Code2 size={10} className="text-tertiary" />
      )}
      <span className="font-medium text-foreground/70">{worker.name}</span>
      {worker.durationMs && (
        <span className="text-muted-foreground">
          ({formatDuration(worker.durationMs)})
        </span>
      )}
      <span className="opacity-0 group-hover:opacity-100 transition-opacity">
        点击查看运行
      </span>
      {worker.status === "completed" && (
        <CheckCircle2 size={10} className="text-success" />
      )}
      {worker.status === "failed" && <Ban size={10} className="text-error" />}
    </div>
  );
}

export function WorkerIndicators() {
  const {
    state: { workerActivities },
    actions: { onWorkerClick },
  } = useAiMessageContext();

  if (workerActivities.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 px-4 mt-2 pb-1">
      {workerActivities.map((worker, idx) => (
        <WorkerIndicatorItem
          key={`${worker.name}-${idx}`}
          worker={worker}
          onClick={onWorkerClick}
        />
      ))}
    </div>
  );
}
