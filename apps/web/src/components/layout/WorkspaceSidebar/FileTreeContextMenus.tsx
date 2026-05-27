import React from "react";
import { cn } from "@/lib/utils";
import type { WorkspaceFile } from "@/types/task";
import {
  BookOpen,
  Clipboard,
  Download,
  ExternalLink,
  FilePlus,
  FileText,
  FolderPlus,
  History,
  Scissors,
  SquarePen,
  Trash2,
} from "lucide-react";
import { isGenericallyEditable } from "@/utils/workspaceFileEditing";
import type { FileTreeClipboardItem } from "./FileTreeView";

type ExportFormat = "md" | "docx" | "pdf";

interface CopyPathOption {
  label: string;
  value: string;
  icon: "path" | "link";
}

interface FileMenuState {
  file: WorkspaceFile;
  x: number;
  y: number;
  multiSelectedFiles?: WorkspaceFile[];
  multiSelectedFolders?: string[];
}

interface FolderMenuState {
  path: string;
  name: string;
  absolutePath?: string | null;
  x: number;
  y: number;
  multiSelectedFiles?: WorkspaceFile[];
  multiSelectedFolders?: string[];
}

interface FileContextMenuProps {
  fileMenu: FileMenuState | null;
  menuRef: React.RefObject<HTMLDivElement | null>;
  deletingFileName: string | null;
  exportingFile: { filename: string; format: ExportFormat } | null;
  onFileSelect?: (file: WorkspaceFile) => void;
  onOpenInMainCanvas?: (file: WorkspaceFile) => void;
  onEditInMainCanvas?: (file: WorkspaceFile) => void;
  onOpenFileHistory?: (file: WorkspaceFile) => void;
  onExportMarkdownFile?: (filename: string, format: ExportFormat) => Promise<void>;
  onDeleteFile?: (filename: string) => Promise<boolean>;
  onMoveFile?: (source: string, target: string) => Promise<boolean>;
  getFileCopyPathOptions: (file: WorkspaceFile) => CopyPathOption[];
  getDownloadUrl: (filename: string) => string | null;
  handleCopyText: (text: string, source: "file" | "folder") => Promise<void>;
  rememberClipboardItem: (item: FileTreeClipboardItem) => void;
  handleExportFile: (file: WorkspaceFile, format: ExportFormat) => Promise<void>;
  requestDeleteFile: (file: WorkspaceFile) => void;
  requestDeleteMultiple?: (files: WorkspaceFile[], folders: string[]) => void;
  closeFileMenu: () => void;
  isNotebookFile: (filename: string) => boolean;
  isMarkdownFile: (filename: string) => boolean;
  onRefreshFiles?: () => Promise<void>;
}

