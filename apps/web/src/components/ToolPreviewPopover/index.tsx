/**
 * ToolPreviewPopover - 工具调用悬浮预览
 *
 * 显示单个工具的输入参数和执行结果
 * 以悬浮卡片形式展示，不占用固定侧边栏空间
 */
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  X,
  Wrench,
  FileOutput,
  Clock,
  ChevronRight,
  Terminal,
  Globe,
  FileText,
  Network,
} from "lucide-react";

function getToolDisplayLabel(toolName: string): string {
  switch (toolName) {
    case "LocalIPythonBox":
    case "IPythonBox":
      return "本地笔记本执行";
    case "RunNotebookTool":
      return "运行笔记本";
    case "EditNotebookFileTool":
      return "编辑笔记本";
    case "ListSessionNotebooksTool":
      return "笔记本列表";
    case "CreateSessionNotebookTool":
      return "新建笔记本";
    case "ReadNotebookOutputsTool":
      return "读取笔记本输出";
    default:
      return toolName;
  }
}

// 辅助函数：基于工具名称推断显示图标和配套颜色
function getToolDisplayConfig(toolName: string) {
  switch (toolName) {
    case "LocalIPythonBox":
    case "IPythonBox":
    case "RunNotebookTool":
    case "Shell":
      return {
        Icon: Terminal,
        bgClass: "bg-tertiary/10",
        textClass: "text-tertiary dark:text-tertiary",
      };
    case "EditNotebookFileTool":
    case "ListSessionNotebooksTool":
    case "CreateSessionNotebookTool":
    case "ReadNotebookOutputsTool":
      return {
        Icon: FileText,
        bgClass: "bg-info/10",
        textClass: "text-info dark:text-info",
      };
    case "SearchWeb":
    case "FetchURL":
      return {
        Icon: Globe,
        bgClass: "bg-info/10",
        textClass: "text-info dark:text-info",
      };
    case "ReadFile":
    case "WriteFile":
    case "StrReplaceFile":
    case "ReadMediaFile":
    case "Grep":
    case "Glob":
      return {
        Icon: FileText,
        bgClass: "bg-success/10",
        textClass: "text-success dark:text-success",
      };
    case "Task":
    case "CreateSubagent":
      return {
        Icon: Network,
        bgClass: "bg-warning/10",
        textClass: "text-warning dark:text-warning",
      };
    default:
      return {
        Icon: Wrench,
        bgClass: "bg-primary/10",
        textClass: "text-primary",
      };
  }
}

interface ToolPreviewPopoverProps {
  /** 是否显示 */
  isOpen: boolean;
  /** 关闭回调 */
  onClose: () => void;
  /** 工具名称 */
  toolName: string;
  /** 工具参数 */
  toolParams?: Record<string, unknown>;
  /** 工具输出 */
  toolOutput?: string;
  /** 关联的任务 ID */
  taskId?: string;
  /** 触发元素的位置（用于定位悬浮窗） */
  triggerRect?: DOMRect | null;
}

