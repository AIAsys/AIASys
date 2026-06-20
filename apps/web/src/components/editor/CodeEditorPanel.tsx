import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Loader2,
  RotateCcw,
  Save,
} from "lucide-react";
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
import { CodeMirrorEditor } from "./CodeMirrorEditor";
import { useEditableFile } from "@/hooks/useEditableFile";
import { getWorkspaceEditorLanguage } from "@/utils/workspaceFileEditing";
import { cn } from "@/lib/utils";
import { FileUploadToast, useFileUploadToast } from "@/components/file/FileUploadToast";
import type { PreviewFile } from "@/components/layout/WorkspaceSidebar/preview";

interface CodeEditorPanelProps {
  file: PreviewFile;
  sessionId?: string | null;
  workspaceId?: string | null;
  onReadFileContent?: (filename: string) => Promise<string | null>;
  onRefreshWorkspace?: (sessionId: string) => Promise<void> | void;
  onDirtyChange?: (dirty: boolean) => void;
}

export function CodeEditorPanel({
  file,
  sessionId,
  workspaceId,
  onReadFileContent,
  onRefreshWorkspace,
  onDirtyChange,
}: CodeEditorPanelProps) {
  const {
    content,
    isLoading,
    isSaving,
    error,
    editable,
    editLockReason,
    loaded,
    dirty,
    setContent,
    save,
    reset,
  } = useEditableFile({
    fileName: file.name,
    sessionId,
    workspaceId,
    loadContent: onReadFileContent,
    onDirtyChange,
    onRefreshWorkspace,
  });
  const { toasts, showSuccess, showError } = useFileUploadToast();

  // 保存文件并显示 toast 反馈
  const handleSave = useCallback(async () => {
    if (!editable || !dirty || isSaving) return;
    const ok = await save();
    if (ok) {
      showSuccess("保存成功");
    } else {
      showError("保存失败，请重试");
    }
  }, [editable, dirty, isSaving, save, showSuccess, showError]);

  // 键盘快捷键
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (editable && dirty && !isSaving) {
          void handleSave();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [editable, dirty, isSaving, handleSave]);

  const [resetDialogOpen, setResetDialogOpen] = useState(false);

  const handleReset = useCallback(() => {
    if (!dirty) return;
    setResetDialogOpen(true);
  }, [dirty]);

  const handleConfirmReset = useCallback(() => {
    setResetDialogOpen(false);
    reset();
  }, [reset]);

  const language = getWorkspaceEditorLanguage(file.name);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-white dark:bg-[#1e1e1e] text-gray-900 dark:text-white">
      {error ? (
        <div className="border-b border-warning/30 bg-warning-container px-4 py-3 text-sm text-warning">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4" />
            <span>{error}</span>
          </div>
        </div>
      ) : null}
      {editLockReason ? (
        <div className="border-b border-warning/30 bg-warning-container px-4 py-3 text-sm text-warning">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4" />
            <span>{editLockReason}</span>
          </div>
        </div>
      ) : null}

      {/* 工具栏 */}
      <div className="flex items-center justify-between gap-3 border-b border-border/20 bg-gray-50 dark:bg-[#252526] px-4 py-2">
        <div className="flex items-center gap-2">
          {editable ? (
            <>
              <div
                className={cn(
                  "h-2 w-2 rounded-full",
                  dirty ? "bg-yellow-500" : "bg-green-500",
                )}
              />
              <span className="text-[11px] text-gray-500 dark:text-white/60">
                {dirty ? "未保存" : "已保存"}
              </span>
            </>
          ) : (
            <span className="text-[11px] text-gray-500 dark:text-white/60">只读</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {editable ? (
            <>
              <button
                type="button"
                onClick={handleReset}
                disabled={!dirty || isSaving}
                className="inline-flex h-7 items-center gap-1 rounded-md border border-gray-200 dark:border-white/10 bg-gray-100 dark:bg-white/5 px-2.5 text-[11px] text-gray-600 dark:text-white/70 transition-colors hover:bg-gray-200 dark:hover:bg-white/10 disabled:opacity-40"
              >
                <RotateCcw className="h-3 w-3" />
                还原
              </button>
              <button
                type="button"
                onClick={() => void handleSave()}
                disabled={!editable || !dirty || isSaving}
                className="inline-flex h-7 items-center gap-1 rounded-md bg-primary px-2.5 text-[11px] text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
              >
                {isSaving ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Save className="h-3 w-3" />
                )}
                保存
              </button>
            </>
          ) : null}
        </div>
      </div>

      {/* 编辑器 */}
      <div className="min-h-0 flex-1 overflow-hidden">
        {isLoading || !loaded ? (
          <div className="flex h-full items-center justify-center text-sm text-gray-500 dark:text-white/60">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            正在加载文件
          </div>
        ) : (
          <CodeMirrorEditor
            value={content}
            onChange={setContent}
            language={language}
            readOnly={!editable}
            theme="dark"
            ariaLabel={`编辑 ${file.name}`}
          />
        )}
      </div>

      <AlertDialog open={resetDialogOpen} onOpenChange={setResetDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认放弃修改</AlertDialogTitle>
            <AlertDialogDescription>
              放弃 "{file.name}" 的未保存修改吗？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setResetDialogOpen(false)}>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmReset}
              className="bg-destructive text-destructive-foreground"
            >
              放弃
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* 状态栏 */}
      <div className="flex min-h-7 items-center justify-between gap-3 border-t border-border/20 bg-gray-50 dark:bg-[#252526] px-4 py-1.5 text-[11px] text-gray-500 dark:text-white/50">
        <div className="min-w-0 truncate font-mono">{file.name}</div>
        <div className="flex shrink-0 items-center gap-3">
          <span>{content.length.toLocaleString("zh-CN")} 字符</span>
          <span>{language}</span>
          <span>{dirty ? "未保存" : "已同步"}</span>
        </div>
      </div>
      {/* 保存操作 toast 反馈 */}
      {toasts.map((toast) => (
        <FileUploadToast
          key={toast.id}
          message={toast.message}
          type={toast.type}
        />
      ))}
    </div>
  );
}

export default CodeEditorPanel;
