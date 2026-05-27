/**
 * 文件树浏览器（展平虚拟滚动架构）
 * 对标 VS Code Explorer 交互体验：
 * - 整树展平为列表，统一参与虚拟滚动
 * - 固定行高 28px + 绝对定位 + transform translateY
 * - 展开箭头用 CSS transform rotate-90，避免 DOM 重建
 * - useTransition 包裹展开/折叠，不阻塞 UI
 *
 * 图片文件特性：
 * - 显示小缩略图（inline preview，20x20）
 * - 点击缩略图使用统一图片放大组件预览
 */

import { useAuthContext } from "@/contexts/AuthContext";
import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import type { WorkspaceFile } from "@/types/task";
import { apiRequest } from "@/lib/api/httpClient";
import {
  type FileTreeNode,
  buildFileTree,
  filterFileTree,
  flattenFileTree,
  isImageFile,
  isLoadMoreRow,
} from "@/utils/fileTreeUtils";
import { appendAccessToken } from "@/utils/urlUtils";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useVirtualizer } from "@tanstack/react-virtual";
import React, { useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";
import { writeTextToClipboard } from "@/utils/clipboardText";
import { FileContextMenu, FolderContextMenu } from "./FileTreeContextMenus";
import { FileTreeRow } from "./FileTreeRow";

const ROW_HEIGHT = 28;

interface FileTreeImageSlide {
  src: string;
  alt?: string;
  thumbnail?: string;
}

interface FileTreeImageLightboxViewerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  slides: readonly FileTreeImageSlide[];
  startIndex?: number;
  zoomMargin?: number;
  zoomable?: boolean;
}

const LazyImageLightboxViewer = React.lazy(async () => {
  const module = await import("@/components/ui/image-lightbox");
  return {
    default:
      module.ImageLightboxViewer as React.ComponentType<FileTreeImageLightboxViewerProps>,
  };
});

function isNotebookFile(filename: string): boolean {
  return filename.toLowerCase().endsWith(".ipynb");
}

function isMarkdownFile(filename: string) {
  const ext = filename.lastIndexOf(".") >= 0 ? filename.slice(filename.lastIndexOf(".")).toLowerCase() : "";
  return [".md", ".markdown"].includes(ext);
}

const FILE_MENU_WIDTH = 224;
const FILE_MENU_HEIGHT = 492;

type ExportFormat = "md" | "docx" | "pdf";

interface FileMenuState {
  file: WorkspaceFile;
  x: number;
  y: number;
  /** 多选时，右键的项在选中集合中，传递所有选中文件 */
  multiSelectedFiles?: WorkspaceFile[];
  /** 多选时，传递所有选中文件夹路径 */
  multiSelectedFolders?: string[];
}

interface FolderMenuState {
  path: string;
  name: string;
  absolutePath?: string | null;
  x: number;
  y: number;
  /** 多选时，右键的项在选中集合中，传递所有选中文件 */
  multiSelectedFiles?: WorkspaceFile[];
  /** 多选时，传递所有选中文件夹路径 */
  multiSelectedFolders?: string[];
}

interface CopyPathOption {
  label: string;
  value: string;
  icon: "path" | "link";
}

export interface FileTreeClipboardItem {
  kind: "file" | "folder";
  sourcePath: string;
  action: "copy" | "cut";
}

function getFileSelectionKey(filename: string): string {
  return `file:${filename}`;
}

function getFolderSelectionKey(path: string): string {
  return `folder:${path}`;
}

function dedupeCopyPathOptions(options: CopyPathOption[]): CopyPathOption[] {
  const seen = new Set<string>();
  const result: CopyPathOption[] = [];
  for (const option of options) {
    const value = option.value.trim();
    if (!value || seen.has(value)) continue;
    seen.add(value);
    result.push({ ...option, value });
  }
  return result;
}

function getAncestorFolderPaths(filename: string): string[] {
  const parts = filename.split("/").filter(Boolean);
  if (parts.length <= 1) {
    return [];
  }
  return parts.slice(0, -1).map((_, index) => parts.slice(0, index + 1).join("/"));
}

function toBrowserAbsoluteUrl(url: string): string {
  if (!url) return "";
  if (typeof window === "undefined") return url;
  try {
    return new URL(url, window.location.origin).toString();
  } catch {
    return url;
  }
}

interface FileTreeViewProps {
  files?: WorkspaceFile[];
  treeData?: FileTreeNode[];
  sessionId?: string;
  searchQuery?: string;
  onFileSelect?: (file: WorkspaceFile) => void;
  onTreeNodeSelect?: (node: FileTreeNode) => void;
  selectedFileName?: string;
  onDeleteFile?: (filename: string) => Promise<boolean>;
  onOpenInMainCanvas?: (file: WorkspaceFile) => void;
  onEditInMainCanvas?: (file: WorkspaceFile) => void;
  onOpenFileHistory?: (file: WorkspaceFile) => void;
  onExportMarkdownFile?: (filename: string, format: ExportFormat) => Promise<void>;
  onMoveFile?: (source: string, target: string) => Promise<boolean>;
  onRefreshFiles?: () => Promise<void>;
  collapseAllSignal?: number;
  expandFirstLevel?: boolean;
  onOpenFileCreate?: (folderPath: string) => void;
  onOpenFolderCreate?: (folderPath: string) => void;
  onDeleteFolder?: (folderPath: string) => Promise<boolean>;
  getDownloadUrl?: (filename: string) => string;
  getCopyPath?: (file: WorkspaceFile) => string;
  getFolderCopyPath?: (folderPath: string) => string;
  clipboardItem?: FileTreeClipboardItem | null;
  onClipboardItemChange?: (item: FileTreeClipboardItem | null) => void;
  onCopyFileSystemEntry?: (source: string, target: string) => Promise<boolean>;
  onPasteComplete?: (target: string) => void;
  workspaceId?: string;
}