export function ToolPreviewPopover({
  isOpen,
  onClose,
  toolName,
  toolParams,
  toolOutput,
  taskId,
  triggerRect,
}: ToolPreviewPopoverProps) {
  const popoverRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  // 计算悬浮窗位置
  useEffect(() => {
    if (!isOpen || !popoverRef.current) return;

    const popover = popoverRef.current;
    const rect = popover.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    let top = 100;
    let left = viewportWidth - rect.width - 20;

    // 如果有触发元素位置，尝试在触发元素附近显示
    if (triggerRect) {
      // 优先显示在触发元素右侧
      left = triggerRect.right + 10;
      top = triggerRect.top;

      // 如果右侧空间不足，显示在左侧
      if (left + rect.width > viewportWidth - 10) {
        left = triggerRect.left - rect.width - 10;
      }

      // 如果顶部超出视口，调整到底部
      if (top + rect.height > viewportHeight - 10) {
        top = viewportHeight - rect.height - 10;
      }

      // 确保不超出左侧
      if (left < 10) {
        left = 10;
      }

      // 确保不超出顶部
      if (top < 10) {
        top = 10;
      }
    }

    setPosition({ top, left });
  }, [isOpen, triggerRect]);

  // 点击外部关闭
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node)
      ) {
        onClose();
      }
    };

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [isOpen, onClose]);

  if (!isOpen || !isMounted || typeof document === "undefined") return null;

  const hasParams = toolParams && Object.keys(toolParams).length > 0;
  const hasOutput = toolOutput && toolOutput.length > 0;

  const { Icon: ToolIcon, bgClass, textClass } = getToolDisplayConfig(toolName);

  return createPortal(
    <div
      ref={popoverRef}
      className="fixed z-[80] w-[480px] max-h-[70vh] bg-popover rounded-xl shadow-2xl border border-border overflow-hidden animate-in fade-in zoom-in-95 duration-200"
      style={{
        top: position.top,
        left: position.left,
      }}
    >
      {/* 头部 */}
      <div className="flex items-center justify-between px-4 py-3 bg-muted border-b border-border">
        <div className="flex items-center gap-2">
          <div
            className={`w-7 h-7 rounded-lg flex items-center justify-center ${bgClass}`}
          >
            <ToolIcon className={`w-3.5 h-3.5 ${textClass}`} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">
              {getToolDisplayLabel(toolName)}
            </h3>
            {taskId && taskId !== "host" && (
              <p className="text-[10px] text-muted-foreground">
                Task: {taskId.slice(0, 8)}...
              </p>
            )}
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 hover:bg-accent rounded-md text-muted-foreground hover:text-foreground transition-colors"
          title="关闭"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* 内容区域 */}
      <div className="overflow-y-auto max-h-[calc(70vh-60px)]">
        {/* 工具输入 */}
        <div className="p-4 border-b border-border">
          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground mb-2">
            <ChevronRight className="w-3 h-3" />
            输入参数
          </div>
          <div className="bg-muted rounded-lg border border-border overflow-hidden">
            {hasParams ? (
              <div className="p-3 text-[11px] space-y-3">
                {Object.entries(toolParams).map(([key, value]) => {
                  let isCodeBlock = false;
                  let displayValue = "";

                  if (typeof value === "string") {
                    const formattedStr = value.replace(/\\n/g, "\n");
                    isCodeBlock =
                      formattedStr.includes("\n") || formattedStr.length > 60;
                    displayValue = formattedStr;
                  } else {
                    displayValue =
                      typeof value === "object"
                        ? JSON.stringify(value, null, 2)
                        : String(value);
                    isCodeBlock = typeof value === "object";
                  }

                  return (
                    <div key={key} className="flex flex-col gap-1.5">
                      <span className="text-muted-foreground font-semibold">
                        {key}:
                      </span>
                      {isCodeBlock ? (
                        <pre className="bg-foreground text-muted-foreground p-2.5 rounded-md whitespace-pre-wrap font-mono border border-border break-all max-h-[300px] overflow-y-auto">
                          {displayValue}
                        </pre>
                      ) : (
                        <code className="text-foreground bg-background px-2 py-1.5 rounded-md border border-border whitespace-pre-wrap break-all font-mono">
                          {displayValue}
                        </code>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="p-3 text-[11px] text-muted-foreground italic">
                无参数
              </div>
            )}
          </div>
        </div>

        {/* 工具输出 */}
        <div className="p-4">
          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground mb-2">
            <FileOutput className="w-3 h-3" />
            执行结果
          </div>
          <div className="bg-foreground rounded-lg overflow-hidden">
            {hasOutput ? (
              <div className="p-3 text-[11px] text-muted-foreground font-mono whitespace-pre-wrap max-h-60 overflow-y-auto">
                {toolOutput}
              </div>
            ) : (
              <div className="p-3 text-[11px] text-muted-foreground italic flex items-center gap-2">
                <Clock className="w-3 h-3 animate-spin" />
                等待执行结果...
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
    ,
    document.body,
  );
}
