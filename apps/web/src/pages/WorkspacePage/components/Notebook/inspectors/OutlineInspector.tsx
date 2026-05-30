import { Badge } from "@/components/ui/badge";
import type { NotebookOutlineItem } from "@/types/notebook";

interface OutlineInspectorProps {
  items: NotebookOutlineItem[];
  onSelectCell: (cellId: string) => void;
}

export function OutlineInspector({ items, onSelectCell }: OutlineInspectorProps) {
  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border/60 px-3 py-4 text-xs text-muted-foreground">
        当前 notebook 还没有可用的 outline 项。
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {items.map((item) => (
        <button
          key={`${item.cell_id}-${item.cell_index}-${item.title}`}
          type="button"
          className="w-full rounded-xl border border-border px-3 py-3 text-left transition-colors hover:border-primary/40 hover:bg-muted/30"
          onClick={() => onSelectCell(item.cell_id)}
        >
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-medium text-foreground">{item.title}</div>
            <Badge variant="outline">{item.item_type}</Badge>
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            Cell {item.cell_index + 1}
            {typeof item.level === "number" ? ` · H${item.level}` : ""}
            {item.execution_count ? ` · 执行 ${item.execution_count}` : ""}
          </div>
        </button>
      ))}
    </div>
  );
}
