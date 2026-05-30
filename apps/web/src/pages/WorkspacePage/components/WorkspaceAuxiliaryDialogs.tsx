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
import { useWorkspaceRuntimeControls } from "../hooks/useWorkspaceRuntimeControls";

type RuntimeControlsState = ReturnType<typeof useWorkspaceRuntimeControls>;

interface WorkspaceAuxiliaryDialogsProps {
  runtimeControls: RuntimeControlsState;
}

export function WorkspaceAuxiliaryDialogs({
  runtimeControls,
}: WorkspaceAuxiliaryDialogsProps) {
  return (
    <>
      <Dialog
        open={runtimeControls.showRestartRuntimeConfirmDialog}
        onOpenChange={(open) => {
          if (!open) {
            runtimeControls.closeRestartRuntimeConfirmDialog();
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-foreground" />
              确认重置 Python 运行环境
            </DialogTitle>
            <DialogDescription className="pt-2">
              这会重置当前会话的 Python 运行环境
              {runtimeControls.activeEnv?.name
                ? `「${runtimeControls.activeEnv.name}」`
                : ""}
              ，用于处理变量污染、内存态脏掉或 notebook 内核异常。
              <br />
              <span className="text-muted-foreground">
                当前会话、代码执行记录和工作区文件会保留；旧变量和 Python 内存态不会恢复。
              </span>
              <br />
              <span className="text-muted-foreground">
                本地执行链路会释放当前 notebook 内核，并在下一次代码执行时创建新的 Python 运行环境。
              </span>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              variant="outline"
              onClick={runtimeControls.closeRestartRuntimeConfirmDialog}
              disabled={runtimeControls.isRestartingRuntime}
            >
              取消
            </Button>
            <Button
              variant="default"
              onClick={() => runtimeControls.confirmRestartRuntime()}
              disabled={runtimeControls.isRestartingRuntime}
            >
              {runtimeControls.isRestartingRuntime ? "重置中..." : "确认重置"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
