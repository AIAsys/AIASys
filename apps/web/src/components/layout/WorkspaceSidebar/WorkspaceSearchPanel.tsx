import { useMemo, useState } from "react";
import { FileText, Search } from "lucide-react";

import type { WorkspaceFile } from "@/types/task";
import { isWorkspaceFolderMarkerFile } from "@/utils/fileTreeUtils";

interface WorkspaceSearchPanelProps {
  files: WorkspaceFile[];
  onOpenFile?: (file: WorkspaceFile) => void;
}

export function WorkspaceSearchPanel({
  files,
  onOpenFile,
}: WorkspaceSearchPanelProps) {
  const [query, setQuery] = useState("");
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const trimmedQuery = query.trim().toLowerCase();
  const results = useMemo(() => {
    const visibleFiles = files.filter(
      (file) => !isWorkspaceFolderMarkerFile(file.name),
    );
    if (!trimmedQuery) {
      return visibleFiles.slice(0, 20);
    }
    return visibleFiles
      .filter((file) => file.name.toLowerCase().includes(trimmedQuery))
      .slice(0, 50);
  }, [files, trimmedQuery]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <div className="border-b border-border px-3 py-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索工作区文件..."
            className="h-9 w-full rounded-lg border border-input bg-muted/50 pl-9 pr-3 font-mono text-xs outline-none transition-colors placeholder:text-muted-foreground/60 focus:bg-background focus:ring-1 focus:ring-ring"
          />
        </div>
        <div className="mt-2 text-[11px] text-muted-foreground">
          {trimmedQuery ? `${results.length} 个匹配项` : "显示最近的工作区文件"}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {results.length > 0 ? (
          <div className="space-y-1">
            {results.map((file) => {
              const isSelected = selectedFileName === file.name;
              return (
                <button
                  key={file.name}
                  type="button"
                  onClick={() => {
                    setSelectedFileName(file.name);
                    onOpenFile?.(file);
                  }}
                  className={`flex w-full min-w-0 items-start gap-2 rounded-lg px-2 py-2 text-left text-sm transition-colors ${
                    isSelected
                      ? "bg-secondary text-foreground"
                      : "text-foreground/80 hover:bg-muted/50"
                  }`}
                  title={file.name}
                >
                  <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-mono text-xs">
                      {file.name}
                    </span>
                    <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                      {file.mtime
                        ? new Date(file.mtime).toLocaleString("zh-CN", {
                            hour12: false,
                          })
                        : "时间未知"}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center px-5 text-center text-xs leading-5 text-muted-foreground">
            没有匹配的工作区文件。
          </div>
        )}
      </div>
    </div>
  );
}
