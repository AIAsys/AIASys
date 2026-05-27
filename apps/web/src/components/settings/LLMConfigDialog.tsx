/**
 * LLM 配置弹窗
 *
 * 独立弹窗包装 LLMConfigPanel，替代"我的默认"弹窗中的模型配置入口。
 */

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Server } from "lucide-react";
import LLMConfigPanel from "./llm-config";

interface LLMConfigDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onModelsChange?: () => void;
}

export function LLMConfigDialog({
  open,
  onOpenChange,
  onModelsChange,
}: LLMConfigDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col p-0">
        <DialogHeader className="px-6 pt-6 pb-2">
          <DialogTitle className="flex items-center gap-2 text-base">
            <Server className="w-5 h-5" />
            模型配置
          </DialogTitle>
        </DialogHeader>
        <div className="flex-1 overflow-y-auto px-6 pb-6 min-h-0">
          <LLMConfigPanel onModelsChange={onModelsChange} />
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default LLMConfigDialog;
