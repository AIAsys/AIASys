import {
  ArrowUp,
  Brain,
  Container,
  FileText,
  FlaskConical,
  SlidersHorizontal,
  StopCircle,
  Upload,
  X,
} from "lucide-react";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import {
  type ChangeEvent,
  type KeyboardEvent,
  type RefObject,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import type { LLMModelConfig } from "@/lib/api/llm";
import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import { extractClipboardFiles } from "@/utils/clipboardFiles";
import { useDragDrop } from "@/hooks/useDragDrop";
import {
  WORKSPACE_FILE_DRAG_MIME,
  type WorkspaceFileReferenceDragPayload,
} from "@/utils/workspaceFileDrag";
import { cn } from "@/lib/utils";
import { ModelSelector } from "./ModelSelector";

interface UploadedFile {
  filename: string;
  file_path?: string;
  size: number;
  progress?: number;
}

interface InputAreaProps {
  inputValue: string;
  onInputChange: (value: string) => void;
  onSubmit: () => void;
  onKeyDown: (e: KeyboardEvent<HTMLTextAreaElement>) => void;
  isRunning: boolean;
  onStop: () => void;
  uploadedFiles: UploadedFile[];
  onRemoveFile: (index: number) => void;
  onAddFileClick: () => void;
  fileInputRef: RefObject<HTMLInputElement | null>;
  onFileChange: (e: ChangeEvent<HTMLInputElement>) => void;
  isUploading?: boolean;
  /** 当前上传进度 0-100，null 表示不在上传中 */
  uploadProgress?: number | null;
  isPrewarming?: boolean;
  /** 是否正在准备 Python 环境 */
  isInitializingEnvironment?: boolean;
  /** 当前会话ID */
  sessionId?: string;
  /** 是否正在压缩当前会话的上下文 */
  isCompactingConversation?: boolean;
  /** 工作区是否已配置 MCP */
  hasMCPConfig?: boolean;
  /** 用户自定义的 LLM 模型列表 */
  userModels?: LLMModelConfig[];
  /** 当前选中的模型 ID（用户自定义时）或 'system'（系统默认时） */
  selectedModelId?: string;
  /** 当前优先级链路解析后的生效模型显示名 */
  effectiveModelDisplayName?: string | null;
  /** 选择模型回调 */
  onSelectModel?: (modelId: string) => Promise<void> | void;
  thinkingEnabled?: boolean;
  thinkingEffort?: "low" | "medium" | "high";
  setThinkingEnabled?: (enabled: boolean) => void;
  setThinkingEffort?: (effort: "low" | "medium" | "high") => void;
  selectedModelSupportsThinking?: boolean;
  /** 跳转到配置页面 */
  onOpenConfig?: () => void;
  /** 打开当前会话工具配置 */
  onOpenToolConfig?: () => void;
  /** 打开执行资源面板 */
  onOpenRuntimeTab?: () => void;
  /** 当前运行环境信息 */
  activeEnv?: {
    id: string;
    name: string;
    image: string;
    sandbox_mode?: string;
  } | null;
  /** 需要把焦点重新带回输入框时递增 */
  focusSignal?: number;
}

export function InputArea({
  inputValue,
  onInputChange,
  onSubmit,
  onKeyDown,
  isRunning,
  onStop,
  uploadedFiles,
  onRemoveFile,
  onAddFileClick,
  fileInputRef,
  onFileChange,
  isUploading = false,
  uploadProgress = null,
  isPrewarming = false,
  isInitializingEnvironment = false,
  sessionId,
  isCompactingConversation = false,
  userModels = [],
  selectedModelId,
  effectiveModelDisplayName,
  onSelectModel,
  thinkingEnabled = false,
  thinkingEffort = "high",
  setThinkingEnabled,
  setThinkingEffort,
  selectedModelSupportsThinking = false,
  onOpenConfig,
  onOpenToolConfig,
  onOpenRuntimeTab,
  activeEnv,
  focusSignal,
}: InputAreaProps) {
  const isImageFile = (filename: string) =>
    /\.(png|jpe?g|gif|webp)$/i.test(filename);

  const [showAttachments, setShowAttachments] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // 自动调整 textarea 高度
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      const newHeight = Math.min(Math.max(textarea.scrollHeight, 60), 240);
      textarea.style.height = `${newHeight}px`;
    }
  }, [inputValue]);

  useEffect(() => {
    if (!focusSignal) {
      return;
    }

    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    const frameId = window.requestAnimationFrame(() => {
      textarea.focus();
      const cursor = textarea.value.length;
      textarea.setSelectionRange(cursor, cursor);
    });

    return () => window.cancelAnimationFrame(frameId);
  }, [focusSignal]);

  // 点击外部关闭弹窗
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setShowAttachments(false);
      }
    };

    if (showAttachments) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showAttachments]);

  // 拖拽文件到输入框，作为消息附件
  const handleWorkspaceDrop = useCallback(
    (files: FileList) => {
      if (!onFileChange || isUploading || isPrewarming || isInitializingEnvironment) return;
      const mockEvent = {
        target: { files },
      } as React.ChangeEvent<HTMLInputElement>;
      onFileChange(mockEvent);
    },
    [onFileChange, isUploading, isPrewarming, isInitializingEnvironment],
  );
  const {
    isDragging,
    dragProps: {
      onDragEnter: onWorkspaceDragEnter,
      onDragOver: onWorkspaceDragOver,
      onDragLeave: onWorkspaceDragLeave,
      onDrop: onWorkspaceDropEvent,
    },
  } = useDragDrop(handleWorkspaceDrop);

  const [isReferenceDragging, setIsReferenceDragging] = useState(false);

  const hasWorkspaceFileReference = useCallback(
    (dataTransfer: DataTransfer) => {
      return Array.from(dataTransfer.types).includes(WORKSPACE_FILE_DRAG_MIME);
    },
    [],
  );

  const insertReferencePaths = useCallback(
    (paths: string[]) => {
      const textarea = textareaRef.current;
      if (!textarea) return;

      const textToInsert = paths.join(" ");
      if (!textToInsert) return;

      const start = textarea.selectionStart ?? 0;
      const end = textarea.selectionEnd ?? 0;
      const before = inputValue.slice(0, start);
      const after = inputValue.slice(end);
      const needsLeadingSpace = before.length > 0 && !/\s$/.test(before);
      const needsTrailingSpace = after.length > 0 && !/^\s/.test(after);
      const inserted =
        (needsLeadingSpace ? " " : "") +
        textToInsert +
        (needsTrailingSpace ? " " : "");
      const newValue = before + inserted + after;
      onInputChange(newValue);

      // 光标放到插入内容之后
      const newCursor = start + inserted.length;
      requestAnimationFrame(() => {
        textarea.focus();
        textarea.setSelectionRange(newCursor, newCursor);
      });
    },
    [inputValue, onInputChange],
  );

  /**
   * 从 DataTransfer 解析工作区文件引用路径。
   * 优先使用自定义 MIME payload；某些浏览器/环境下自定义 MIME 不可用，
   * 则回退到 text/plain（FileTreeRow 单文件拖拽时会写入原始文件名）。
   */
  const extractReferencePaths = useCallback(
    (dataTransfer: DataTransfer): string[] => {
      if (Array.from(dataTransfer.types).includes(WORKSPACE_FILE_DRAG_MIME)) {
        const raw = dataTransfer.getData(WORKSPACE_FILE_DRAG_MIME);
        if (raw) {
          try {
            const payload = JSON.parse(raw) as WorkspaceFileReferenceDragPayload;
            if (payload.paths && payload.paths.length > 0) {
              return payload.paths;
            }
          } catch {
            // 解析失败继续尝试回退
          }
        }
      }

      // 回退：text/plain 中的单个文件名，按当前工作区路径补全
      const plain = dataTransfer.getData("text/plain");
      if (plain && !plain.includes("\n") && !plain.includes("/")) {
        return [`/workspace/${plain}`];
      }

      return [];
    },
    [],
  );

  const handleReferenceDrop = useCallback(
    (e: React.DragEvent) => {
      const paths = extractReferencePaths(e.dataTransfer);
      if (paths.length === 0) return false;

      e.preventDefault();
      e.stopPropagation();
      setIsReferenceDragging(false);
      insertReferencePaths(paths);
      return true;
    },
    [extractReferencePaths, insertReferencePaths],
  );

  const handleReferenceDragOver = useCallback(
    (e: React.DragEvent) => {
      if (!hasWorkspaceFileReference(e.dataTransfer)) return;
      e.preventDefault();
      e.stopPropagation();
      e.dataTransfer.dropEffect = "copy";
      setIsReferenceDragging(true);
    },
    [hasWorkspaceFileReference],
  );

  const handleReferenceDragLeave = useCallback(
    (e: React.DragEvent) => {
      if (!isReferenceDragging) return;
      e.preventDefault();
      e.stopPropagation();
      setIsReferenceDragging(false);
    },
    [isReferenceDragging],
  );

  // 处理粘贴文件
  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      const pastedFiles = extractClipboardFiles(e.clipboardData);
      if (pastedFiles.length === 0) return;

      // 阻止默认粘贴行为，改走统一文件上传链路。
      e.preventDefault();

      if (!onFileChange || isUploading || isPrewarming || isInitializingEnvironment) {
        return;
      }

      // 构造虚拟 ChangeEvent 以复用系统文件上传处理流程
      const dt = new DataTransfer();
      pastedFiles.forEach((f) => dt.items.add(f));
      const mockEvent = {
        target: { files: dt.files },
      } as React.ChangeEvent<HTMLInputElement>;
      onFileChange(mockEvent);
    },
    [onFileChange, isUploading, isPrewarming, isInitializingEnvironment]
  );

  return (
    <div
      className="p-4 md:p-6 bg-muted relative"
      onDragEnter={onWorkspaceDragEnter}
      onDragOver={(e) => {
        handleReferenceDragOver(e);
        onWorkspaceDragOver(e);
      }}
      onDragLeave={(e) => {
        handleReferenceDragLeave(e);
        onWorkspaceDragLeave(e);
      }}
      onDrop={(e) => {
        if (handleReferenceDrop(e)) return;
        onWorkspaceDropEvent(e);
      }}
    >
      <div
        className={cn(
          "max-w-4xl mx-auto rounded-xl border shadow-sm p-4 min-h-[120px] relative flex flex-col transition-colors",
          isDragging || isReferenceDragging
            ? "bg-primary/5 border-primary/30 ring-1 ring-primary/20"
            : "bg-muted border-border",
        )}
      >
        {/* 待发送附件预览 */}
        {uploadedFiles.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {uploadedFiles.map((file, idx) => {
              const isImage = isImageFile(file.filename);
              return (
                <div
                  key={file.file_path || file.filename}
                  className="group relative flex items-center gap-2 pl-2 pr-1 py-1 text-sm border border-border rounded-lg bg-background/80 hover:bg-accent/50 transition-colors"
                >
                  {isImage && sessionId ? (
                    <div className="flex items-center gap-2">
                      <img
                        src={`${API_ENDPOINTS.FILES_DOWNLOAD(getCurrentUserId(), sessionId, file.filename)}?user_id=${getCurrentUserId()}`}
                        alt=""
                        className="h-8 w-8 rounded object-cover border border-border flex-shrink-0"
                        onError={(e) => {
                          (e.currentTarget as HTMLImageElement).style.display = "none";
                        }}
                      />
                      <span className="truncate max-w-[100px] text-xs text-muted-foreground">
                        {file.filename}
                      </span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <FileText size={14} className="text-muted-foreground flex-shrink-0" />
                      <span className="truncate max-w-[120px] text-xs text-muted-foreground">
                        {file.filename}
                      </span>
                    </div>
                  )}
                  <button
                    type="button"
                    className="ml-1 p-0.5 rounded-full text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                    onClick={() => onRemoveFile(idx)}
                    title="移除附件"
                    aria-label="移除附件"
                  >
                    <X size={12} />
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {/* 上传进度条 */}
        {isUploading && uploadProgress !== null && (
          <div className="mb-2 flex items-center gap-2">
            <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
              <div
                className="h-full bg-primary transition-all duration-150 ease-out rounded-full"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
            <span className="text-xs text-muted-foreground font-mono tabular-nums w-9 text-right">
              {uploadProgress}%
            </span>
          </div>
        )}

        <textarea
          ref={textareaRef}
          value={inputValue}
          aria-label="消息输入框"
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={(e) => {
            // 如果正在初始化环境，阻止键盘事件
            if (isInitializingEnvironment) {
              e.preventDefault();
              return;
            }
            onKeyDown(e);
          }}
          onPaste={handlePaste}
          placeholder={
            isInitializingEnvironment || isPrewarming
              ? "工作区准备中，请稍候..."
              : isCompactingConversation
                ? "正在压缩上下文，请稍候..."
                : isUploading
                  ? "文件正在上传中..."
                  : "可以拖拽、上传文件，并询问任何问题"
          }
          disabled={isUploading || isPrewarming || isInitializingEnvironment || isCompactingConversation}
          rows={1}
          className="w-full flex-1 resize-none outline-none text-base text-foreground placeholder:text-muted-foreground bg-transparent disabled:opacity-50 disabled:cursor-not-allowed min-h-[60px] max-h-[240px] overflow-y-auto"
        />

        {/* 底部按钮区 -- 文件显示已移至右侧工作区 */}
        <div className="flex items-end mt-2 gap-2">
          <div className="flex items-center gap-1 relative flex-1 flex-wrap" ref={containerRef}>
            {/* 附件菜单弹窗（必须在 containerRef 内部，否则 click-outside 会在 click 前移除菜单） */}
            {showAttachments && (
              <div className="absolute left-0 bottom-full mb-1 w-48 bg-popover border border-border rounded-lg shadow-lg py-1 z-10">
                <button
                  type="button"
                  onClick={() => {
                    onAddFileClick();
                    setShowAttachments(false);
                  }}
                  className="w-full text-left px-4 py-2 hover:bg-accent flex items-center gap-2 text-sm text-foreground transition-colors"
                >
                  <Upload size={16} />
                  <span className="font-mono">本地上传</span>
                </button>
                </div>
            )}
            {/* 添加文件按钮 */}
            <button
              type="button"
              onClick={() => setShowAttachments(!showAttachments)}
              className={`flex-shrink-0 p-2 rounded-md transition-colors ${
                showAttachments
                  ? "bg-foreground/10 text-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent"
              }`}
              title="添加附件"
              aria-label="添加附件"
              disabled={isUploading || isPrewarming || isInitializingEnvironment}
            >
              <Upload size={18} />
            </button>

            {/* 模型选择区域 - 类似 OpenAI/Claude 的下拉菜单 */}
            <ModelSelector
              userModels={userModels}
              selectedModelId={selectedModelId}
              effectiveModelDisplayName={effectiveModelDisplayName}
              onSelectModel={onSelectModel}
              thinkingEnabled={thinkingEnabled}
              thinkingEffort={thinkingEffort}
              setThinkingEnabled={setThinkingEnabled}
              setThinkingEffort={setThinkingEffort}
              selectedModelSupportsThinking={selectedModelSupportsThinking}
              onOpenConfig={onOpenConfig}
              disabled={
                isRunning ||
                isInitializingEnvironment ||
                isPrewarming ||
                isCompactingConversation
              }
            />

            {selectedModelSupportsThinking && setThinkingEnabled ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={() => setThinkingEnabled(!thinkingEnabled)}
                    disabled={
                      isRunning ||
                      isInitializingEnvironment ||
                      isPrewarming ||
                      isCompactingConversation
                    }
                    className={`flex-shrink-0 inline-flex items-center justify-center rounded-md p-2 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                      thinkingEnabled
                        ? "bg-primary/10 text-primary hover:bg-primary/20"
                        : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
                    }`}
                    title={thinkingEnabled ? `Thinking 已开启 (${thinkingEffort})` : "Thinking 已关闭"}
                    aria-label={thinkingEnabled ? `Thinking 已开启，强度 ${thinkingEffort}` : "Thinking 已关闭"}
                  >
                    <Brain className="h-4 w-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top" sideOffset={6}>
                  {thinkingEnabled
                    ? `Thinking 已开启（强度 ${thinkingEffort}），点击关闭`
                    : "Thinking 已关闭，点击开启"}
                </TooltipContent>
              </Tooltip>
            ) : null}

            {onOpenToolConfig ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={onOpenToolConfig}
                    disabled={!sessionId}
                    className="flex-shrink-0 inline-flex items-center justify-center rounded-md bg-secondary p-2 text-xs text-secondary-foreground transition-colors hover:bg-secondary/80 disabled:cursor-not-allowed disabled:opacity-50"
                    title="当前会话工具配置"
                    aria-label="当前会话工具配置"
                    data-testid="input-tool-config"
                  >
                    <SlidersHorizontal className="h-4 w-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top" sideOffset={6}>
                  当前会话工具配置
                </TooltipContent>
              </Tooltip>
            ) : null}

            {/* 运行环境状态徽标 */}
            {activeEnv && onOpenRuntimeTab ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={onOpenRuntimeTab}
                    disabled={isInitializingEnvironment}
                    className={cn(
                      "flex-shrink-0 inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-[11px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                      activeEnv.image === "none"
                        ? "bg-warning/10 text-warning hover:bg-warning/20"
                        : activeEnv.image === "docker"
                          ? "bg-info/10 text-info hover:bg-info/20"
                          : "bg-success/10 text-success hover:bg-success/20",
                    )}
                    aria-label={`运行环境：${activeEnv.name}`}
                  >
                    {activeEnv.image === "docker" ? (
                      <Container className="h-3.5 w-3.5" />
                    ) : activeEnv.image === "none" ? (
                      <FlaskConical className="h-3.5 w-3.5" />
                    ) : (
                      <FlaskConical className="h-3.5 w-3.5" />
                    )}
                    <span className="max-w-[120px] truncate">
                      {activeEnv.image === "none" ? "未配置环境" : activeEnv.name}
                    </span>
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top" sideOffset={6}>
                  {activeEnv.image === "none"
                    ? "未配置运行环境，点击配置"
                    : `运行环境：${activeEnv.name}，点击管理`}
                </TooltipContent>
              </Tooltip>
            ) : null}

            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={onFileChange}
              title="上传文件"
              aria-label="上传文件"
            />
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            {/* 停止按钮 */}
            {isRunning && (
              <button
                type="button"
                onClick={onStop}
                className="p-2 rounded-md bg-destructive/10 hover:bg-destructive/20 text-destructive transition-colors"
                title="停止"
                aria-label="停止"
              >
                <StopCircle size={18} />
              </button>
            )}

            {/* 发送按钮 */}
            <button
              type="button"
              onClick={() => {
                // 如果正在初始化环境，阻止提交
                if (isInitializingEnvironment) {
                  return;
                }
                onSubmit();
              }}
              disabled={
                !inputValue.trim() || isRunning || isUploading || isPrewarming || isInitializingEnvironment || isCompactingConversation
              }
              className={`p-2 rounded-md transition-all font-mono ${
                inputValue.trim() && !isRunning && !isUploading && !isPrewarming && !isInitializingEnvironment && !isCompactingConversation
                  ? "bg-foreground text-background hover:bg-foreground/90"
                  : "bg-muted text-muted-foreground cursor-not-allowed"
              }`}
              title={
                isCompactingConversation
                  ? "正在压缩上下文"
                  : isInitializingEnvironment || isPrewarming
                    ? "工作区准备中"
                    : isUploading
                      ? "文件上传中"
                      : "发送"
              }
              aria-label={
                isCompactingConversation
                  ? "正在压缩上下文"
                  : isInitializingEnvironment || isPrewarming
                    ? "工作区准备中"
                    : isUploading
                      ? "文件上传中"
                      : "发送"
              }
            >
              <ArrowUp size={18} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
