/**
 * FileOperationNotice - Agent 文件操作内联通知
 *
 * 当 Agent 通过文件写入类工具（WriteFile、StrReplaceFile、CreateFile 等）
 * 成功创建或编辑文件后，在对话流中内联显示文件路径和"打开"按钮，
 * 让用户无需手动去文件树查找即可快速预览产物。
 */
import { memo, useCallback, useMemo } from "react";
import { FileEdit, FilePlus, FileText, FolderOpen } from "lucide-react";

import type { PreviewFile } from "@/utils/filePreviewRegistry";
import { createWorkspacePreviewFile } from "@/utils/workspaceFiles";
import { useAiMessageContext } from "./context";

/** 文件写入类工具配置：工具名 → 路径参数名 + 操作类型 */
const FILE_WRITE_TOOLS: Record<
  string,
  { pathKey: string; operation: "create" | "edit" | "write" }
> = {
  WriteFile: { pathKey: "path", operation: "write" },
  StrReplaceFile: { pathKey: "path", operation: "edit" },
  CreateFile: { pathKey: "path", operation: "create" },
  WriteCanvas: { pathKey: "canvas_path", operation: "write" },
  BatchCanvasOperations: { pathKey: "canvas_path", operation: "edit" },
  EditNotebookFile: { pathKey: "notebook_path", operation: "edit" },
};

/** 从工具参数 JSON 字符串中提取文件路径 */
export function extractFilePathFromToolParams(
  toolName: string | undefined,
  toolParams: string | undefined,
): string | null {
  if (!toolName || !(toolName in FILE_WRITE_TOOLS)) return null;
  if (!toolParams) return null;

  const config = FILE_WRITE_TOOLS[toolName];
  try {
    const parsed = JSON.parse(toolParams);
    const rawPath = parsed[config.pathKey];
    if (typeof rawPath === "string" && rawPath.trim()) {
      return rawPath.trim();
    }
  } catch {
    // JSON 解析失败，忽略
  }
  return null;
}

/** 获取文件操作类型 */
export function getFileOperation(
  toolName: string | undefined,
): "create" | "edit" | "write" | null {
  if (!toolName || !(toolName in FILE_WRITE_TOOLS)) return null;
  return FILE_WRITE_TOOLS[toolName].operation;
}

const OPERATION_CONFIG = {
  create: { label: "创建文件", icon: FilePlus, color: "text-success" },
  edit: { label: "编辑文件", icon: FileEdit, color: "text-warning" },
  write: { label: "写入文件", icon: FileText, color: "text-info" },
} as const;

interface FileOperationNoticeProps {
  /** 工具名称 */
  toolName: string;
  /** 文件路径（工作区相对路径或带 /workspace/ /global/ 前缀） */
  filePath: string;
}

export const FileOperationNotice = memo(function FileOperationNotice({
  toolName,
  filePath,
}: FileOperationNoticeProps) {
  const {
    meta: { sessionId, onOpenWorkspaceArtifact, onOpenInBrowserTab },
  } = useAiMessageContext();

  const operation = getFileOperation(toolName) ?? "write";
  const config = OPERATION_CONFIG[operation];
  const Icon = config.icon;

  const displayPath = useMemo(() => {
    let p = filePath;
    if (p.startsWith("/workspace/")) p = p.slice("/workspace/".length);
    else if (p.startsWith("/global/")) p = p.slice("/global/".length);
    return p.replace(/^\.?\//, "");
  }, [filePath]);

  const fileName = useMemo(
    () => displayPath.split("/").pop() || displayPath,
    [displayPath],
  );

  const handleOpen = useCallback(() => {
    if (onOpenWorkspaceArtifact) {
      const previewFile: PreviewFile = createWorkspacePreviewFile(
        filePath,
        sessionId,
      );
      onOpenWorkspaceArtifact(previewFile);
    } else if (onOpenInBrowserTab) {
      onOpenInBrowserTab(filePath);
    }
  }, [filePath, sessionId, onOpenWorkspaceArtifact, onOpenInBrowserTab]);

  const canOpen = Boolean(onOpenWorkspaceArtifact || onOpenInBrowserTab);

  return (
    <div className="mb-2 flex items-center gap-2.5 rounded-lg border border-border bg-muted/40 px-3 py-2">
      <Icon className={`h-4 w-4 flex-shrink-0 ${config.color}`} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-[11px] font-medium text-muted-foreground">
          {config.label}
        </span>
        <span
          className="truncate font-mono text-xs text-foreground"
          title={displayPath}
        >
          {fileName}
        </span>
      </div>
      {canOpen && (
        <button
          type="button"
          onClick={handleOpen}
          className="flex flex-shrink-0 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 py-1.5 text-[11px] font-medium text-foreground transition-colors hover:bg-accent"
        >
          <FolderOpen className="h-3 w-3" />
          打开
        </button>
      )}
    </div>
  );
});
