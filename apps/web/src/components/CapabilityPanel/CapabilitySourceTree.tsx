import { useState, useMemo, useCallback } from "react";
import { ChevronRight, ChevronDown, FileText, Folder, FolderOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CapabilitySourceTreeEntry } from "@/lib/api/capabilities";

interface TreeNode {
  name: string;
  path: string;
  isDir: boolean;
  children: TreeNode[];
}

function buildTree(entries: CapabilitySourceTreeEntry[]): TreeNode[] {
  const root: TreeNode[] = [];
  const map = new Map<string, TreeNode>();

  for (const entry of entries) {
    const parts = entry.path.split("/");
    let currentPath = "";
    let parentNodes = root;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      const isLast = i === parts.length - 1;
      const isDir = isLast ? entry.is_dir : true;

      let node = map.get(currentPath);
      if (!node) {
        node = { name: part, path: currentPath, isDir, children: [] };
        map.set(currentPath, node);
        parentNodes.push(node);
      }
      parentNodes = node.children;
    }
  }

  const sortNodes = (nodes: TreeNode[]): TreeNode[] => {
    const sorted = [...nodes].sort((a, b) => {
      if (a.isDir === b.isDir) return a.name.localeCompare(b.name);
      return a.isDir ? -1 : 1;
    });
    sorted.forEach((n) => {
      if (n.children.length > 0) n.children = sortNodes(n.children);
    });
    return sorted;
  };

  return sortNodes(root);
}

interface CapabilitySourceTreeProps {
  entries: CapabilitySourceTreeEntry[];
  selectedPath: string;
  onSelectFile: (path: string) => void;
}

function TreeItem({
  node,
  depth,
  selectedPath,
  onSelectFile,
  expandedPaths,
  toggleExpand,
}: {
  node: TreeNode;
  depth: number;
  selectedPath: string;
  onSelectFile: (path: string) => void;
  expandedPaths: Set<string>;
  toggleExpand: (path: string) => void;
}) {
  const isExpanded = expandedPaths.has(node.path);
  const isSelected = node.path === selectedPath;

  const handleClick = useCallback(() => {
    if (node.isDir) {
      toggleExpand(node.path);
    } else {
      onSelectFile(node.path);
    }
  }, [node, toggleExpand, onSelectFile]);

  return (
    <div>
      <button
        type="button"
        onClick={handleClick}
        className={cn(
          "flex w-full items-center gap-1 rounded px-1.5 py-0.5 text-[11px] transition-colors",
          isSelected
            ? "bg-primary/10 text-primary"
            : "text-foreground hover:bg-muted/60"
        )}
        style={{ paddingLeft: `${depth * 12 + 6}px` }}
      >
        {node.isDir ? (
          isExpanded ? (
            <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
          )
        ) : (
          <span className="h-3 w-3 shrink-0" />
        )}
        {node.isDir ? (
          isExpanded ? (
            <FolderOpen className="h-3 w-3 shrink-0 text-amber-500" />
          ) : (
            <Folder className="h-3 w-3 shrink-0 text-amber-500" />
          )
        ) : (
          <FileText className="h-3 w-3 shrink-0 text-blue-500" />
        )}
        <span className="truncate">{node.name}</span>
      </button>
      {node.isDir && isExpanded && (
        <div>
          {node.children.map((child) => (
            <TreeItem
              key={child.path}
              node={child}
              depth={depth + 1}
              selectedPath={selectedPath}
              onSelectFile={onSelectFile}
              expandedPaths={expandedPaths}
              toggleExpand={toggleExpand}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function CapabilitySourceTree({
  entries,
  selectedPath,
  onSelectFile,
}: CapabilitySourceTreeProps) {
  const tree = useMemo(() => buildTree(entries), [entries]);
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(() => {
    const initial = new Set<string>();
    for (const e of entries) {
      if (e.is_dir) initial.add(e.path);
    }
    return initial;
  });

  const toggleExpand = useCallback((path: string) => {
    setExpandedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  return (
    <div className="select-none">
      {tree.map((node) => (
        <TreeItem
          key={node.path}
          node={node}
          depth={0}
          selectedPath={selectedPath}
          onSelectFile={onSelectFile}
          expandedPaths={expandedPaths}
          toggleExpand={toggleExpand}
        />
      ))}
    </div>
  );
}