export const FileTreeView: React.FC<FileTreeViewProps> = ({
  files,
  treeData: externalTreeData,
  sessionId,
  searchQuery = "",
  onFileSelect,
  onTreeNodeSelect,
  selectedFileName,
  onDeleteFile,
  onDeleteFolder,
  onOpenInMainCanvas,
  onEditInMainCanvas,
  onOpenFileHistory,
  onExportMarkdownFile,
  onMoveFile,
  onRefreshFiles,
  collapseAllSignal = 0,
  expandFirstLevel = false,
  onOpenFileCreate,
  onOpenFolderCreate,
  getDownloadUrl: customGetDownloadUrl,
  getCopyPath,
  getFolderCopyPath,
  clipboardItem,
  onClipboardItemChange,
  onCopyFileSystemEntry,
  onPasteComplete,
  workspaceId,
}) => {
  const { session } = useAuthContext();
  const token = session?.token;
  const menuRef = useRef<HTMLDivElement | null>(null);

  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const [fileMenu, setFileMenu] = useState<FileMenuState | null>(null);
  const [folderMenu, setFolderMenu] = useState<FolderMenuState | null>(null);
  const [deletingFileName, setDeletingFileName] = useState<string | null>(null);
  const deletingFileNameRef = useRef<string | null>(null);
  const [deletingFolderPath, setDeletingFolderPath] = useState<string | null>(null);
  const deletingFolderPathRef = useRef<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<
    | { kind: "file"; file: WorkspaceFile; isCritical?: boolean }
    | { kind: "folder"; path: string; isCritical?: boolean }
    | null
  >(null);
  const [criticalConfirmText, setCriticalConfirmText] = useState("");
  const CRITICAL_CONFIRM_PHRASE = "我已了解风险，确认删除";
  const [exportingFile, setExportingFile] = useState<{
    filename: string;
    format: ExportFormat;
  } | null>(null);
  const exportingFileRef = useRef<{ filename: string; format: ExportFormat } | null>(null);
  const [dragOverFolderPath, setDragOverFolderPath] = useState<string | null>(null);
  const [draggingPath, setDraggingPath] = useState<string | null>(null);
  const [loadedDirectoryChildren, setLoadedDirectoryChildren] = useState<
    Record<string, FileTreeNode[]>
  >({});
  const [loadedDirectoryMeta, setLoadedDirectoryMeta] = useState<
    Record<string, Record<string, unknown>>
  >({});
  const [loadingDirectoryPath, setLoadingDirectoryPath] = useState<string | null>(null);
  const [imagePreview, setImagePreview] = useState<{
    slide: FileTreeImageSlide;
    startIndex: number;
  } | null>(null);
  const [copyFailure, setCopyFailure] = useState<{
    text: string;
    reason: string;
  } | null>(null);
  const [multiSelectedItemKeys, setMultiSelectedItemKeys] = useState<Set<string>>(
    () => new Set(selectedFileName ? [getFileSelectionKey(selectedFileName)] : [])
  );
  const [anchorItemKey, setAnchorItemKey] = useState<string | null>(null);
  const [focusItemKey, setFocusItemKey] = useState<string | null>(null);
  const [isTreeFocused, setIsTreeFocused] = useState(false);
  const lastSyncedSelectedFileNameRef = useRef<string | undefined>(selectedFileName);

  const [, startTransition] = useTransition();

  const treeData = useMemo(() => {
    if (externalTreeData) {
      if (searchQuery) {
        return filterFileTree(externalTreeData, searchQuery);
      }
      return externalTreeData;
    }
    const sourceFiles = files || [];
    const tree = buildFileTree(sourceFiles);
    if (searchQuery) {
      return filterFileTree(tree, searchQuery);
    }
    return tree;
  }, [externalTreeData, files, searchQuery]);

  const treeDataWithLoadedChildren = useMemo(() => {
    const attachChildren = (nodes: FileTreeNode[]): FileTreeNode[] =>
      nodes.map((node) => {
        const loadedChildren = loadedDirectoryChildren[node.path];
        const loadedMeta = loadedDirectoryMeta[node.path];
        const children = node.children ? attachChildren(node.children) : undefined;
        if (loadedChildren) {
          return {
            ...node,
            meta: loadedMeta ? { ...(node.meta ?? {}), ...loadedMeta } : node.meta,
            children: attachChildren(loadedChildren),
          };
        }
        return children || loadedMeta
          ? {
              ...node,
              meta: loadedMeta ? { ...(node.meta ?? {}), ...loadedMeta } : node.meta,
              children,
            }
          : node;
      });
    return attachChildren(treeData);
  }, [loadedDirectoryChildren, loadedDirectoryMeta, treeData]);

  // 整树展平为列表，参与统一虚拟滚动
  const flatNodes = useMemo(
    () => flattenFileTree(treeDataWithLoadedChildren, expandedFolders),
    [treeDataWithLoadedChildren, expandedFolders],
  );

  // 文件列表变化时清理已不存在目录的展开状态
  useEffect(() => {
    setExpandedFolders((prev) => {
      const validPaths = new Set<string>();
      const collectPaths = (nodes: FileTreeNode[]) => {
        for (const node of nodes) {
          if (node.isDirectory) {
            validPaths.add(node.path);
            if (node.children) collectPaths(node.children);
          }
        }
      };
      collectPaths(treeDataWithLoadedChildren);
      const next = new Set<string>();
      for (const path of prev) {
        if (validPaths.has(path)) {
          next.add(path);
        }
      }
      return next;
    });
  }, [treeDataWithLoadedChildren]);

  const closeFileMenu = useCallback(() => {
    setFileMenu(null);
  }, []);

  const closeFolderMenu = useCallback(() => {
    setFolderMenu(null);
  }, []);

  const loadDirectoryChildrenPage = useCallback(
    async (node: FileTreeNode, offset: number) => {
      if (!workspaceId) return;
      const isHeavy =
        node.isDirectory && node.meta?.heavy === true;
      if (!isHeavy) return;

      setLoadingDirectoryPath(node.path);
      try {
        const response = await apiRequest<{
          nodes: Array<{
            name: string;
            path: string;
            absolute_path?: string | null;
            node_type: "directory" | "resource";
            resource_type?: string | null;
            meta?: Record<string, unknown>;
            children?: Array<unknown>;
          }>;
          total: number;
          limit: number;
          offset: number;
          has_more: boolean;
          next_offset?: number | null;
        }>(
          API_ENDPOINTS.WORKSPACE_RESOURCES_TREE_CHILDREN(workspaceId, node.path),
          { query: { limit: 50, offset } },
        );
        const convertNodes = (
          nodes: typeof response.nodes,
        ): FileTreeNode[] =>
          nodes.map((item) => ({
            name: item.name,
            path: item.path,
            absolutePath: item.absolute_path,
            isDirectory: item.node_type === "directory",
            children: item.children
              ? convertNodes(
                  item.children as Array<{
                    name: string;
                    path: string;
                    absolute_path?: string | null;
                    node_type: "directory" | "resource";
                    resource_type?: string | null;
                    meta?: Record<string, unknown>;
                    children?: Array<unknown>;
                  }>,
                )
              : undefined,
            meta: item.meta,
            file:
              item.node_type !== "directory"
                ? {
                    name: item.path,
                    size: 0,
                    mtime: "",
                    absolute_path: item.absolute_path,
                    resource_type: item.resource_type ?? undefined,
                    meta: item.meta,
                  }
                : undefined,
          }));
        const nextChildren = convertNodes(response.nodes);
        setLoadedDirectoryChildren((current) => ({
          ...current,
          [node.path]:
            offset === 0
              ? nextChildren
              : [...(current[node.path] ?? []), ...nextChildren],
        }));
        setLoadedDirectoryMeta((current) => ({
          ...current,
          [node.path]: {
            total: response.total,
            limit: response.limit,
            loaded_count:
              offset === 0
                ? nextChildren.length
                : (current[node.path]?.loaded_count as number ?? 0) + nextChildren.length,
            has_more: response.has_more,
            next_offset: response.next_offset ?? null,
          },
        }));
      } catch (error) {
        if (import.meta.env.DEV) {
          console.warn("加载依赖目录预览失败", error);
        }
      } finally {
        setLoadingDirectoryPath((current) => (current === node.path ? null : current));
      }
    },
    [workspaceId],
  );

  const loadDirectoryChildren = useCallback(
    async (node: FileTreeNode) => {
      if (loadedDirectoryChildren[node.path]) {
        return;
      }
      await loadDirectoryChildrenPage(node, 0);
    },
    [loadDirectoryChildrenPage, loadedDirectoryChildren],
  );

  const loadMoreDirectoryChildren = useCallback(
    async (node: FileTreeNode) => {
      const nextOffset = node.meta?.next_offset;
      if (typeof nextOffset !== "number") {
        return;
      }
      await loadDirectoryChildrenPage(node, nextOffset);
    },
    [loadDirectoryChildrenPage],
  );

  // useTransition 包裹展开/折叠，不阻塞 UI
  const handleToggleFolder = useCallback((path: string) => {
    startTransition(() => {
      setExpandedFolders((prev) => {
        const next = new Set(prev);
        if (next.has(path)) {
          next.delete(path);
        } else {
          next.add(path);
        }
        return next;
      });
    });
  }, []);

  // 从多选集合中提取文件和文件夹列表
  const getMultiSelectionInfo = useCallback(() => {
    if (multiSelectedItemKeys.size <= 1) return null;
    const selectedFiles: WorkspaceFile[] = [];
    const selectedFolders: string[] = [];
    for (const key of multiSelectedItemKeys) {
      if (key.startsWith("file:")) {
        const filename = key.slice(5);
        const fn = flatNodes.find(
          (f) => f.node.file?.name === filename,
        );
        if (fn?.node.file) {
          selectedFiles.push(fn.node.file);
        }
      } else if (key.startsWith("folder:")) {
        selectedFolders.push(key.slice(7));
      }
    }
    return { selectedFiles, selectedFolders };
  }, [multiSelectedItemKeys, flatNodes]);

  const openFileMenu = useCallback(
    (file: WorkspaceFile, event: React.MouseEvent<HTMLElement>) => {
      event.preventDefault();
      event.stopPropagation();

      const viewportWidth = typeof window === "undefined" ? 1024 : window.innerWidth;
      const viewportHeight = typeof window === "undefined" ? 768 : window.innerHeight;
      const triggerRect = event.currentTarget.getBoundingClientRect();
      const rawX = event.type === "contextmenu" ? event.clientX : triggerRect.right;
      const rawY = event.type === "contextmenu" ? event.clientY : triggerRect.bottom + 4;
      const x = Math.min(Math.max(8, rawX), Math.max(8, viewportWidth - FILE_MENU_WIDTH - 8));
      const y = Math.min(Math.max(8, rawY), Math.max(8, viewportHeight - FILE_MENU_HEIGHT - 8));

      // 判断右键的文件是否在多选集合中
      const fileKey = getFileSelectionKey(file.name);
      const isInSelection = multiSelectedItemKeys.has(fileKey) && multiSelectedItemKeys.size > 1;
      const multi = isInSelection ? getMultiSelectionInfo() : null;

      setFileMenu({
        file,
        x,
        y,
        multiSelectedFiles: multi?.selectedFiles.length ? multi.selectedFiles : undefined,
        multiSelectedFolders: multi?.selectedFolders.length ? multi.selectedFolders : undefined,
      });
    },
    [multiSelectedItemKeys, getMultiSelectionInfo],
  );

  const openFolderMenu = useCallback(
    (folderNode: FileTreeNode, event: React.MouseEvent<HTMLElement>) => {
      event.preventDefault();
      event.stopPropagation();

      const viewportWidth = typeof window === "undefined" ? 1024 : window.innerWidth;
      const viewportHeight = typeof window === "undefined" ? 768 : window.innerHeight;
      const triggerRect = event.currentTarget.getBoundingClientRect();
      const rawX = event.type === "contextmenu" ? event.clientX : triggerRect.right;
      const rawY = event.type === "contextmenu" ? event.clientY : triggerRect.bottom + 4;
      const x = Math.min(Math.max(8, rawX), Math.max(8, viewportWidth - FILE_MENU_WIDTH - 8));
      const y = Math.min(Math.max(8, rawY), Math.max(8, viewportHeight - FILE_MENU_HEIGHT - 8));

      // 判断右键的文件夹是否在多选集合中
      const folderKey = getFolderSelectionKey(folderNode.path);
      const isInSelection = multiSelectedItemKeys.has(folderKey) && multiSelectedItemKeys.size > 1;
      const multi = isInSelection ? getMultiSelectionInfo() : null;

      setFolderMenu({
        path: folderNode.path,
        name: folderNode.name,
        absolutePath: folderNode.absolutePath,
        x,
        y,
        multiSelectedFiles: multi?.selectedFiles.length ? multi.selectedFiles : undefined,
        multiSelectedFolders: multi?.selectedFolders.length ? multi.selectedFolders : undefined,
      });
    },
    [multiSelectedItemKeys, getMultiSelectionInfo],
  );

  const getDownloadUrl = useCallback(
    (filename: string) => {
      if (customGetDownloadUrl) {
        return customGetDownloadUrl(filename);
      }
      if (!sessionId) {
        return "";
      }
      const userId = getCurrentUserId();
      let url = `${API_ENDPOINTS.FILES_DOWNLOAD(userId, sessionId, filename)}?user_id=${userId}`;
      if (token) {
        url = appendAccessToken(url, token);
      }
      return url;
    },
    [customGetDownloadUrl, sessionId, token],
  );

  const getFileCopyPathOptions = useCallback(
    (file: WorkspaceFile): CopyPathOption[] => {
      const relativePath = file.name;
      const resourcePath = getCopyPath?.(file) ?? relativePath;
      const downloadUrl = toBrowserAbsoluteUrl(getDownloadUrl(file.name));
      return dedupeCopyPathOptions([
        {
          label: "复制绝对路径",
          value: file.absolute_path ?? "",
          icon: "path",
        },
        { label: "复制资源路径", value: resourcePath, icon: "path" },
        { label: "复制相对路径", value: relativePath, icon: "path" },
        { label: "复制链接", value: downloadUrl, icon: "link" },
      ]);
    },
    [getCopyPath, getDownloadUrl],
  );

  const getFolderCopyPathOptions = useCallback(
    (folderPath: string, absolutePath?: string | null): CopyPathOption[] => {
      const logicalPath = getFolderCopyPath?.(folderPath) ?? folderPath;
      return dedupeCopyPathOptions([
        { label: "复制绝对路径", value: absolutePath ?? "", icon: "path" },
        { label: "复制资源路径", value: logicalPath, icon: "path" },
        { label: "复制相对路径", value: folderPath, icon: "path" },
      ]);
    },
    [getFolderCopyPath],
  );

  const handleCopyText = useCallback(
    async (value: string, menuKind: "file" | "folder") => {
      const result = await writeTextToClipboard(value);
      if (!result.ok) {
        if (import.meta.env.DEV) {
          console.warn("复制路径失败", result.error ?? result.reason);
        }
        setCopyFailure({
          text: value,
          reason:
            result.reason === "denied"
              ? "浏览器拒绝了剪贴板写入权限。"
              : "当前浏览器没有完成剪贴板写入。",
        });
      }
      if (menuKind === "file") {
        closeFileMenu();
      } else {
        closeFolderMenu();
      }
    },
    [closeFileMenu, closeFolderMenu],
  );

  const handleRetryCopyText = useCallback(async () => {
    if (!copyFailure) return;
    const result = await writeTextToClipboard(copyFailure.text);
    if (result.ok) {
      setCopyFailure(null);
      return;
    }
    setCopyFailure((current) =>
      current
        ? {
            ...current,
            reason:
              result.reason === "denied"
                ? "浏览器仍然拒绝剪贴板写入权限。"
                : "重试复制失败，请在下方选中文本后使用系统复制。",
          }
        : current,
    );
  }, [copyFailure]);

  const rememberClipboardItem = useCallback(
    (item: FileTreeClipboardItem) => {
      onClipboardItemChange?.(item);
      closeFileMenu();
      closeFolderMenu();
    },
    [closeFileMenu, closeFolderMenu, onClipboardItemChange],
  );

  const pasteClipboardItem = useCallback(
    async (targetFolderPath: string) => {
      if (!clipboardItem) return;
      const sourceName =
        clipboardItem.sourcePath.split("/").filter(Boolean).pop() ??
        clipboardItem.sourcePath;
      const normalizedTargetFolder = targetFolderPath.replace(/^\/+|\/+$/g, "");
      const target = normalizedTargetFolder
        ? `${normalizedTargetFolder}/${sourceName}`
        : sourceName;
      const ok =
        clipboardItem.action === "cut"
          ? await onMoveFile?.(clipboardItem.sourcePath, target)
          : await onCopyFileSystemEntry?.(clipboardItem.sourcePath, target);
      if (!ok) return;
      if (clipboardItem.action === "cut") {
        onClipboardItemChange?.(null);
      }
      await onRefreshFiles?.();
      onPasteComplete?.(target);
      closeFolderMenu();
    },
    [
      clipboardItem,
      closeFolderMenu,
      onClipboardItemChange,
      onCopyFileSystemEntry,
      onMoveFile,
      onPasteComplete,
      onRefreshFiles,
    ],
  );

  const isCriticalPath = useCallback((path: string) => {
    return path.includes(".aiasys");
  }, []);

  const requestDeleteFile = useCallback(
    (file: WorkspaceFile) => {
      closeFileMenu();
      const critical = isCriticalPath(file.name) || (file.absolute_path ? isCriticalPath(file.absolute_path) : false);
      setDeleteConfirm({ kind: "file", file, isCritical: critical });
    },
    [closeFileMenu, isCriticalPath],
  );

  const requestDeleteFolder = useCallback(
    (folderPath: string) => {
      closeFolderMenu();
      setDeleteConfirm({ kind: "folder", path: folderPath, isCritical: isCriticalPath(folderPath) });
    },
    [closeFolderMenu, isCriticalPath],
  );

  // 批量删除（多选右键菜单触发）
  const requestDeleteMultiple = useCallback(
    async (files: WorkspaceFile[], folders: string[]) => {
      let anyOk = false;
      for (const f of files) {
        try {
          const ok = await onDeleteFile?.(f.name);
          if (ok) anyOk = true;
        } catch {
          // 静默失败
        }
      }
      if (onDeleteFolder) {
        for (const p of folders) {
          try {
            const ok = await onDeleteFolder(p);
            if (ok) anyOk = true;
          } catch {
            // 静默失败
          }
        }
      }
      setMultiSelectedItemKeys(new Set());
      setAnchorItemKey(null);
      if (anyOk) {
        await onRefreshFiles?.();
      }
    },
    [onDeleteFile, onDeleteFolder, onRefreshFiles],
  );

  const executeDelete = useCallback(async () => {
    if (!deleteConfirm) return;
    if (deleteConfirm.kind === "file") {
      const file = deleteConfirm.file;
      if (!onDeleteFile || deletingFileNameRef.current) {
        setDeleteConfirm(null);
        return;
      }
      deletingFileNameRef.current = file.name;
      setDeletingFileName(file.name);
      try {
        await onDeleteFile(file.name);
      } finally {
        deletingFileNameRef.current = null;
        setDeletingFileName(null);
      }
    } else {
      const folderPath = deleteConfirm.path;
      if (!onDeleteFolder || deletingFolderPathRef.current) {
        setDeleteConfirm(null);
        return;
      }
      deletingFolderPathRef.current = folderPath;
      setDeletingFolderPath(folderPath);
      try {
        await onDeleteFolder(folderPath);
      } finally {
        deletingFolderPathRef.current = null;
        setDeletingFolderPath(null);
      }
    }
    setDeleteConfirm(null);
  }, [deleteConfirm, onDeleteFile, onDeleteFolder]);

  const handleExportFile = useCallback(
    async (file: WorkspaceFile, format: ExportFormat) => {
      if (!onExportMarkdownFile || exportingFileRef.current) {
        return;
      }

      closeFileMenu();
      exportingFileRef.current = { filename: file.name, format };
      setExportingFile({ filename: file.name, format });
      try {
        await onExportMarkdownFile(file.name, format);
      } finally {
        exportingFileRef.current = null;
        setExportingFile(null);
      }
    },
    [closeFileMenu, onExportMarkdownFile],
  );

  useEffect(() => {
    if (!fileMenu) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (menuRef.current?.contains(event.target as Node)) return;
      setFileMenu(null);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFileMenu(null);
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [fileMenu]);

  useEffect(() => {
    if (!folderMenu) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (menuRef.current?.contains(event.target as Node)) return;
      setFolderMenu(null);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFolderMenu(null);
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [folderMenu]);

  const filesRef = useRef(files);
  filesRef.current = files;

  const imageFilesKey = useMemo(() => {
    if (!files) return "";
    return files
      .filter((f) => isImageFile(f.name))
      .map((f) => f.name)
      .sort()
      .join("\x00");
  }, [files]);

  const imageSlides = useMemo<readonly FileTreeImageSlide[]>(() => {
    if (!sessionId) return [];
    const userId = getCurrentUserId();
    return (filesRef.current || [])
      .filter((file) => isImageFile(file.name))
      .map((file) => {
        let url = `${API_ENDPOINTS.FILES_DOWNLOAD(userId, sessionId, file.name)}?user_id=${userId}`;
        if (token) url = appendAccessToken(url, token);
        return { src: url, alt: file.name, thumbnail: url };
      });
  }, [imageFilesKey, sessionId, token]);

  const imageIndexMap = useMemo(
    () => new Map(imageSlides.map((slide, index) => [slide.alt || slide.src, index])),
    [imageSlides],
  );

  const lightboxSlides = useMemo<readonly FileTreeImageSlide[]>(() => {
    if (!imagePreview) return [];
    return imageSlides.length > 0 ? imageSlides : [imagePreview.slide];
  }, [imagePreview, imageSlides]);

  const lightboxStartIndex = imagePreview
    ? imageSlides.length > 0
      ? imagePreview.startIndex
      : 0
    : 0;

  const openImagePreview = useCallback(
    (slide: FileTreeImageSlide, startIndex: number) => {
      setImagePreview({ slide, startIndex });
    },
    [],
  );

  const handleImageLightboxOpenChange = useCallback((open: boolean) => {
    if (!open) setImagePreview(null);
  }, []);

  // 搜索时自动展开所有目录
  useEffect(() => {
    if (searchQuery && treeDataWithLoadedChildren?.length > 0) {
      const allPaths = new Set<string>();
      const traverse = (nodes: FileTreeNode[]) => {
        nodes.forEach((n) => {
          if (n.isDirectory) {
            allPaths.add(n.path);
            if (n.children) traverse(n.children);
          }
        });
      };
      traverse(treeDataWithLoadedChildren);
      setExpandedFolders(allPaths);
    }
  }, [searchQuery, treeDataWithLoadedChildren]);

  // collapseAll 信号处理
  useEffect(() => {
    if (collapseAllSignal <= 0) return;
    setExpandedFolders(new Set());
  }, [collapseAllSignal]);

  // 默认展开第一层目录
  useEffect(() => {
    if (!expandFirstLevel || !treeDataWithLoadedChildren || treeDataWithLoadedChildren.length === 0) return;
    const firstLevelPaths = new Set<string>();
    treeDataWithLoadedChildren.forEach((node) => {
      if (node.isDirectory) firstLevelPaths.add(node.path);
    });
    if (firstLevelPaths.size > 0) {
      setExpandedFolders((current) => {
        const next = new Set(current);
        firstLevelPaths.forEach((p) => next.add(p));
        return next;
      });
    }
  }, [expandFirstLevel, treeDataWithLoadedChildren]);

  // 选中文件时自动展开祖先目录
  useEffect(() => {
    if (!selectedFileName) return;
    const ancestorPaths = getAncestorFolderPaths(selectedFileName);
    if (ancestorPaths.length === 0) return;
    setExpandedFolders((current) => {
      const next = new Set(current);
      ancestorPaths.forEach((path) => next.add(path));
      return next;
    });
  }, [selectedFileName]);

  // 清理已不存在的选中项
  const visibleItemKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const { node } of flatNodes) {
      if (node.isDirectory || node.file) {
        keys.add(node.isDirectory
          ? getFolderSelectionKey(node.path)
          : getFileSelectionKey(node.file?.name ?? node.path));
      }
    }
    return keys;
  }, [flatNodes]);

  useEffect(() => {
    setMultiSelectedItemKeys((current) => {
      let changed = false;
      const next = new Set<string>();
      for (const itemKey of current) {
        if (visibleItemKeys.has(itemKey)) {
          next.add(itemKey);
        } else {
          changed = true;
        }
      }
      return changed ? next : current;
    });
  }, [visibleItemKeys]);

  // 外部 selectedFileName 变化时同步选中状态
  useEffect(() => {
    if (lastSyncedSelectedFileNameRef.current === selectedFileName) return;
    lastSyncedSelectedFileNameRef.current = selectedFileName;
    setMultiSelectedItemKeys(
      selectedFileName
        ? new Set([getFileSelectionKey(selectedFileName)])
        : new Set(),
    );
  }, [selectedFileName]);

  const selectedItemKeys = multiSelectedItemKeys;

  // 统一获取节点选择 key
  const getNodeKey = useCallback((node: FileTreeNode): string => {
    return node.isDirectory
      ? getFolderSelectionKey(node.path)
      : getFileSelectionKey(node.file?.name ?? node.path);
  }, []);

  // 从 anchor 扩展到目标 key 的选中范围
  const extendSelectionFromAnchor = useCallback(
    (targetKey: string) => {
      if (!anchorItemKey) return;
      const anchorIdx = flatNodes.findIndex((fn) => getNodeKey(fn.node) === anchorItemKey);
      const targetIdx = flatNodes.findIndex((fn) => getNodeKey(fn.node) === targetKey);
      if (anchorIdx === -1 || targetIdx === -1) return;
      const min = Math.min(anchorIdx, targetIdx);
      const max = Math.max(anchorIdx, targetIdx);
      const rangeKeys = new Set<string>();
      for (let i = min; i <= max; i++) {
        const fn = flatNodes[i];
        if (fn && !isLoadMoreRow(fn.node)) {
          rangeKeys.add(getNodeKey(fn.node));
        }
      }
      setMultiSelectedItemKeys(rangeKeys);
    },
    [anchorItemKey, flatNodes, getNodeKey],
  );

  // 键盘导航
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      const currentIndex = focusItemKey
        ? flatNodes.findIndex((fn) => getNodeKey(fn.node) === focusItemKey)
        : -1;

      const focusAndMaybeSelect = (nextKey: string, shift: boolean) => {
        setFocusItemKey(nextKey);
        if (shift && anchorItemKey) {
          // 用函数式更新获取最新的 anchorItemKey
          setMultiSelectedItemKeys((prev) => {
            const anchorIdx = flatNodes.findIndex((fn) => getNodeKey(fn.node) === anchorItemKey);
            const targetIdx = flatNodes.findIndex((fn) => getNodeKey(fn.node) === nextKey);
            if (anchorIdx === -1 || targetIdx === -1) return prev;
            const min = Math.min(anchorIdx, targetIdx);
            const max = Math.max(anchorIdx, targetIdx);
            const rangeKeys = new Set<string>();
            for (let i = min; i <= max; i++) {
              const fn = flatNodes[i];
              if (fn && !isLoadMoreRow(fn.node)) {
                rangeKeys.add(getNodeKey(fn.node));
              }
            }
            return rangeKeys;
          });
        }
      };

      switch (event.key) {
        case "ArrowDown": {
          event.preventDefault();
          const nextIndex = Math.min(currentIndex + 1, flatNodes.length - 1);
          if (nextIndex >= 0 && nextIndex !== currentIndex) {
            const nextKey = getNodeKey(flatNodes[nextIndex].node);
            focusAndMaybeSelect(nextKey, event.shiftKey);
          }
          break;
        }
        case "ArrowUp": {
          event.preventDefault();
          const prevIndex = Math.max(currentIndex - 1, 0);
          if (prevIndex >= 0 && prevIndex !== currentIndex) {
            const prevKey = getNodeKey(flatNodes[prevIndex].node);
            focusAndMaybeSelect(prevKey, event.shiftKey);
          }
          break;
        }
        case "Enter": {
          event.preventDefault();
          if (focusItemKey) {
            if (event.shiftKey && anchorItemKey) {
              extendSelectionFromAnchor(focusItemKey);
            } else {
              setMultiSelectedItemKeys(new Set([focusItemKey]));
              setAnchorItemKey(focusItemKey);
            }
            const focusNode = flatNodes.find(
              (fn) => getNodeKey(fn.node) === focusItemKey,
            );
            if (focusNode) {
              if (focusNode.node.isDirectory) {
                handleToggleFolder(focusNode.node.path);
              } else if (focusNode.node.file && onFileSelect) {
                onFileSelect(focusNode.node.file);
              }
            }
          }
          break;
        }
        case " ": {
          event.preventDefault();
          if (focusItemKey) {
            setMultiSelectedItemKeys((current) => {
              const next = new Set(current);
              if (next.has(focusItemKey)) {
                next.delete(focusItemKey);
              } else {
                next.add(focusItemKey);
              }
              return next;
            });
            if (!event.shiftKey) {
              setAnchorItemKey(focusItemKey);
            }
          }
          break;
        }
        case "a": {
          if ((event.ctrlKey || event.metaKey) && !event.shiftKey) {
            event.preventDefault();
            const allKeys = flatNodes
              .filter((fn) => !isLoadMoreRow(fn.node))
              .map((fn) => getNodeKey(fn.node));
            setMultiSelectedItemKeys(new Set(allKeys));
          }
          break;
        }
        case "Escape": {
          setMultiSelectedItemKeys(new Set());
          setAnchorItemKey(null);
          break;
        }
        case "Home": {
          event.preventDefault();
          if (flatNodes.length > 0) {
            const firstKey = getNodeKey(flatNodes[0].node);
            focusAndMaybeSelect(firstKey, event.shiftKey);
          }
          break;
        }
        case "End": {
          event.preventDefault();
          if (flatNodes.length > 0) {
            const lastKey = getNodeKey(flatNodes[flatNodes.length - 1].node);
            focusAndMaybeSelect(lastKey, event.shiftKey);
          }
          break;
        }
      }
    },
    [
      focusItemKey,
      anchorItemKey,
      flatNodes,
      getNodeKey,
      extendSelectionFromAnchor,
      handleToggleFolder,
      onFileSelect,
    ],
  );

  const handleNodeClick = useCallback(
    (node: FileTreeNode, event: React.MouseEvent) => {
      if (!node.isDirectory && !node.file) return;
      const itemKey = node.isDirectory
        ? getFolderSelectionKey(node.path)
        : getFileSelectionKey(node.file?.name ?? node.path);

      // Shift + 点击：选择 anchor 到当前项之间的所有可见项
      if (event.shiftKey && anchorItemKey) {
        event.preventDefault();
        const anchorIndex = flatNodes.findIndex((fn) => {
          const key = fn.node.isDirectory
            ? getFolderSelectionKey(fn.node.path)
            : getFileSelectionKey(fn.node.file?.name ?? fn.node.path);
          return key === anchorItemKey;
        });
        const currentIndex = flatNodes.findIndex((fn) => {
          const key = fn.node.isDirectory
            ? getFolderSelectionKey(fn.node.path)
            : getFileSelectionKey(fn.node.file?.name ?? fn.node.path);
          return key === itemKey;
        });

        if (anchorIndex !== -1 && currentIndex !== -1) {
          const min = Math.min(anchorIndex, currentIndex);
          const max = Math.max(anchorIndex, currentIndex);
          const rangeKeys = new Set<string>();
          for (let i = min; i <= max; i++) {
            const fn = flatNodes[i];
            if (fn && !isLoadMoreRow(fn.node)) {
              const key = fn.node.isDirectory
                ? getFolderSelectionKey(fn.node.path)
                : getFileSelectionKey(fn.node.file?.name ?? fn.node.path);
              rangeKeys.add(key);
            }
          }
          setMultiSelectedItemKeys(rangeKeys);
        } else {
          // anchor 已不在可见列表中（目录被折叠），退化为普通单选
          setAnchorItemKey(itemKey);
          setMultiSelectedItemKeys(new Set([itemKey]));
          if (node.isDirectory) {
            onTreeNodeSelect?.(node);
            handleToggleFolder(node.path);
          } else if (node.file) {
            onFileSelect?.(node.file);
          }
        }
        return;
      }

      if (event.ctrlKey || event.metaKey) {
        event.preventDefault();
        setMultiSelectedItemKeys((current) => {
          const next = new Set(current);
          if (next.has(itemKey)) {
            next.delete(itemKey);
          } else {
            next.add(itemKey);
          }
          return next;
        });
        // Ctrl 点击不更新 anchor
        return;
      }

      // 普通点击：更新 anchor，单选当前项
      setAnchorItemKey(itemKey);
      setMultiSelectedItemKeys(new Set([itemKey]));
      if (node.isDirectory) {
        onTreeNodeSelect?.(node);
        handleToggleFolder(node.path);
      } else if (node.file) {
        onFileSelect?.(node.file);
      }
    },
    [handleToggleFolder, onFileSelect, onTreeNodeSelect, anchorItemKey, flatNodes],
  );

  const containerRef = useRef<HTMLDivElement>(null);

  // 基于展平列表的虚拟滚动
  const virtualizer = useVirtualizer({
    count: flatNodes.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
  });

  if (
    (!files || files.length === 0) &&
    (!externalTreeData || externalTreeData.length === 0)
  ) {
    return null;
  }

  const handleRootDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  };

  const handleRootDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOverFolderPath(null);
    setDraggingPath(null);

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

    // 只移动根级直接子项（不包含 "/" 的路径）
    let anyOk = false;
    for (const source of sources) {
      if (!source.includes("/")) continue;

      const sourceName = source.split("/").pop() || source;

      try {
        const ok = await onMoveFile?.(source, sourceName);
        if (ok) anyOk = true;
      } catch {
        // 静默失败
      }
    }

    if (anyOk) {
      await onRefreshFiles?.();
    }
  };

  return (
    <div
      ref={containerRef}
      className="flex flex-col h-full overflow-y-auto py-2 outline-none"
      tabIndex={0}
      onKeyDown={handleKeyDown}
      onFocus={() => setIsTreeFocused(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) {
          setIsTreeFocused(false);
        }
      }}
      onDragOver={handleRootDragOver}
      onDrop={handleRootDrop}
    >
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: "100%",
          position: "relative",
        }}
      >
        {virtualizer.getVirtualItems().map((virtualItem) => {
          const flatNode = flatNodes[virtualItem.index];
          if (!flatNode) return null;
          return (
            <div
              key={`${flatNode.node.path}-${virtualItem.index}`}
              data-index={virtualItem.index}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                height: ROW_HEIGHT,
                transform: `translateY(${virtualItem.start}px)`,
              }}
            >
              <FileTreeRow
                node={flatNode.node}
                level={flatNode.level}
                sessionId={sessionId}
                token={token}
                imageSlides={imageSlides}
                imageIndexMap={imageIndexMap}
                onOpenImagePreview={openImagePreview}
                expandedFolders={expandedFolders}
                onToggleFolder={handleToggleFolder}
                onTreeNodeSelect={onTreeNodeSelect}
                selectedItemKeys={selectedItemKeys}
                onNodeClick={handleNodeClick}
                onOpenFileMenu={openFileMenu}
                onOpenInMainCanvas={onOpenInMainCanvas}
                onEditInMainCanvas={onEditInMainCanvas}
                onMoveFile={onMoveFile}
                onRefreshFiles={onRefreshFiles}
                dragOverFolder={dragOverFolderPath}
                onDragOverFolder={setDragOverFolderPath}
                draggingNode={draggingPath}
                onDragStartNode={setDraggingPath}
                onOpenFolderMenu={openFolderMenu}
                onOpenFileCreate={onOpenFileCreate}
                onOpenFolderCreate={onOpenFolderCreate}
                onLoadDirectoryChildren={loadDirectoryChildren}
                onLoadMoreDirectoryChildren={loadMoreDirectoryChildren}
                loadingDirectoryPath={loadingDirectoryPath}
                focusItemKey={focusItemKey}
                isTreeFocused={isTreeFocused}
              />
            </div>
          );
        })}
      </div>

      {imagePreview ? (
        <React.Suspense fallback={null}>
          <LazyImageLightboxViewer
            open={imagePreview !== null}
            onOpenChange={handleImageLightboxOpenChange}
            slides={lightboxSlides}
            startIndex={lightboxStartIndex}
            zoomMargin={24}
          />
        </React.Suspense>
      ) : null}

      {selectedItemKeys.size > 1 ? (
        <div
          data-testid="workspace-file-tree-multi-select-summary"
          className="mx-3 mt-2 flex items-center gap-2 rounded-md border border-primary/20 bg-primary/5 px-3 py-1.5 text-[11px] font-medium text-primary"
        >
          <span className="flex-1">已选 {selectedItemKeys.size} 项</span>
          <button
            type="button"
            className="rounded px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-primary/10 hover:text-primary transition-colors"
            onClick={() => {
              setMultiSelectedItemKeys(new Set());
              setAnchorItemKey(null);
            }}
            title="清除选择 (Esc)"
          >
            清除
          </button>
          {onDeleteFile && (
            <button
              type="button"
              className="rounded px-1.5 py-0.5 text-[10px] text-error/80 hover:bg-error/10 hover:text-error transition-colors"
              onClick={() => {
                // 收集所有选中文件的文件名
                const selectedFiles: string[] = [];
                const selectedFolders: string[] = [];
                for (const key of selectedItemKeys) {
                  if (key.startsWith("file:")) {
                    selectedFiles.push(key.slice(5));
                  } else if (key.startsWith("folder:")) {
                    selectedFolders.push(key.slice(7));
                  }
                }
                // 批量删除：逐个调用
                const doDelete = async () => {
                  for (const f of selectedFiles) {
                    await onDeleteFile(f);
                  }
                  if (onDeleteFolder) {
                    for (const f of selectedFolders) {
                      await onDeleteFolder(f);
                    }
                  }
                  setMultiSelectedItemKeys(new Set());
                  setAnchorItemKey(null);
                  await onRefreshFiles?.();
                };
                void doDelete();
              }}
              title="删除选中项"
            >
              删除
            </button>
          )}
        </div>
      ) : null}

      <div className="mt-4 px-4 py-2 text-[10px] text-muted-foreground/40 font-mono text-center border-t border-border/50 mx-4">
        END OF FILES
      </div>

      <FileContextMenu
        fileMenu={fileMenu}
        menuRef={menuRef}
        deletingFileName={deletingFileName}
        exportingFile={exportingFile}
        onFileSelect={onFileSelect}
        onOpenInMainCanvas={onOpenInMainCanvas}
        onEditInMainCanvas={onEditInMainCanvas}
        onOpenFileHistory={onOpenFileHistory}
        onExportMarkdownFile={onExportMarkdownFile}
        onDeleteFile={onDeleteFile}
        onMoveFile={onMoveFile}
        getFileCopyPathOptions={getFileCopyPathOptions}
        getDownloadUrl={getDownloadUrl}
        handleCopyText={handleCopyText}
        rememberClipboardItem={rememberClipboardItem}
        handleExportFile={handleExportFile}
        requestDeleteFile={requestDeleteFile}
        requestDeleteMultiple={requestDeleteMultiple}
        closeFileMenu={closeFileMenu}
        isNotebookFile={isNotebookFile}
        isMarkdownFile={isMarkdownFile}
        onRefreshFiles={onRefreshFiles}
      />

      <FolderContextMenu
        folderMenu={folderMenu}
        menuRef={menuRef}
        deletingFolderPath={deletingFolderPath}
        clipboardItem={clipboardItem}
        onMoveFile={onMoveFile}
        onOpenFileCreate={onOpenFileCreate}
        onOpenFolderCreate={onOpenFolderCreate}
        onDeleteFolder={onDeleteFolder}
        getFolderCopyPath={getFolderCopyPath}
        getFolderCopyPathOptions={getFolderCopyPathOptions}
        handleCopyText={handleCopyText}
        rememberClipboardItem={rememberClipboardItem}
        pasteClipboardItem={pasteClipboardItem}
        requestDeleteFolder={requestDeleteFolder}
        requestDeleteMultiple={requestDeleteMultiple}
        closeFolderMenu={closeFolderMenu}
        onRefreshFiles={onRefreshFiles}
      />

      <AlertDialog
        open={Boolean(deleteConfirm)}
        onOpenChange={(open) => {
          if (!open) {
            setDeleteConfirm(null);
            setCriticalConfirmText("");
          }
        }}
      >
        <AlertDialogContent className={deleteConfirm?.isCritical ? "border-destructive" : undefined}>
          <AlertDialogHeader>
            <AlertDialogTitle className={deleteConfirm?.isCritical ? "text-destructive" : undefined}>
              {deleteConfirm?.isCritical
                ? "危险操作：删除系统配置"
                : deleteConfirm?.kind === "file"
                  ? "删除文件"
                  : "删除文件夹"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {deleteConfirm?.isCritical ? (
                <span className="space-y-2">
                  <p className="font-medium text-destructive">
                    你正在删除系统关键配置目录或文件。此操作可能导致：
                  </p>
                  <ul className="list-disc pl-4 text-sm">
                    <li>LLM 模型配置丢失</li>
                    <li>Memory 记忆文件丢失</li>
                    <li>已安装的技能副本丢失</li>
                    <li>Agent 运行状态异常</li>
                  </ul>
                  <p className="text-sm font-medium">如需继续，请在下方输入确认文字。</p>
                </span>
              ) : deleteConfirm?.kind === "file" ? (
                `确定要删除文件 "${deleteConfirm.file.name}" 吗？删除后无法恢复。`
              ) : (
                `确定要删除文件夹 "${deleteConfirm?.path}" 吗？该文件夹及其内容将被一并删除，且无法恢复。`
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteConfirm?.isCritical && (
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground">
                请输入确认文字：{CRITICAL_CONFIRM_PHRASE}
              </label>
              <input
                type="text"
                value={criticalConfirmText}
                onChange={(e) => setCriticalConfirmText(e.target.value)}
                placeholder={CRITICAL_CONFIRM_PHRASE}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-destructive focus:ring-1 focus:ring-destructive"
                autoFocus
              />
            </div>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel
              disabled={deletingFileName !== null || deletingFolderPath !== null}
              onClick={() => setCriticalConfirmText("")}
            >
              取消
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setCriticalConfirmText("");
                void executeDelete();
              }}
              disabled={
                deletingFileName !== null ||
                deletingFolderPath !== null ||
                (deleteConfirm?.isCritical && criticalConfirmText !== CRITICAL_CONFIRM_PHRASE)
              }
              className="bg-destructive text-destructive-foreground"
            >
              {deletingFileName !== null || deletingFolderPath !== null ? (
                <span className="mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
              ) : null}
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={Boolean(copyFailure)}
        onOpenChange={(open) => {
          if (!open) setCopyFailure(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>复制失败</AlertDialogTitle>
            <AlertDialogDescription>{copyFailure?.reason}</AlertDialogDescription>
          </AlertDialogHeader>
          <textarea
            readOnly
            value={copyFailure?.text ?? ""}
            className="min-h-24 w-full resize-none rounded-md border border-border bg-muted/30 p-2 font-mono text-xs text-foreground outline-none"
            onFocus={(event) => event.currentTarget.select()}
          />
          <AlertDialogFooter>
            <AlertDialogCancel>关闭</AlertDialogCancel>
            <AlertDialogAction onClick={() => void handleRetryCopyText()}>
              再试一次
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};