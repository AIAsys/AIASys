/**
 * 文件树行组件（展平虚拟滚动专用）
 * 只渲染单行，不递归子节点
 */

import React, { useRef, useMemo } from "react";
import { cn } from "@/lib/utils";
import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import type { WorkspaceFile } from "@/types/task";
import {
  type FileTreeNode,
  isImageFile,
  isLoadMoreRow,
  getLoadMoreParentPath,
} from "@/utils/fileTreeUtils";
import { appendAccessToken } from "@/utils/urlUtils";
import {
  WORKSPACE_FILE_DRAG_MIME,
  type WorkspaceFileReferenceDragPayload,
} from "@/utils/workspaceFileDrag";
import {
  ChevronRight,
  BookOpen,
  Database,
  FileCode,
  FileText,
  Folder,
  FolderOpen,
  Image as ImageIcon,
  Layout,
  MoreHorizontal,
  Network,
  Notebook,
  Presentation,
  ServerCog,
  Table,
} from "lucide-react";

interface FileTreeImageSlide {
  src: string;
  alt?: string;
  thumbnail?: string;
}

function isNotebookFile(filename: string): boolean {
  return filename.toLowerCase().endsWith(".ipynb");
}

function getDirectoryKind(node: FileTreeNode): string {
  return typeof node.meta?.directory_kind === "string"
    ? node.meta.directory_kind
    : "normal";
}

function isHeavyDirectory(node: FileTreeNode): boolean {
  return node.isDirectory && node.meta?.heavy === true;
}

function getHeavyDirectoryLabel(node: FileTreeNode): string {
  switch (getDirectoryKind(node)) {
    case "python_venv":
      return "Python 环境";
    case "python_dependency":
      return "Python 依赖";
    case "node_dependency":
      return "Node 依赖";
    default:
      return "大型目录";
  }
}

function getTreeNodeSelectionKey(node: FileTreeNode): string {
  return node.isDirectory
    ? `folder:${node.path}`
    : `file:${node.file?.name ?? node.path}`;
}

export interface FileTreeRowProps {
  node: FileTreeNode;
  level: number;
  sessionId?: string;
  token?: string;
  scope?: "current" | "global";
  imageSlides: readonly FileTreeImageSlide[];
  imageIndexMap: ReadonlyMap<string, number>;
  onOpenImagePreview: (slide: FileTreeImageSlide, startIndex: number) => void;
  expandedFolders: Set<string>;
  onToggleFolder: (path: string) => void;
  onTreeNodeSelect?: (node: FileTreeNode) => void;
  selectedItemKeys: ReadonlySet<string>;
  onNodeClick: (node: FileTreeNode, event: React.MouseEvent) => void;
  onOpenFileMenu: (file: WorkspaceFile, event: React.MouseEvent<HTMLElement>) => void;
  onOpenInMainCanvas?: (file: WorkspaceFile) => void;
  onEditInMainCanvas?: (file: WorkspaceFile) => void;
  onMoveFile?: (source: string, target: string) => Promise<boolean>;
  onRefreshFiles?: () => Promise<void>;
  dragOverFolder: string | null;
  onDragOverFolder?: (path: string | null) => void;
  draggingNode: string | null;
  onDragStartNode?: (path: string | null) => void;
  onOpenFolderMenu?: (node: FileTreeNode, event: React.MouseEvent<HTMLElement>) => void;
  onOpenFileCreate?: (folderPath: string) => void;
  onOpenFolderCreate?: (folderPath: string) => void;
  onLoadDirectoryChildren?: (node: FileTreeNode) => Promise<void>;
  onLoadMoreDirectoryChildren?: (node: FileTreeNode) => Promise<void>;
  loadingDirectoryPath: string | null;
  focusItemKey?: string | null;
  isTreeFocused?: boolean;
}

