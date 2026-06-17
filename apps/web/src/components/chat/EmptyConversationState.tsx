/**
 * EmptyConversationState - 空对话引导状态
 *
 * 新工作区/新对话的 empty state，引导用户开始第一次交互。
 */
import { FileText, Lightbulb, Sparkles, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";

interface EmptyConversationStateProps {
  /** 点击示例问题，将文本填入输入框 */
  onExampleClick?: (text: string) => void;
  /** 点击上传文件按钮 */
  onAddFileClick?: () => void;
}

const EXAMPLE_QUESTIONS = [
  "帮我分析这份数据的趋势并画图",
  "阅读这个 PDF 并总结要点",
  "写一个 Python 脚本批量重命名文件",
  "帮我整理这段时间的实验结果",
];

export function EmptyConversationState({
  onExampleClick,
  onAddFileClick,
}: EmptyConversationStateProps) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12">
      <div className="w-full max-w-md space-y-6 text-center">
        {/* 标题 */}
        <div className="space-y-2">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10">
            <Sparkles className="h-6 w-6 text-primary" />
          </div>
          <h2 className="text-lg font-semibold text-foreground">
            开始你的任务
          </h2>
          <p className="text-sm leading-6 text-muted-foreground">
            向 AI 提问、上传文件或拖入文件夹开始工作
          </p>
        </div>

        {/* 示例问题 */}
        <div className="space-y-2 text-left">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
            <Lightbulb className="h-3 w-3" />
            示例
          </div>
          {EXAMPLE_QUESTIONS.map((question) => (
            <button
              key={question}
              type="button"
              onClick={() => onExampleClick?.(question)}
              className="flex w-full items-center gap-2 rounded-lg border border-border bg-background px-3 py-2.5 text-left text-sm text-foreground transition-colors hover:border-tertiary/40 hover:bg-muted/30"
            >
              <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <span className="min-w-0">{question}</span>
            </button>
          ))}
        </div>

        {/* 操作按钮 */}
        {onAddFileClick ? (
          <div className="flex items-center justify-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onAddFileClick}
            >
              <Upload className="mr-1.5 h-3.5 w-3.5" />
              选择文件
            </Button>
          </div>
        ) : null}

        <p className="text-[11px] text-muted-foreground/70">
          也可以直接拖拽文件或文件夹到输入框
        </p>
      </div>
    </div>
  );
}
