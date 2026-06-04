import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface WorkspaceDeleteDialogProps {
  open: boolean;
  workspaceTitle?: string | null;
  isCurrentWorkspace: boolean;
  isBulkDelete?: boolean;
  workspaceCount?: number;
  deleteWorkspaceError?: string | null;
  isDeletingWorkspace: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirmDelete: () => void;
}

export function WorkspaceDeleteDialog({
  open,
  workspaceTitle,
  isCurrentWorkspace,
  isBulkDelete,
  workspaceCount,
  deleteWorkspaceError,
  isDeletingWorkspace,
  onOpenChange,
  onConfirmDelete,
}: WorkspaceDeleteDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader className="sr-only">
          <DialogTitle>{isBulkDelete ? "清空工作区" : "删除工作区"}</DialogTitle>
          <DialogDescription>
            {isBulkDelete
              ? "确认清空所有工作区，此操作不可恢复。"
              : "确认删除当前工作区及其所有会话和文件，此操作不可恢复。"}
          </DialogDescription>
        </DialogHeader>
        <div className="flex items-start gap-4 py-4">
          <div className="rounded-full bg-error-container p-2 text-error">
            <AlertTriangle className="h-6 w-6" />
          </div>
          <div className="flex-1">
            <h3 className="mb-1 text-lg font-semibold text-foreground">
              {isBulkDelete ? "清空工作区" : "删除工作区"}
            </h3>
            {isBulkDelete ? (
              <p className="text-sm leading-6 text-muted-foreground">
                确定要清空全部 {workspaceCount ?? 0} 个工作区吗？
                <br />
                所有工作区及其会话、文件都会被删除，此操作不可恢复。
              </p>
            ) : (
              <p className="text-sm leading-6 text-muted-foreground">
                确定要删除 "{workspaceTitle || "未命名工作区"}" 吗？
                <br />
                该工作区下的所有会话和工作区文件都会被删除，此操作不可恢复。
              </p>
            )}
            {isCurrentWorkspace && !isBulkDelete ? (
              <p className="mt-3 text-xs leading-5 text-muted-foreground">
                删除当前工作区后，系统会自动切到剩余工作区；如果没有剩余工作区，会打开新建工作区弹窗。
              </p>
            ) : null}
            {deleteWorkspaceError ? (
              <div className="mt-3 rounded-xl border border-dashed border-error/20 bg-error-container px-3 py-2 text-sm text-error">
                {deleteWorkspaceError}
              </div>
            ) : null}
          </div>
        </div>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isDeletingWorkspace}
          >
            取消
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirmDelete}
            disabled={isDeletingWorkspace}
          >
            {isDeletingWorkspace
              ? "删除中..."
              : isBulkDelete
                ? "全部清空"
                : "删除工作区"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
