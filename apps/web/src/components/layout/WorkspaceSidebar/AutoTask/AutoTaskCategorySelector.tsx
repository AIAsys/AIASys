import { Clock, Infinity as InfinityIcon } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

interface AutoTaskCategorySelectorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelectCategory: (category: "scheduled" | "continuous") => void;
}

export function AutoTaskCategorySelector({
  open,
  onOpenChange,
  onSelectCategory,
}: AutoTaskCategorySelectorProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>新建自动化任务</DialogTitle>
          <DialogDescription className="sr-only">
            选择自动化任务类别。
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 py-2">
          <button
            type="button"
            className={cn(
              "flex items-start gap-4 rounded-2xl border p-4 text-left transition",
              "border-border bg-background hover:border-foreground/20 hover:bg-muted/10",
            )}
            onClick={() => onSelectCategory("scheduled")}
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border bg-muted/15">
              <Clock className="h-5 w-5 text-muted-foreground" />
            </div>
            <div>
              <div className="text-sm font-semibold text-foreground">
                按时间触发
              </div>
              <div className="mt-1 text-[12px] leading-5 text-muted-foreground">
                立即、单次、周期或固定时间运行。适合巡检、简报、数据同步等周期性工作。
              </div>
            </div>
          </button>
          <button
            type="button"
            className={cn(
              "flex items-start gap-4 rounded-2xl border p-4 text-left transition",
              "border-border bg-background hover:border-foreground/20 hover:bg-muted/10",
            )}
            onClick={() => onSelectCategory("continuous")}
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border bg-muted/15">
              <InfinityIcon className="h-5 w-5 text-muted-foreground" />
            </div>
            <div>
              <div className="text-sm font-semibold text-foreground">
                连续推进
              </div>
              <div className="mt-1 text-[12px] leading-5 text-muted-foreground">
                绑定会话持续推进目标，直到达成目标或触发停止条件。适合需要多轮自动执行的复杂目标。
              </div>
            </div>
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
