import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, FileText, Folder } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TemplateFileItem } from "@/lib/api/workspaces";

function getFileLanguageClass(fileName: string): string {
  const ext = fileName.split(".").pop()?.toLowerCase() ?? "";
  switch (ext) {
    case "py":
    case "js":
    case "ts":
    case "tsx":
    case "jsx":
      return "bg-amber-50/50 dark:bg-amber-950/20";
    case "json":
      return "bg-blue-50/50 dark:bg-blue-950/20";
    case "md":
    case "markdown":
      return "bg-slate-50/50 dark:bg-slate-950/20";
    case "yml":
    case "yaml":
    case "toml":
      return "bg-emerald-50/50 dark:bg-emerald-950/20";
    case "gitignore":
    case "txt":
    case "env":
      return "bg-gray-50/50 dark:bg-gray-950/20";
    default:
      return "bg-muted/30";
  }
}

function FileContentPreview({
  fileName,
  content,
}: {
  fileName: string;
  content: string;
}) {
  const bgClass = getFileLanguageClass(fileName);
  return (
    <pre
      className={cn(
        "max-w-full break-all whitespace-pre-wrap rounded-md border border-border/50 p-2 font-mono text-[11px] leading-relaxed text-muted-foreground",
        bgClass,
      )}
    >
      {content || "（空文件）"}
    </pre>
  );
}

interface PreviewTreeNode {
  name: string;
  path: string;
  isDirectory: boolean;
  children?: PreviewTreeNode[];
  content?: string;
}

function buildPreviewTree(files: TemplateFileItem[]): PreviewTreeNode[] {
  const dirMap: Record<string, PreviewTreeNode> = {};
  const rootNodes: PreviewTreeNode[] = [];

  for (const file of files) {
    const parts = file.relative_path.split("/").filter(Boolean);
    if (parts.length === 1) {
      rootNodes.push({
        name: parts[0],
        path: file.relative_path,
        isDirectory: false,
        content: file.content,
      });
      continue;
    }

    let currentPath = "";
    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i];
      const parentPath = currentPath;
      currentPath = currentPath ? `${currentPath}/${part}` : part;

      if (!dirMap[currentPath]) {
        const dirNode: PreviewTreeNode = {
          name: part,
          path: currentPath,
          isDirectory: true,
          children: [],
        };
        dirMap[currentPath] = dirNode;

        if (parentPath && dirMap[parentPath]) {
          dirMap[parentPath].children!.push(dirNode);
        } else if (!parentPath) {
          rootNodes.push(dirNode);
        }
      }
    }

    const fileName = parts[parts.length - 1];
    const parentDir = parts.slice(0, -1).join("/");
    const fileNode: PreviewTreeNode = {
      name: fileName,
      path: file.relative_path,
      isDirectory: false,
      content: file.content,
    };

    if (dirMap[parentDir]) {
      dirMap[parentDir].children!.push(fileNode);
    }
  }

  return sortPreviewNodes(rootNodes);
}

function sortPreviewNodes(nodes: PreviewTreeNode[]): PreviewTreeNode[] {
  return nodes
    .map((node) => ({
      ...node,
      children: node.children ? sortPreviewNodes(node.children) : undefined,
    }))
    .sort((a, b) => {
      if (a.isDirectory && !b.isDirectory) return -1;
      if (!a.isDirectory && b.isDirectory) return 1;
      return a.name.localeCompare(b.name);
    });
}

function TreeNodeItem({
  node,
  selectedPath,
  onSelect,
  depth = 0,
}: {
  node: PreviewTreeNode;
  selectedPath: string;
  onSelect: (path: string) => void;
  depth?: number;
}) {
  const [expanded, setExpanded] = useState(true);

  if (node.isDirectory) {
    return (
      <div>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex w-full items-center gap-1 rounded-sm py-0.5 text-left hover:bg-muted/50"
          style={{ paddingLeft: `${depth * 12}px` }}
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
          )}
          <Folder className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate text-[11px]">{node.name}</span>
        </button>
        {expanded &&
          node.children?.map((child) => (
            <TreeNodeItem
              key={child.path}
              node={child}
              selectedPath={selectedPath}
              onSelect={onSelect}
              depth={depth + 1}
            />
          ))}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onSelect(node.path)}
      className={cn(
        "flex w-full items-center gap-1 rounded-sm py-0.5 text-left hover:bg-muted/50",
        selectedPath === node.path && "bg-primary/5 text-primary",
      )}
      style={{ paddingLeft: `${depth * 12 + 16}px` }}
    >
      <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <span className="truncate text-[11px]">{node.name}</span>
    </button>
  );
}

export function TemplatePreviewFileTree({
  files,
}: {
  files: TemplateFileItem[];
}) {
  const [selectedPath, setSelectedPath] = useState(
    files[0]?.relative_path ?? "",
  );
  const selectedFile = files.find((f) => f.relative_path === selectedPath);
  const tree = useMemo(() => buildPreviewTree(files), [files]);

  if (files.length === 0) {
    return (
      <div className="py-4 text-center text-sm text-muted-foreground">
        该模板不包含文件
      </div>
    );
  }

  return (
    <div className="flex h-full gap-2 overflow-hidden">
      <div className="w-32 shrink-0 overflow-y-auto border-r border-border pr-1">
        {tree.map((node) => (
          <TreeNodeItem
            key={node.path}
            node={node}
            selectedPath={selectedPath}
            onSelect={setSelectedPath}
          />
        ))}
      </div>
      <div className="min-w-0 flex-1 overflow-y-auto">
        <div className="mb-1 text-[10px] text-muted-foreground">
          {selectedFile?.relative_path}
        </div>
        <FileContentPreview
          fileName={selectedFile?.relative_path ?? ""}
          content={selectedFile?.content ?? ""}
        />
      </div>
    </div>
  );
}
