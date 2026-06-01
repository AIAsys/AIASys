import {
  ArrowUp,
  Brain,
  FileText,
  FolderUp,
  Minimize2,
  ServerCog,
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
import { ModelSelector } from "./ModelSelector";
import { HistoryIcon } from "./chatShellIcons";

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
  onImportFromSession?: () => void;
  fileInputRef: RefObject<HTMLInputElement | null>;
  onFileChange: (e: ChangeEvent<HTMLInputElement>) => void;
  isUploading?: boolean;
  isPrewarming?: boolean;
  /** 当前 Python 环境名称（纯展示） */
  currentEnv?: { id?: string; name?: string; image?: string; sandbox_mode?: string } | null;
  /** 是否正在准备 Python 环境 */
  isInitializingEnvironment?: boolean;
  /** 当前会话ID */
  sessionId?: string;
  /** 当前会话是否已有消息 */
  hasMessages?: boolean;
  /** 是否正在压缩当前会话的上下文 */
  isCompactingConversation?: boolean;
  /** 压缩当前会话上下文 */
  onCompactConversation?: (instruction?: string) => Promise<void> | void;
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
  /** 打开 Python 环境面板 */
  onOpenRuntimeConfig?: () => void;
  /** 需要把焦点重新带回输入框时递增 */
  focusSignal?: number;
  /** 上传文件到工作区（不加入消息附件） */
  onUploadToWorkspace?: (files: FileList | File[]) => Promise<void> | void;
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
  onImportFromSession,
  fileInputRef,
  onFileChange,
  isUploading = false,
  isPrewarming = false,
  currentEnv,
  isInitializingEnvironment = false,
  sessionId,
  hasMessages = false,
  isCompactingConversation = false,
  onCompactConversation,
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
  onOpenRuntimeConfig,
  focusSignal,
  onUploadToWorkspace,
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

  // 上传文件到工作区（独立入口，不加入消息附件）
  const workspaceUploadInputRef = useRef<HTMLInputElement>(null);
  const handleWorkspaceUploadChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;
      if (!onUploadToWorkspace || isUploading || isPrewarming || isInitializingEnvironment) return;
      void onUploadToWorkspace(files);
      // 重置 input 以便重复选择同一文件
      e.target.value = "";
    },
    [onUploadToWorkspace, isUploading, isPrewarming, isInitializingEnvironment]
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
  const canCompactConversation =
    Boolean(sessionId) &&
    hasMessages &&
    !isRunning &&
    !isCompactingConversation;
  const compactTooltip = !sessionId
    ? "请先创建或切换到一个可用会话。"
    : !hasMessages
      ? "当前会话还没有可压缩的历史消息。"
      : isRunning
        ? "当前会话运行中，结束本轮执行后才能压缩上下文。"
        : isCompactingConversation
          ? "正在压缩上下文，请稍候。"
          : "压缩历史记录，不影响工作区文件和执行记录。";
  const runtimeLabel = currentEnv?.name?.trim() || "无 Python 环境";
  const runtimeMode =
    currentEnv?.sandbox_mode === "docker" || currentEnv?.image === "docker"
      ? "Docker"
    : currentEnv?.image === "uv"
      ? "Python"
      : currentEnv?.image === "none" || currentEnv?.id === "none"
        ? "Python"
        : currentEnv?.image || "Python";

  return (
    <div className="p-4 md:p-6 bg-muted relative">
      <div className="max-w-4xl mx-auto rounded-xl border shadow-sm p-4 min-h-[120px] relative flex flex-col transition-colors bg-muted border-border">
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
                  >
                    <X size={12} />
                  </button>
                </div>
              );
            })}
          </div>
        )}

        <textarea
          ref={textareaRef}
          value={inputValue}
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
              : isUploading
                ? "文件正在上传中..."
                : "询问任何问题"
          }
          disabled={isUploading || isPrewarming || isInitializingEnvironment}
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
                <button
                  type="button"
                  onClick={() => {
                    onImportFromSession?.();
                    setShowAttachments(false);
                  }}
                  className="w-full text-left px-4 py-2 hover:bg-accent flex items-center gap-2 text-sm text-foreground transition-colors"
                >
                    <HistoryIcon className="h-4 w-4" />
                    <span className="font-mono">从历史导入</span>
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
              disabled={isUploading || isPrewarming || isInitializingEnvironment}
            >
              <Upload size={18} />
            </button>

            {/* 上传文件到工作区 */}
            {onUploadToWorkspace ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={() => workspaceUploadInputRef.current?.click()}
                    className="flex-shrink-0 p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                    title="上传文件到工作区"
                    disabled={isUploading || isPrewarming || isInitializingEnvironment}
                  >
                    <FolderUp size={18} />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top" sideOffset={6}>
                  上传文件到工作区
                </TooltipContent>
              </Tooltip>
            ) : null}
            <input
              ref={workspaceUploadInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={handleWorkspaceUploadChange}
              title="上传文件到工作区"
              aria-label="上传文件到工作区"
            />

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

            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={onOpenRuntimeConfig}
                  disabled={!onOpenRuntimeConfig}
                  className="flex min-w-0 max-w-[168px] flex-shrink items-center gap-1.5 rounded-md bg-secondary px-2.5 py-2 text-left text-xs text-secondary-foreground transition-colors hover:bg-secondary/80 disabled:cursor-default disabled:opacity-80"
                  data-testid="input-runtime-env"
                  aria-label={`当前 Python 环境：${runtimeLabel}`}
                >
                  <ServerCog className="h-4 w-4 flex-shrink-0" />
                  <span className="flex-shrink-0 font-medium">
                    {runtimeMode}
                  </span>
                  <span className="min-w-0 truncate text-muted-foreground">
                    {runtimeLabel}
                  </span>
                </button>
              </TooltipTrigger>
              <TooltipContent side="top" sideOffset={6}>
                {onOpenRuntimeConfig
                  ? `当前 Python 环境：${runtimeLabel}。点击管理 Python 环境`
                  : `当前 Python 环境：${runtimeLabel}`}
              </TooltipContent>
            </Tooltip>

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

            {sessionId && onCompactConversation ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={() => {
                      if (!canCompactConversation) {
                        return;
                      }
                      void onCompactConversation();
                    }}
                    disabled={!canCompactConversation}
                    className="flex-shrink-0 inline-flex items-center gap-1.5 rounded-md bg-secondary px-2.5 py-2 text-xs text-secondary-foreground transition-colors hover:bg-secondary/80 disabled:cursor-not-allowed disabled:opacity-50"
                    title="压缩上下文"
                    aria-label="压缩上下文"
                    data-testid="input-compact-conversation"
                  >
                    <Minimize2 className="h-4 w-4" />
                    <span className="font-medium">
                      {isCompactingConversation ? "压缩中" : "压缩"}
                    </span>
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top" sideOffset={6}>
                  {compactTooltip}
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
                !inputValue.trim() || isRunning || isUploading || isPrewarming || isInitializingEnvironment
              }
              className={`p-2 rounded-md transition-all font-mono ${
                inputValue.trim() && !isRunning && !isUploading && !isPrewarming && !isInitializingEnvironment
                  ? "bg-foreground text-background hover:bg-foreground/90"
                  : "bg-muted text-muted-foreground cursor-not-allowed"
              }`}
              title={
                isInitializingEnvironment || isPrewarming
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
