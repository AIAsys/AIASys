import { useMemo, useCallback, useState } from "react";
import { FileText, Folder, Loader2 } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

interface SelectableFileItem {
  path: string;
  content?: string;
}

interface SelectableTreeNode {
  name: string;
  path: string;
  isDirectory: boolean;
  children?: SelectableTreeNode[];
  content?: string;
}

function buildTree(files: SelectableFileItem[]): SelectableTreeNode[] {
  const dirMap: Record<string, SelectableTreeNode> = {};
  const rootNodes: SelectableTreeNode[] = [];

  for (const file of files) {
    const parts = file.path.split("/").filter(Boolean);
    if (parts.length === 1) {
      rootNodes.push({
        name: parts[0],
        path: file.path,
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
        const dirNode: SelectableTreeNode = {
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
    const fileNode: SelectableTreeNode = {
      name: fileName,
      path: file.path,
      isDirectory: false,
      content: file.content,
    };

    if (dirMap[parentDir]) {
      dirMap[parentDir].children!.push(fileNode);
    }
  }

  return sortNodes(rootNodes);
}

function sortNodes(nodes: SelectableTreeNode[]): SelectableTreeNode[] {
  return nodes
    .map((node) => ({
      ...node,
      children: node.children ? sortNodes(node.children) : undefined,
    }))
    .sort((a, b) => {
      if (a.isDirectory && !b.isDirectory) return -1;
      if (!a.isDirectory && b.isDirectory) return 1;
      return a.name.localeCompare(b.name);
    });
}

function getAllFilePaths(node: SelectableTreeNode): string[] {
  if (!node.isDirectory) return [node.path];
  return node.children?.flatMap(getAllFilePaths) ?? [];
}

// ── 排除规则引擎（类 gitignore 风格） ──

export interface ExcludeRule {
  id: string;
  pattern: string;
  label?: string;
  isDefault?: boolean;
  enabled: boolean;
}

export const DEFAULT_EXCLUDE_RULES: ExcludeRule[] = [
  { id: "default-1", pattern: "__pycache__/", label: "Python 缓存", isDefault: true, enabled: true },
  { id: "default-2", pattern: "*.pyc", label: "Python 编译文件", isDefault: true, enabled: true },
  { id: "default-3", pattern: ".ipynb_checkpoints/", label: "Notebook 检查点", isDefault: true, enabled: true },
  { id: "default-4", pattern: ".env", label: "环境变量文件", isDefault: true, enabled: true },
  { id: "default-5", pattern: ".env.*", label: "环境变量文件", isDefault: true, enabled: true },
  { id: "default-6", pattern: "node_modules/", label: "Node 依赖", isDefault: true, enabled: true },
  { id: "default-7", pattern: "*.log", label: "日志文件", isDefault: true, enabled: true },
  { id: "default-8", pattern: "*.tmp", label: "临时文件", isDefault: true, enabled: true },
  { id: "default-9", pattern: "*.cache", label: "缓存文件", isDefault: true, enabled: true },
  { id: "default-10", pattern: ".*", label: "隐藏文件", isDefault: true, enabled: true },
];

function globToRegExp(pattern: string): RegExp {
  let regex = "";
  let i = 0;
  while (i < pattern.length) {
    const c = pattern[i];
    if (c === "*") {
      if (i + 1 < pattern.length && pattern[i + 1] === "*") {
        regex += ".*";
        i += 2;
      } else {
        regex += "[^/]*";
        i++;
      }
    } else if (c === "?") {
      regex += "[^/]";
      i++;
    } else if (".+$^{}()|[]\\".includes(c)) {
      regex += "\\" + c;
      i++;
    } else {
      regex += c;
      i++;
    }
  }
  return new RegExp("^" + regex + "$");
}

function matchExcludePattern(filePath: string, pattern: string): boolean {
  const normalizedPath = filePath.replace(/^\/+/,"");

  // 目录模式（以 / 结尾）：匹配任意层级的该目录及其所有子内容
  if (pattern.endsWith("/")) {
    const dirPattern = pattern.slice(0, -1);
    if (normalizedPath === dirPattern) return true;
    if (normalizedPath.startsWith(dirPattern + "/")) return true;
    const parts = normalizedPath.split("/");
    for (let i = 0; i < parts.length; i++) {
      if (parts[i] === dirPattern) return true;
      const prefix = parts.slice(0, i + 1).join("/");
      if (prefix === dirPattern || prefix.startsWith(dirPattern + "/")) return true;
    }
    return false;
  }

  // 不含 / 的模式：匹配任何层级的文件名
  if (!pattern.includes("/")) {
    const regex = globToRegExp(pattern);
    const parts = normalizedPath.split("/");
    return parts.some((part) => regex.test(part));
  }

  // 含 / 的模式：匹配完整路径
  const regex = globToRegExp(pattern);
  return regex.test(normalizedPath) || normalizedPath.startsWith(pattern + "/");
}

export function isFileExcluded(filePath: string, rules: ExcludeRule[]): boolean {
  const normalizedPath = filePath.replace(/^\/+/, "");
  return rules.some((rule) => rule.enabled && matchExcludePattern(normalizedPath, rule.pattern));
}

/** 兼容旧接口：使用默认规则判断临时文件 */
export function getTempFilePaths(files: SelectableFileItem[]): string[] {
  return files.filter((f) => isFileExcluded(f.path, DEFAULT_EXCLUDE_RULES)).map((f) => f.path);
}

interface TreeNodeItemProps {
  node: SelectableTreeNode;
  selectedPaths: Set<string>;
  onToggle: (path: string, isDirectory: boolean, checked: boolean) => void;
  depth?: number;
  activePreviewPath?: string | null;
  onTogglePreview?: (path: string) => void;
  previewContent?: string | null;
  isPreviewLoading?: boolean;
}

function TreeNodeItem({
  node,
  selectedPaths,
  onToggle,
  depth = 0,
  activePreviewPath,
  onTogglePreview,
  previewContent,
  isPreviewLoading,
}: TreeNodeItemProps) {
  const filePaths = useMemo(() => getAllFilePaths(node), [node]);
  const checked = filePaths.length > 0 && filePaths.every((p) => selectedPaths.has(p));
  const indeterminate =
    !checked && filePaths.length > 0 && filePaths.some((p) => selectedPaths.has(p));

  const handleChange = useCallback(
    (checkedState: boolean | "indeterminate") => {
      const isChecked = checkedState === true;
      onToggle(node.path, node.isDirectory, isChecked);
    },
    [node, onToggle],
  );

  const [internalPreviewExpanded, setInternalPreviewExpanded] = useState(false);

  if (node.isDirectory) {
    return (
      <div>
        <div
          className="flex items-center gap-1 rounded-sm py-0.5 hover:bg-muted/50"
          style={{ paddingLeft: `${depth * 12}px` }}
        >
          <Checkbox
            checked={checked ? true : indeterminate ? "indeterminate" : false}
            onCheckedChange={handleChange}
            className="h-3.5 w-3.5"
          />
          <Folder className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate text-[11px]">{node.name}</span>
        </div>
        {node.children?.map((child) => (
          <TreeNodeItem
            key={child.path}
            node={child}
            selectedPaths={selectedPaths}
            onToggle={onToggle}
            depth={depth + 1}
            activePreviewPath={activePreviewPath}
            onTogglePreview={onTogglePreview}
            previewContent={previewContent}
            isPreviewLoading={isPreviewLoading}
          />
        ))}
      </div>
    );
  }

  const isPreviewing = activePreviewPath === node.path;
  const showPreview = isPreviewing || (internalPreviewExpanded && !onTogglePreview && node.content);
  const displayContent = isPreviewing ? previewContent : node.content;

  return (
    <div>
      <div
        className={cn(
          "flex items-center gap-1 rounded-sm py-0.5 hover:bg-muted/50",
          isPreviewing && "bg-primary/5",
        )}
        style={{ paddingLeft: `${depth * 12}px` }}
      >
        <Checkbox
          checked={selectedPaths.has(node.path)}
          onCheckedChange={handleChange}
          className="h-3.5 w-3.5"
        />
        <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <button
          type="button"
          onClick={() => {
            if (onTogglePreview) {
              onTogglePreview(node.path);
            } else {
              setInternalPreviewExpanded((v) => !v);
            }
          }}
          className={cn(
            "truncate text-[11px] text-left hover:underline",
            isPreviewing && "text-primary font-medium",
          )}
          title="点击预览文件内容"
        >
          {node.name}
        </button>
      </div>
      {showPreview && (
        <div style={{ marginLeft: `${depth * 12 + 20}px` }}>
          {isPreviewLoading && isPreviewing ? (
            <div className="py-2 text-[10px] text-muted-foreground flex items-center gap-1">
              <Loader2 className="h-3 w-3 animate-spin" />
              加载中...
            </div>
          ) : displayContent ? (
            <pre className="mx-1 my-0.5 rounded border border-border/50 bg-muted/30 px-2 py-1 font-mono text-[10px] leading-relaxed text-muted-foreground break-all whitespace-pre-wrap">
              {displayContent}
            </pre>
          ) : (
            <div className="py-2 text-[10px] text-muted-foreground">暂无预览内容</div>
          )}
        </div>
      )}
    </div>
  );
}

interface TemplateFileTreeSelectorProps {
  files: SelectableFileItem[];
  selectedPaths: Set<string>;
  onSelectionChange: (selectedPaths: Set<string>) => void;
  activePreviewPath?: string | null;
  onTogglePreview?: (path: string) => void;
  previewContent?: string | null;
  isPreviewLoading?: boolean;
}

export function TemplateFileTreeSelector({
  files,
  selectedPaths,
  onSelectionChange,
  activePreviewPath,
  onTogglePreview,
  previewContent,
  isPreviewLoading,
}: TemplateFileTreeSelectorProps) {
  const tree = useMemo(() => buildTree(files), [files]);
  const allPaths = useMemo(() => files.map((f) => f.path), [files]);

  const handleToggle = useCallback(
    (path: string, isDirectory: boolean, checked: boolean) => {
      const newSet = new Set(selectedPaths);

      if (isDirectory) {
        const findNode = (nodes: SelectableTreeNode[]): SelectableTreeNode | null => {
          for (const n of nodes) {
            if (n.path === path) return n;
            if (n.children) {
              const found = findNode(n.children);
              if (found) return found;
            }
          }
          return null;
        };
        const node = findNode(tree);
        const paths = node ? getAllFilePaths(node) : [];
        for (const p of paths) {
          if (checked) {
            newSet.add(p);
          } else {
            newSet.delete(p);
          }
        }
      } else {
        if (checked) {
          newSet.add(path);
        } else {
          newSet.delete(path);
        }
      }

      onSelectionChange(newSet);
    },
    [selectedPaths, tree, onSelectionChange],
  );

  const handleSelectAll = useCallback(
    (checked: boolean) => {
      if (checked) {
        onSelectionChange(new Set(allPaths));
      } else {
        onSelectionChange(new Set());
      }
    },
    [allPaths, onSelectionChange],
  );

  const allChecked = allPaths.length > 0 && allPaths.every((p) => selectedPaths.has(p));

  if (files.length === 0) {
    return (
      <div className="py-4 text-center text-sm text-muted-foreground">
        没有可选择的文件
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1 rounded-sm py-0.5 hover:bg-muted/50">
        <Checkbox
          checked={allChecked}
          onCheckedChange={handleSelectAll}
          className="h-3.5 w-3.5"
        />
        <span className="text-[11px] font-medium">全选</span>
      </div>
      <div className="border-t border-border pt-1">
        {tree.map((node) => (
          <TreeNodeItem
            key={node.path}
            node={node}
            selectedPaths={selectedPaths}
            onToggle={handleToggle}
            activePreviewPath={activePreviewPath}
            onTogglePreview={onTogglePreview}
            previewContent={previewContent}
            isPreviewLoading={isPreviewLoading}
          />
        ))}
      </div>
    </div>
  );
}