const FileTreeRowComponent: React.FC<FileTreeRowProps> = ({
  node,
  level,
  sessionId,
  token,
  scope = "current",
  imageSlides: _imageSlides,
  imageIndexMap,
  onOpenImagePreview,
  expandedFolders,
  onToggleFolder,
  onTreeNodeSelect,
  selectedItemKeys,
  onNodeClick,
  onOpenFileMenu,
  onOpenInMainCanvas,
  onEditInMainCanvas,
  onMoveFile,
  onRefreshFiles,
  dragOverFolder,
  onDragOverFolder,
  draggingNode,
  onDragStartNode,
  onOpenFolderMenu,
  onOpenFileCreate: _onOpenFileCreate,
  onOpenFolderCreate: _onOpenFolderCreate,
  onLoadDirectoryChildren,
  onLoadMoreDirectoryChildren,
  loadingDirectoryPath,
  focusItemKey,
  isTreeFocused = false,
}) => {
  const isExpanded = expandedFolders.has(node.path);
  const isSelected = selectedItemKeys.has(getTreeNodeSelectionKey(node));
  const isFocused = focusItemKey === getTreeNodeSelectionKey(node);
  const isImage = !node.isDirectory && isImageFile(node.name);
  const isHeavy = isHeavyDirectory(node);
  const isRuntimeMaterial = getDirectoryKind(node) === "runtime_material";
  const hasLoadedHeavyChildren =
    isHeavy && node.children && node.children.length > 0;
  const isLoadingChildren = loadingDirectoryPath === node.path;
  const hasMoreHeavyChildren =
    isHeavy &&
    typeof node.meta?.next_offset === "number" &&
    node.meta.has_more === true;
  const imageStartIndex = node.file
    ? (imageIndexMap.get(node.file.name) ?? 0)
    : 0;

  // 生成文件URL
  const fileUrl = useMemo(() => {
    if (!sessionId || !node.file) return "";
    const userId = getCurrentUserId();
    let url = `${API_ENDPOINTS.FILES_DOWNLOAD(userId, sessionId, node.file.name)}?user_id=${userId}`;
    if (token) {
      url = appendAccessToken(url, token);
    }
    return url;
  }, [sessionId, node.file, token]);

  /** 获取图标 */
  const iconNode = useMemo(() => {
    if (node.isDirectory) {
      if (isRuntimeMaterial) {
        return <ServerCog className="w-4 h-4 text-tertiary" />;
      }
      return isExpanded ? (
        <FolderOpen className="w-4 h-4 text-primary/80" />
      ) : (
        <Folder className="w-4 h-4 text-primary/60" />
      );
    }

    const ext = node.name.split(".").pop()?.toLowerCase();
    const iconClass = "w-3.5 h-3.5 text-muted-foreground";

    if (["png", "jpg", "jpeg", "gif", "svg", "webp"].includes(ext || "")) {
      return <ImageIcon className={iconClass} />;
    }
    if (["csv", "xlsx", "xls"].includes(ext || "")) {
      return <Table className={iconClass} />;
    }
    if (node.file?.resource_type === "knowledge") {
      return <BookOpen className={iconClass} />;
    }
    if (node.file?.resource_type === "graph") {
      return <Network className={iconClass} />;
    }
    if (node.file?.resource_type === "data_table") {
      return <Table className={iconClass} />;
    }
    if (
      node.file?.resource_type === "database" ||
      ["db", "sqlite", "sqlite3", "duckdb"].includes(ext || "")
    ) {
      return <Database className={iconClass} />;
    }
    if (["ppt", "pptx"].includes(ext || "")) {
      return <Presentation className={iconClass} />;
    }
    if (["ipynb"].includes(ext || "")) {
      return <Notebook className={iconClass} />;
    }
    if (
      ["py", "js", "ts", "tsx", "jsx", "html", "css", "json"].includes(
        ext || "",
      )
    ) {
      return <FileCode className={iconClass} />;
    }
    if (ext === "canvas") {
      return <Layout className={iconClass} />;
    }
    return <FileText className={iconClass} />;
  }, [node.isDirectory, node.name, node.file?.resource_type, isRuntimeMaterial, isExpanded]);

  /** 处理点击（文件夹或选中文件） */
  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (node.isDirectory || node.file) {
      onNodeClick(node, e);
      if (isHeavy && !hasLoadedHeavyChildren && onLoadDirectoryChildren) {
        void onLoadDirectoryChildren(node);
      }
    } else if (onTreeNodeSelect) {
      onTreeNodeSelect(node);
    }
  };

  /** 处理双击（在主画布打开） */
  const handleDoubleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!node.isDirectory && node.file) {
      if (isNotebookFile(node.file.name) && onEditInMainCanvas) {
        onEditInMainCanvas(node.file);
      } else if (onOpenInMainCanvas) {
        onOpenInMainCanvas(node.file);
      }
    }
  };

  const handleMenuOpen = (e: React.MouseEvent<HTMLElement>) => {
    e.stopPropagation();
    if (!node.file) return;
    onOpenFileMenu(node.file, e);
  };

  const handleFolderMenuOpen = (e: React.MouseEvent<HTMLElement>) => {
    e.stopPropagation();
    onOpenFolderMenu?.(node, e);
  };

  const isDragOver = dragOverFolder === node.path;
  const isDragging = draggingNode === node.path;

  const handleDragStart = (e: React.DragEvent<HTMLElement>) => {
    const dragPath = node.file ? node.file.name : node.path;
    onDragStartNode?.(dragPath);
    e.dataTransfer.effectAllowed = "copyMove";

    // 多选拖拽：如果拖拽的项在选中集合中且选中项 > 1，传递所有选中项
    const nodeKey = getTreeNodeSelectionKey(node);
    const isInSelection = selectedItemKeys.has(nodeKey);
    const shouldDragMultiple = isInSelection && selectedItemKeys.size > 1;

    if (shouldDragMultiple) {
      const allPaths: string[] = [];
      for (const key of selectedItemKeys) {
        if (key.startsWith("file:")) {
          allPaths.push(key.slice(5));
        } else if (key.startsWith("folder:")) {
          allPaths.push(key.slice(7));
        }
      }
      e.dataTransfer.setData(
        "application/x-aiasys-file-tree-move",
        JSON.stringify(allPaths),
      );
      e.dataTransfer.setData("text/plain", `${allPaths.length} 个文件/文件夹`);
    } else {
      e.dataTransfer.setData("application/x-aiasys-file-tree-move", dragPath);
      e.dataTransfer.setData("text/plain", dragPath);
    }

    // 构造统一的工作区文件引用拖拽数据
    const referencePaths: string[] = [];
    const prefix = scope === "global" ? "/global/" : "/workspace/";
    if (shouldDragMultiple) {
      for (const key of selectedItemKeys) {
        if (key.startsWith("file:")) {
          referencePaths.push(prefix + key.slice(5));
        } else if (key.startsWith("folder:")) {
          referencePaths.push(prefix + key.slice(7));
        }
      }
    } else {
      referencePaths.push(prefix + dragPath);
    }
    if (referencePaths.length > 0) {
      const payload: WorkspaceFileReferenceDragPayload = {
        scope,
        paths: referencePaths,
      };
      e.dataTransfer.setData(WORKSPACE_FILE_DRAG_MIME, JSON.stringify(payload));
    }

    const ghost = document.createElement("div");
    ghost.className =
      "flex items-center gap-2 rounded-md border border-border bg-background/90 px-3 py-2 text-xs text-foreground shadow-lg backdrop-blur aiasys-drag-ghost";
    ghost.style.position = "fixed";
    ghost.style.top = "-9999px";
    ghost.style.left = "-9999px";
    ghost.style.zIndex = "9999";
    ghost.style.pointerEvents = "none";
    const previousGhost = document.querySelector(".aiasys-drag-ghost");
    if (previousGhost && previousGhost.parentNode) {
      previousGhost.parentNode.removeChild(previousGhost);
    }
    const displayName = shouldDragMultiple
      ? `${selectedItemKeys.size} 个文件/文件夹`
      : (node.file?.name ?? node.name);
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    svg.setAttribute("width", "14");
    svg.setAttribute("height", "14");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("class", "shrink-0 text-muted-foreground");

    const path1 = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path1.setAttribute("d", "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z");
    svg.appendChild(path1);

    const path2 = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path2.setAttribute("d", "M14 2v4a2 2 0 0 0 2 2h4");
    svg.appendChild(path2);

    ghost.appendChild(svg);
    const nameSpan = document.createElement("span");
    nameSpan.className = "truncate font-mono max-w-[160px]";
    nameSpan.textContent = displayName;
    ghost.appendChild(nameSpan);
    document.body.appendChild(ghost);
    e.dataTransfer.setDragImage(ghost, 10, 10);
    requestAnimationFrame(() => {
      setTimeout(() => {
        if (ghost.parentNode) ghost.parentNode.removeChild(ghost);
      }, 0);
    });
  };

  const expandTimerRef = useRef<number | null>(null);

  const handleDragOver = (e: React.DragEvent<HTMLElement>) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";

    if (node.isDirectory) {
      if (dragOverFolder !== node.path) {
        onDragOverFolder?.(node.path);
      }
      // 悬停 800ms 后自动展开折叠的文件夹
      if (!isExpanded && !isHeavy && !expandTimerRef.current) {
        expandTimerRef.current = window.setTimeout(() => {
          onToggleFolder(node.path);
          expandTimerRef.current = null;
        }, 800);
      }
    } else {
      // 文件行：高亮当前行表示可以拖到此处（实际 drop 到父目录）
      if (dragOverFolder !== node.path) {
        onDragOverFolder?.(node.path);
      }
    }
  };

  const handleDragLeave = (e: React.DragEvent<HTMLElement>) => {
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    if (expandTimerRef.current) {
      clearTimeout(expandTimerRef.current);
      expandTimerRef.current = null;
    };
    onDragOverFolder?.(null);
  };

  const handleDrop = async (e: React.DragEvent<HTMLElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (expandTimerRef.current) {
      clearTimeout(expandTimerRef.current);
      expandTimerRef.current = null;
    }
    onDragOverFolder?.(null);
    onDragStartNode?.(null);

    const rawSource = e.dataTransfer.getData("application/x-aiasys-file-tree-move");
    if (!rawSource) return;

    // 尝试解析多选 JSON 格式
    let sources: string[];
    try {
      const parsed = JSON.parse(rawSource);
      if (Array.isArray(parsed)) {
        sources = parsed;
      } else {
        sources = [rawSource];
      }
    } catch {
      sources = [rawSource];
    }

    // 确定目标目录：如果是文件夹则直接作为 target，如果是文件则取其父目录
    let targetDir: string;
    if (node.isDirectory) {
      targetDir = node.path;
    } else {
      // 文件行：取父目录
      const lastSlash = node.path.lastIndexOf("/");
      targetDir = lastSlash >= 0 ? node.path.substring(0, lastSlash) : "";
    }

    // 逐个移动
    let anyOk = false;
    for (const source of sources) {
      if (source === targetDir) continue;
      if (targetDir && targetDir.startsWith(source + "/")) continue;

      const sourceName = source.split("/").pop() || source;
      const target = targetDir ? targetDir + "/" + sourceName : sourceName;

      if (target === source) continue;

      try {
        const ok = await onMoveFile?.(source, target);
        if (ok) anyOk = true;
      } catch {
        // 静默失败
      }
    }

    if (anyOk) {
      await onRefreshFiles?.();
    }
  };

  const indent = level * 12 + 8;

  // 缩进线：在 hover 时显示层级连线
  const indentGuides = level > 0 ? (
    <>
      {Array.from({ length: level }).map((_, i) => (
        <div
          key={`guide-${i}`}
          className="absolute top-0 h-full w-px opacity-0 group-hover:opacity-100 transition-opacity bg-border/60"
          style={{ left: `${i * 12 + 4}px` }}
        />
      ))}
    </>
  ) : null;

  // 加载更多占位行
  if (isLoadMoreRow(node)) {
    const parentPath = getLoadMoreParentPath(node);
    if (!parentPath) return null;
    const parentHeavyLabel = getHeavyDirectoryLabel(node);
    return (
      <div
        className="flex items-center gap-2 py-1 pr-2 text-[11px] text-muted-foreground"
        style={{ paddingLeft: `${indent}px` }}
      >
        <span className="shrink-0 rounded-full border border-warning/20 bg-warning-container px-1.5 py-0.5 text-[10px] font-medium text-on-warning-container">
          {isLoadingChildren ? "加载中" : parentHeavyLabel}
        </span>
        <span>已加载预览，</span>
        {hasMoreHeavyChildren && onLoadMoreDirectoryChildren ? (
          <button
            type="button"
            className="rounded-md border border-border bg-background px-2 py-0.5 text-[11px] font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isLoadingChildren}
            onClick={(event) => {
              event.stopPropagation();
              // 构造一个模拟的 parent node 来触发加载
              const parentNode: FileTreeNode = {
                name: parentPath.split("/").pop() || parentPath,
                path: parentPath,
                isDirectory: true,
                meta: node.meta,
                children: node.children,
              };
              void onLoadMoreDirectoryChildren(parentNode);
            }}
          >
            {isLoadingChildren ? "加载中" : "加载更多"}
          </button>
        ) : null}
      </div>
    );
  }

  const menuButton = node.file ? (
    <button
      type="button"
      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-muted-foreground opacity-0 transition-colors hover:bg-muted hover:text-foreground group-hover:opacity-100 focus:opacity-100"
      onClick={handleMenuOpen}
      title="文件操作"
      aria-label={`打开 ${node.name} 的文件操作菜单`}
    >
      <MoreHorizontal className="h-3.5 w-3.5" />
    </button>
  ) : node.isDirectory ? (
    <button
      type="button"
      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-muted-foreground opacity-0 transition-colors hover:bg-muted hover:text-foreground group-hover:opacity-100 focus:opacity-100"
      onClick={handleFolderMenuOpen}
      title="文件夹操作"
      aria-label={`打开 ${node.name} 的文件夹操作菜单`}
    >
      <MoreHorizontal className="h-3.5 w-3.5" />
    </button>
  ) : null;

  // 统一行高 28px 的容器样式
  const rowBaseClass = cn(
    "group flex items-center gap-1.5 h-7 pr-2 cursor-pointer",
    "transition-colors text-sm rounded-r-md mr-1 select-none relative",
    isSelected
      ? "bg-primary/10 text-primary border-l-2 border-primary -ml-[2px]"
      : isDragOver && node.isDirectory
        ? "bg-primary/10 border-l-2 border-primary -ml-[2px]"
        : isDragOver && !node.isDirectory
          ? "border-b-2 border-primary"
          : isDragging
            ? "opacity-50 border-l-2 border-transparent -ml-[2px]"
            : "text-foreground/80 hover:bg-muted/50 border-l-2 border-transparent -ml-[2px]",
    // Focus ring：键盘焦点框（与 selection 高亮分离）
    isFocused &&
      (isTreeFocused
        ? "ring-1 ring-inset ring-primary/50"
        : "ring-1 ring-inset ring-muted-foreground/30")
  );

  // 图片文件：统一行高 28px，缩略图缩小为 20x20
  if (isImage && fileUrl) {
    return (
      <div
        data-testid="workspace-file-tree-file-node"
        data-file-path={node.file?.name}
        data-selected={isSelected ? "true" : "false"}
        aria-selected={isSelected}
        className={rowBaseClass}
        style={{ paddingLeft: `${indent}px` }}
        draggable
        onClick={handleClick}
        onDoubleClick={handleDoubleClick}
        onContextMenu={
          node.isDirectory
            ? handleFolderMenuOpen
            : node.file
              ? handleMenuOpen
              : undefined
        }
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {indentGuides}
        {/* 缩略图 - 点击打开 Lightbox，缩小为 20x20 */}
        <button
          type="button"
          className="flex-shrink-0 w-5 h-5 overflow-hidden rounded-sm border border-border bg-muted p-0 transition-colors hover:border-primary/50 focus:outline-none focus:ring-1 focus:ring-ring"
          onClick={(event) => {
            event.stopPropagation();
            onOpenImagePreview(
              {
                src: fileUrl,
                alt: node.file?.name ?? node.name,
                thumbnail: fileUrl,
              },
              imageStartIndex,
            );
          }}
          title="点击放大预览"
          aria-label={`放大预览 ${node.name}`}
        >
          <img
            src={fileUrl}
            alt={node.name}
            className="h-full w-full cursor-zoom-in select-none object-cover"
            draggable={false}
            loading="lazy"
            decoding="async"
          />
        </button>

        {/* 文件名 */}
        <span className="truncate font-mono flex-1 text-sm leading-none pt-0.5">
          {node.name}
        </span>

        {/* New 标签 */}
        {node.file?.isNew && (
          <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse flex-shrink-0" />
        )}

        {menuButton}
      </div>
    );
  }

  // 非图片文件/文件夹：统一行高 28px
  return (
    <div
      data-testid={
        node.isDirectory
          ? "workspace-file-tree-folder-node"
          : "workspace-file-tree-file-node"
      }
      data-file-path={node.file?.name ?? node.path}
      data-selected={isSelected ? "true" : "false"}
      aria-selected={isSelected}
      className={rowBaseClass}
      style={{ paddingLeft: `${indent}px` }}
      draggable
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
      onContextMenu={
        node.isDirectory
          ? handleFolderMenuOpen
          : node.file
            ? handleMenuOpen
            : undefined
      }
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {indentGuides}
      {/* 展开箭头 (仅文件夹) - 改用 transform 旋转，避免 DOM 重建 */}
      <div className="w-4 h-4 flex items-center justify-center flex-shrink-0 opacity-50">
        {node.isDirectory && (
          <ChevronRight
            className={cn(
              "w-3 h-3 transition-transform duration-150 ease-out",
              isExpanded && "rotate-90"
            )}
          />
        )}
      </div>

      {/* 图标 */}
      <div
        className={cn(
          "flex-shrink-0",
          node.isDirectory ? "text-primary" : "text-muted-foreground"
        )}
      >
        {iconNode}
      </div>

      {/* 文件名 */}
      <span className="truncate font-mono flex-1 leading-none pt-0.5">
        {node.name}
      </span>

      {isHeavy ? (
        <span className="ml-1 shrink-0 rounded-full border border-warning/20 bg-warning-container px-1.5 py-0.5 text-[10px] font-medium text-on-warning-container">
          {isLoadingChildren ? "加载中" : getHeavyDirectoryLabel(node)}
        </span>
      ) : null}

      {/* New 标签 */}
      {node.file?.isNew && (
        <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse flex-shrink-0 ml-1" />
      )}

      {!node.isDirectory ? menuButton : null}
    </div>
  );
};

