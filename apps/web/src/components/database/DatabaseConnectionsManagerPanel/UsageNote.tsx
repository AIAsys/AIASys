import { AlertTriangle, ChevronDown } from "lucide-react";

interface UsageNoteProps {
  isOpen: boolean;
  onToggle: () => void;
}

export function UsageNote({ isOpen, onToggle }: UsageNoteProps) {
  return (
    <div className="mt-3 rounded-lg border border-border bg-muted/20">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left"
      >
        <div className="flex items-center gap-2 text-xs font-medium text-foreground">
          <AlertTriangle className="h-3.5 w-3.5 text-muted-foreground" />
          <span>连接说明</span>
        </div>
        <ChevronDown
          className={`h-4 w-4 text-muted-foreground transition-transform ${isOpen ? "rotate-180" : ""}`}
        />
      </button>
      {isOpen ? (
        <div className="space-y-1 border-t border-border px-3 py-3 text-xs leading-5 text-muted-foreground">
          <p>PostgreSQL / MySQL 按关系库连接处理，继续显示默认授权与当前会话挂载策略。</p>
          <p>InfluxDB 3 按时序 query-only 连接处理，不暴露写入或 DDL 语义。</p>
          <p>当前面板负责创建、编辑、测试、附加、同步和卸载数据库连接。</p>
        </div>
      ) : null}
    </div>
  );
}