export function FileContextMenu({
  fileMenu,
  menuRef,
  deletingFileName,
  exportingFile,
  onFileSelect,
  onOpenInMainCanvas,
  onEditInMainCanvas,
  onOpenFileHistory,
  onExportMarkdownFile,
  onDeleteFile,
  onMoveFile,
  getFileCopyPathOptions,
  getDownloadUrl,
  handleCopyText,
  rememberClipboardItem,
  handleExportFile,
  requestDeleteFile,
  requestDeleteMultiple,
  closeFileMenu,
  isNotebookFile,
  isMarkdownFile,
  onRefreshFiles: _onRefreshFiles,
}: FileContextMenuProps) {
  if (!fileMenu) return null;

  const isMulti = Boolean(
    fileMenu.multiSelectedFiles?.length || fileMenu.multiSelectedFolders?.length,
  );
  const totalCount =
    (fileMenu.multiSelectedFiles?.length ?? 0) +
    (fileMenu.multiSelectedFolders?.length ?? 0);

  // 多选模式：批量操作菜单
  if (isMulti) {
    const allFilePaths = (fileMenu.multiSelectedFiles ?? [])
      .map((f) => f.absolute_path ?? f.name)
      .join("\n");
    const allNames = [
      ...(fileMenu.multiSelectedFiles ?? []).map((f) => f.name),
      ...(fileMenu.multiSelectedFolders ?? []),
    ].join("\n");

    return (
      <div
        ref={menuRef}
        role="menu"
        className="fixed z-[80] w-56 overflow-hidden rounded-xl border border-border bg-background p-1 text-sm text-foreground shadow-xl"
        style={{ left: `${fileMenu.x}px`, top: `${fileMenu.y}px` }}
      >
        <div className="border-b border-border px-2 py-2">
          <div className="text-xs font-semibold text-foreground">
            已选 {totalCount} 项
          </div>
        </div>
        <button
          type="button"
          role="menuitem"
          className="mt-1 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
          onClick={() => {
            void handleCopyText(allFilePaths || allNames, "file");
            closeFileMenu();
          }}
        >
          <Clipboard className="h-3.5 w-3.5 text-muted-foreground" />
          复制所有路径
        </button>
        <button
          type="button"
          role="menuitem"
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
          onClick={() => {
            void handleCopyText(allNames, "file");
            closeFileMenu();
          }}
        >
          <Clipboard className="h-3.5 w-3.5 text-muted-foreground" />
          复制所有文件名
        </button>
        {onMoveFile ? (
          <>
            <div className="mt-1 border-t border-border pt-1" />
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
              onClick={() => {
                for (const f of fileMenu.multiSelectedFiles ?? []) {
                  rememberClipboardItem({
                    kind: "file",
                    sourcePath: f.name,
                    action: "copy",
                  });
                }
                for (const p of fileMenu.multiSelectedFolders ?? []) {
                  rememberClipboardItem({
                    kind: "folder",
                    sourcePath: p,
                    action: "copy",
                  });
                }
                closeFileMenu();
              }}
            >
              <Clipboard className="h-3.5 w-3.5 text-muted-foreground" />
              复制 {totalCount} 项
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              disabled={!onMoveFile}
              onClick={() => {
                for (const f of fileMenu.multiSelectedFiles ?? []) {
                  rememberClipboardItem({
                    kind: "file",
                    sourcePath: f.name,
                    action: "cut",
                  });
                }
                for (const p of fileMenu.multiSelectedFolders ?? []) {
                  rememberClipboardItem({
                    kind: "folder",
                    sourcePath: p,
                    action: "cut",
                  });
                }
                closeFileMenu();
              }}
            >
              <Scissors className="h-3.5 w-3.5 text-muted-foreground" />
              剪切 {totalCount} 项
            </button>
          </>
        ) : null}
        {onDeleteFile ? (
          <div className="mt-1 border-t border-border pt-1">
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-error transition-colors hover:bg-error-container focus:bg-error-container focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              disabled={Boolean(deletingFileName)}
              onClick={() => {
                requestDeleteMultiple?.(
                  fileMenu.multiSelectedFiles ?? [],
                  fileMenu.multiSelectedFolders ?? [],
                );
                closeFileMenu();
              }}
            >
              <Trash2 className="h-3.5 w-3.5" />
              删除 {totalCount} 项
            </button>
          </div>
        ) : null}
      </div>
    );
  }

  // 单选模式：原有菜单

  return (
    <div
      ref={menuRef}
      role="menu"
      className="fixed z-[80] w-56 overflow-hidden rounded-xl border border-border bg-background p-1 text-sm text-foreground shadow-xl"
      style={{ left: `${fileMenu.x}px`, top: `${fileMenu.y}px` }}
    >
      <div className="border-b border-border px-2 py-2">
        <div className="truncate text-xs font-semibold text-foreground">
          {fileMenu.file.name.split("/").pop()}
        </div>
        <div className="mt-0.5 truncate text-[11px] text-muted-foreground">
          {fileMenu.file.absolute_path ?? fileMenu.file.name}
        </div>
      </div>
      {isNotebookFile(fileMenu.file.name) ? (
        <>
          <button
            type="button"
            role="menuitem"
            className="mt-1 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
            onClick={() => {
              onEditInMainCanvas?.(fileMenu.file);
              closeFileMenu();
            }}
          >
            <BookOpen className="h-3.5 w-3.5 text-muted-foreground" />
            在 Notebook 中打开
          </button>
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
            onClick={() => {
              onFileSelect?.(fileMenu.file);
              closeFileMenu();
            }}
          >
            <FileText className="h-3.5 w-3.5 text-muted-foreground" />
            打开预览
          </button>
        </>
      ) : (
        <>
          <button
            type="button"
            role="menuitem"
            className="mt-1 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
            onClick={() => {
              onFileSelect?.(fileMenu.file);
              closeFileMenu();
            }}
          >
            <FileText className="h-3.5 w-3.5 text-muted-foreground" />
            打开预览
          </button>
          {onOpenInMainCanvas ? (
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
              onClick={() => {
                onOpenInMainCanvas(fileMenu.file);
                closeFileMenu();
              }}
            >
              <ExternalLink className="h-3.5 w-3.5 text-muted-foreground" />
              在主画布打开
            </button>
          ) : null}
          {onEditInMainCanvas && isGenericallyEditable(fileMenu.file.name) ? (
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
              onClick={() => {
                onEditInMainCanvas(fileMenu.file);
                closeFileMenu();
              }}
            >
              <SquarePen className="h-3.5 w-3.5 text-muted-foreground" />
              编辑文件
            </button>
          ) : null}
        </>
      )}
      {getFileCopyPathOptions(fileMenu.file).map((option) => {
        const Icon = option.icon === "link" ? ExternalLink : Clipboard;
        return (
          <button
            key={option.label}
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
            onClick={() => void handleCopyText(option.value, "file")}
          >
            <Icon className="h-3.5 w-3.5 text-muted-foreground" />
            {option.label}
          </button>
        );
      })}
      {onOpenFileHistory ? (
        <button
          type="button"
          role="menuitem"
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
          onClick={() => {
            onOpenFileHistory(fileMenu.file);
            closeFileMenu();
          }}
        >
          <History className="h-3.5 w-3.5 text-muted-foreground" />
          文件历史
        </button>
      ) : null}
      <div className="mt-1 border-t border-border pt-1">
        <button
          type="button"
          role="menuitem"
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
          onClick={() =>
            rememberClipboardItem({
              kind: "file",
              sourcePath: fileMenu.file.name,
              action: "copy",
            })
          }
        >
          <Clipboard className="h-3.5 w-3.5 text-muted-foreground" />
          复制文件
        </button>
        <button
          type="button"
          role="menuitem"
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
          disabled={!onMoveFile}
          onClick={() =>
            rememberClipboardItem({
              kind: "file",
              sourcePath: fileMenu.file.name,
              action: "cut",
            })
          }
        >
          <Scissors className="h-3.5 w-3.5 text-muted-foreground" />
          剪切文件
        </button>
      </div>
      <a
        role="menuitem"
        href={getDownloadUrl(fileMenu.file.name) || undefined}
        download={fileMenu.file.name}
        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
        onClick={closeFileMenu}
      >
        <Download className="h-3.5 w-3.5 text-muted-foreground" />
        下载原文件
      </a>
      {onExportMarkdownFile && isMarkdownFile(fileMenu.file.name) ? (
        <div className="mt-1 border-t border-border pt-1">
          {(
            [
              ["md", "导出 Markdown"],
              ["docx", "导出 Word"],
              ["pdf", "导出 PDF"],
            ] as const
          ).map(([format, label]) => (
            <button
              key={format}
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              disabled={Boolean(exportingFile)}
              onClick={() => void handleExportFile(fileMenu.file, format)}
            >
              <Download className="h-3.5 w-3.5 text-muted-foreground" />
              {label}
            </button>
          ))}
        </div>
      ) : null}
      {onDeleteFile ? (
        <div className="mt-1 border-t border-border pt-1">
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-error transition-colors hover:bg-error-container focus:bg-error-container focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
            disabled={deletingFileName === fileMenu.file.name}
            onClick={() => void requestDeleteFile(fileMenu.file)}
          >
            <Trash2 className="h-3.5 w-3.5" />
            {deletingFileName === fileMenu.file.name ? "删除中" : "删除文件"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

interface FolderContextMenuProps {
  folderMenu: FolderMenuState | null;
  menuRef: React.RefObject<HTMLDivElement | null>;
  deletingFolderPath: string | null;
  clipboardItem: FileTreeClipboardItem | null | undefined;
  onMoveFile?: (source: string, target: string) => Promise<boolean>;
  onOpenFileCreate?: (folderPath: string) => void;
  onOpenFolderCreate?: (folderPath: string) => void;
  onDeleteFolder?: (folderPath: string) => Promise<boolean>;
  getFolderCopyPath?: (folderPath: string) => string;
  getFolderCopyPathOptions: (folderPath: string, absolutePath?: string | null) => CopyPathOption[];
  handleCopyText: (text: string, source: "file" | "folder") => Promise<void>;
  rememberClipboardItem: (item: FileTreeClipboardItem) => void;
  pasteClipboardItem: (targetPath: string) => Promise<void>;
  requestDeleteFolder: (folderPath: string) => void;
  requestDeleteMultiple?: (files: WorkspaceFile[], folders: string[]) => void;
  closeFolderMenu: () => void;
  onRefreshFiles?: () => Promise<void>;
}

export function FolderContextMenu({
  folderMenu,
  menuRef,
  deletingFolderPath,
  clipboardItem,
  onMoveFile,
  onOpenFileCreate,
  onOpenFolderCreate,
  onDeleteFolder,
  getFolderCopyPath,
  getFolderCopyPathOptions,
  handleCopyText,
  rememberClipboardItem,
  pasteClipboardItem,
  requestDeleteFolder,
  requestDeleteMultiple,
  closeFolderMenu,
  onRefreshFiles: _onRefreshFiles2,
}: FolderContextMenuProps) {
  if (!folderMenu) return null;

  const isMulti = Boolean(
    folderMenu.multiSelectedFiles?.length || folderMenu.multiSelectedFolders?.length,
  );
  const totalCount =
    (folderMenu.multiSelectedFiles?.length ?? 0) +
    (folderMenu.multiSelectedFolders?.length ?? 0);

  // 多选模式：批量操作菜单
  if (isMulti) {
    const allFilePaths = (folderMenu.multiSelectedFiles ?? [])
      .map((f) => f.absolute_path ?? f.name)
      .join("\n");
    const allNames = [
      ...(folderMenu.multiSelectedFiles ?? []).map((f) => f.name),
      ...(folderMenu.multiSelectedFolders ?? []),
    ].join("\n");

    return (
      <div
        ref={menuRef}
        role="menu"
        className="fixed z-[80] w-56 overflow-hidden rounded-xl border border-border bg-background p-1 text-sm text-foreground shadow-xl"
        style={{ left: `${folderMenu.x}px`, top: `${folderMenu.y}px` }}
      >
        <div className="border-b border-border px-2 py-2">
          <div className="text-xs font-semibold text-foreground">
            已选 {totalCount} 项
          </div>
        </div>
        <button
          type="button"
          role="menuitem"
          className="mt-1 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
          onClick={() => {
            void handleCopyText(allFilePaths || allNames, "folder");
            closeFolderMenu();
          }}
        >
          <Clipboard className="h-3.5 w-3.5 text-muted-foreground" />
          复制所有路径
        </button>
        <button
          type="button"
          role="menuitem"
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
          onClick={() => {
            void handleCopyText(allNames, "folder");
            closeFolderMenu();
          }}
        >
          <Clipboard className="h-3.5 w-3.5 text-muted-foreground" />
          复制所有文件名
        </button>
        {onMoveFile ? (
          <>
            <div className="mt-1 border-t border-border pt-1" />
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
              onClick={() => {
                for (const f of folderMenu.multiSelectedFiles ?? []) {
                  rememberClipboardItem({
                    kind: "file",
                    sourcePath: f.name,
                    action: "copy",
                  });
                }
                for (const p of folderMenu.multiSelectedFolders ?? []) {
                  rememberClipboardItem({
                    kind: "folder",
                    sourcePath: p,
                    action: "copy",
                  });
                }
                closeFolderMenu();
              }}
            >
              <Clipboard className="h-3.5 w-3.5 text-muted-foreground" />
              复制 {totalCount} 项
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              disabled={!onMoveFile}
              onClick={() => {
                for (const f of folderMenu.multiSelectedFiles ?? []) {
                  rememberClipboardItem({
                    kind: "file",
                    sourcePath: f.name,
                    action: "cut",
                  });
                }
                for (const p of folderMenu.multiSelectedFolders ?? []) {
                  rememberClipboardItem({
                    kind: "folder",
                    sourcePath: p,
                    action: "cut",
                  });
                }
                closeFolderMenu();
              }}
            >
              <Scissors className="h-3.5 w-3.5 text-muted-foreground" />
              剪切 {totalCount} 项
            </button>
          </>
        ) : null}
        {onDeleteFolder ? (
          <div className="mt-1 border-t border-border pt-1">
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-error transition-colors hover:bg-error-container focus:bg-error-container focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              disabled={Boolean(deletingFolderPath)}
              onClick={() => {
                requestDeleteMultiple?.(
                  folderMenu.multiSelectedFiles ?? [],
                  folderMenu.multiSelectedFolders ?? [],
                );
                closeFolderMenu();
              }}
            >
              <Trash2 className="h-3.5 w-3.5" />
              删除 {totalCount} 项
            </button>
          </div>
        ) : null}
      </div>
    );
  }

  // 单选模式：原有菜单

  return (
    <div
      ref={menuRef}
      role="menu"
      className="fixed z-[80] w-56 overflow-hidden rounded-xl border border-border bg-background p-1 text-sm text-foreground shadow-xl"
      style={{ left: `${folderMenu.x}px`, top: `${folderMenu.y}px` }}
    >
      <div className="border-b border-border px-2 py-2">
        <div className="truncate text-xs font-semibold text-foreground">
          {folderMenu.name}
        </div>
        <div className="mt-0.5 truncate text-[11px] text-muted-foreground">
          {folderMenu.absolutePath ?? getFolderCopyPath?.(folderMenu.path) ?? folderMenu.path}
        </div>
      </div>
      {getFolderCopyPathOptions(folderMenu.path, folderMenu.absolutePath).map((option, index) => (
        <button
          key={option.label}
          type="button"
          role="menuitem"
          className={cn(
            "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none",
            index === 0 && "mt-1",
          )}
          onClick={() => void handleCopyText(option.value, "folder")}
        >
          <Clipboard className="h-3.5 w-3.5 text-muted-foreground" />
          {option.label}
        </button>
      ))}
      <div className="mt-1 border-t border-border pt-1">
        <button
          type="button"
          role="menuitem"
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
          onClick={() =>
            rememberClipboardItem({
              kind: "folder",
              sourcePath: folderMenu.path,
              action: "copy",
            })
          }
        >
          <Clipboard className="h-3.5 w-3.5 text-muted-foreground" />
          复制文件夹
        </button>
        <button
          type="button"
          role="menuitem"
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
          disabled={!onMoveFile}
          onClick={() =>
            rememberClipboardItem({
              kind: "folder",
              sourcePath: folderMenu.path,
              action: "cut",
            })
          }
        >
          <Scissors className="h-3.5 w-3.5 text-muted-foreground" />
          剪切文件夹
        </button>
        <button
          type="button"
          role="menuitem"
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
          disabled={!clipboardItem}
          onClick={() => void pasteClipboardItem(folderMenu.path)}
        >
          <Clipboard className="h-3.5 w-3.5 text-muted-foreground" />
          粘贴到此文件夹
        </button>
      </div>
      <div className="mt-1 border-t border-border pt-1">
        <button
          type="button"
          role="menuitem"
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
          onClick={() => {
            onOpenFileCreate?.(folderMenu.path);
            closeFolderMenu();
          }}
        >
          <FilePlus className="h-3.5 w-3.5 text-muted-foreground" />
          新建文件
        </button>
        <button
          type="button"
          role="menuitem"
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
          onClick={() => {
            onOpenFolderCreate?.(folderMenu.path);
            closeFolderMenu();
          }}
        >
          <FolderPlus className="h-3.5 w-3.5 text-muted-foreground" />
          新建文件夹
        </button>
      </div>
      {onDeleteFolder ? (
        <div className="mt-1 border-t border-border pt-1">
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-error transition-colors hover:bg-error-container focus:bg-error-container focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
            disabled={deletingFolderPath === folderMenu.path}
            onClick={() => void requestDeleteFolder(folderMenu.path)}
          >
            <Trash2 className="h-3.5 w-3.5" />
            {deletingFolderPath === folderMenu.path ? "删除中" : "删除文件夹"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