export const FileTreeRow = React.memo(FileTreeRowComponent, (prev, next) => {
  // 节点数据或层级变化
  if (prev.node !== next.node) return false;
  if (prev.level !== next.level) return false;
  if (prev.sessionId !== next.sessionId) return false;
  if (prev.token !== next.token) return false;

  // 展开状态变化
  const prevExpanded = prev.expandedFolders.has(prev.node.path);
  const nextExpanded = next.expandedFolders.has(prev.node.path);
  if (prevExpanded !== nextExpanded) return false;

  // 选中状态变化
  const prevKey = getTreeNodeSelectionKey(prev.node);
  const nextKey = getTreeNodeSelectionKey(next.node);
  const prevSelected = prev.selectedItemKeys.has(prevKey);
  const nextSelected = next.selectedItemKeys.has(nextKey);
  if (prevSelected !== nextSelected) return false;

  // 拖拽状态只影响当前节点
  const prevDragOver = prev.dragOverFolder === prev.node.path;
  const nextDragOver = next.dragOverFolder === prev.node.path;
  if (prevDragOver !== nextDragOver) return false;
  const prevDragging = prev.draggingNode === prev.node.path;
  const nextDragging = next.draggingNode === prev.node.path;
  if (prevDragging !== nextDragging) return false;

  // 目录加载状态同样只影响正在加载的目录节点
  const prevLoading = prev.loadingDirectoryPath === prev.node.path;
  const nextLoading = next.loadingDirectoryPath === prev.node.path;
  if (prevLoading !== nextLoading) return false;

  // focus 状态变化
  const prevFocused = prev.focusItemKey === prevKey;
  const nextFocused = next.focusItemKey === nextKey;
  if (prevFocused !== nextFocused) return false;
  if (prev.isTreeFocused !== next.isTreeFocused) return false;

  // 图片集合变化：比较内容而非引用
  if (prev.imageIndexMap.size !== next.imageIndexMap.size) return false;
  for (const [key, val] of prev.imageIndexMap) {
    if (next.imageIndexMap.get(key) !== val) return false;
  }

  return true;
});
