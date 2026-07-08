import { cn } from "@/lib/utils";
import type { FileHistoryEntry } from "@/lib/api/fileHistory";
import {
  FileText,
  GitBranch,
  Trash2,
  FolderInput,
  RotateCcw,
} from "lucide-react";

interface ChangeEventFileRowProps {
  entry: FileHistoryEntry;
  isSelected: boolean;
  onClick: () => void;
  depth?: number;
}

const OPERATION_ICONS: Record<string, React.ReactNode> = {
  before_update: <GitBranch className="h-3.5 w-3.5 text-warning" />,
  before_overwrite: <GitBranch className="h-3.5 w-3.5 text-info" />,
  before_delete: <Trash2 className="h-3.5 w-3.5 text-error" />,
  before_move: <FolderInput className="h-3.5 w-3.5 text-tertiary" />,
  before_restore: <RotateCcw className="h-3.5 w-3.5 text-success" />,
};

const OPERATION_LABELS: Record<string, string> = {
  before_update: "修改",
  before_overwrite: "覆盖",
  before_delete: "删除",
  before_move: "移动",
  before_restore: "恢复",
};

export function ChangeEventFileRow({
  entry,
  isSelected,
  onClick,
  depth = 0,
}: ChangeEventFileRowProps) {
  const fileName = entry.file_path.split("/").pop() || entry.file_path;
  const dirPath = entry.file_path.includes("/")
    ? entry.file_path.substring(0, entry.file_path.lastIndexOf("/"))
    : "";

  return (
    <button
      type="button"
      className={cn(
        "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
        isSelected
          ? "bg-primary/10 text-primary"
          : "text-foreground hover:bg-muted/50",
      )}
      style={{ paddingLeft: `${8 + depth * 16}px` }}
      onClick={onClick}
    >
      <span className="shrink-0">
        {OPERATION_ICONS[entry.operation] ?? (
          <FileText className="h-3.5 w-3.5 text-muted-foreground" />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-mono text-xs">{fileName}</span>
        {dirPath && (
          <span className="block truncate text-[11px] text-muted-foreground">
            {dirPath}
          </span>
        )}
      </span>
      <span className="shrink-0 text-[11px] text-muted-foreground">
        {OPERATION_LABELS[entry.operation] ?? entry.operation}
      </span>
    </button>
  );
}
