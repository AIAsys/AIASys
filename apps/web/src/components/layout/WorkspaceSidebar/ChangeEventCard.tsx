import { useState } from "react";
import { ChevronRight, Clock, Bot, User, Server } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChangeEventItem } from "@/lib/api/fileChanges";
import { ChangeEventFileRow } from "./ChangeEventFileRow";
import type { FileHistoryEntry } from "@/lib/api/fileHistory";

interface ChangeEventCardProps {
  event: ChangeEventItem;
  selectedEntryId: string | null;
  onSelectEntry: (entry: FileHistoryEntry) => void;
}

const OPERATION_LABELS: Record<string, string> = {
  before_update: "修改",
  before_overwrite: "覆盖",
  before_delete: "删除",
  before_move: "移动",
  before_restore: "恢复",
};

function formatEventTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function getSourceIcon(source: string) {
  if (source === "workspace_asset" || source === "global_workspace_asset") {
    return <Server className="h-3.5 w-3.5 text-muted-foreground" />;
  }
  if (source === "agent" || source.startsWith("agent")) {
    return <Bot className="h-3.5 w-3.5 text-primary" />;
  }
  return <User className="h-3.5 w-3.5 text-info" />;
}

function getSourceLabel(source: string) {
  if (source === "workspace_asset" || source === "global_workspace_asset") {
    return "系统";
  }
  if (source === "agent" || source.startsWith("agent")) {
    return "Agent";
  }
  if (source === "api") {
    return "用户/Agent";
  }
  return source;
}

export function ChangeEventCard({
  event,
  selectedEntryId,
  onSelectEntry,
}: ChangeEventCardProps) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="border-b border-border last:border-b-0">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left hover:bg-muted/30 transition-colors"
        onClick={() => setExpanded((prev) => !prev)}
      >
        <ChevronRight
          className={cn(
            "h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform",
            expanded && "rotate-90",
          )}
        />
        <span className="shrink-0">{getSourceIcon(event.source)}</span>
        <span className="min-w-0 flex-1 truncate text-xs">
          <span className="font-medium text-foreground">
            {getSourceLabel(event.source)}
          </span>
          <span className="ml-1 text-muted-foreground">
            {OPERATION_LABELS[event.operation] ?? event.operation}
          </span>
          <span className="ml-1 text-muted-foreground">
            {event.file_count} 个文件
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-1 text-[11px] text-muted-foreground">
          <Clock className="h-3 w-3" />
          {formatEventTime(event.timestamp)}
        </span>
      </button>

      {expanded && (
        <div className="px-2 pb-2">
          {event.files.map((entry) => (
            <ChangeEventFileRow
              key={entry.id}
              entry={entry}
              isSelected={selectedEntryId === entry.id}
              onClick={() => onSelectEntry(entry)}
              depth={1}
            />
          ))}
        </div>
      )}
    </div>
  );
}
