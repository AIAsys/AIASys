/**
 * ChatArea Context - 提供消息渲染所需的状态和动作
 *
 * 遵循 State-Context-Interface 模式，将状态管理从 UI 中解耦
 */
import { createContext, useContext } from "react";
import type { ChatItem } from "@/pages/DataAnalysisPage/types";
import type { PreviewFile } from "@/components/layout/WorkspaceSidebar/preview";

// Context 状态接口
interface ChatAreaState {
  /** 当前消息项 */
  item: ChatItem;
  /** 是否为当前用户的消息 */
  isUser: boolean;
}

// Context Actions 接口
interface ChatAreaActions {
  /** 查看执行空间 */
  onViewExecutionSpace?: (taskId: string) => void;
  /** Worker 点击回调 */
  onWorkerClick?: (workerName: string) => void;
  /** 在主画布打开工作区产物 */
  onOpenWorkspaceArtifact?: (file: PreviewFile) => void;
  /** 查看工具调用详情 - 包含触发元素位置用于悬浮窗定位 */
  onViewToolDetails?: (
    toolCallId: string,
    taskId: string | undefined,
    triggerRect: DOMRect,
  ) => void;
  /** 编辑用户消息并从该消息处重新发送 */
  onRewriteUserMessage?: (
    messageId: string,
    content: string,
    originalContent?: string,
  ) => Promise<void> | void;
}

type ChatAreaLayout = "default" | "compact" | "rail";

// Context Meta 接口
interface ChatAreaMeta {
  /** 当前消息的附件列表 */
  attachments?: string[];
  /** 当前会话 ID (用于加载工作区图片) */
  sessionId?: string;
  /** 聊天区布局模式 */
  layout?: ChatAreaLayout;
  /** 当前会话是否正在运行 */
  isRunning?: boolean;
}

// 完整的 Context Value 接口
interface ChatAreaContextValue {
  state: ChatAreaState;
  actions: ChatAreaActions;
  meta: ChatAreaMeta;
}

const ChatAreaContext = createContext<ChatAreaContextValue | null>(null);

export function useChatAreaContext() {
  const context = useContext(ChatAreaContext);
  if (!context) {
    throw new Error("useChatAreaContext must be used within ChatAreaProvider");
  }
  return context;
}

export {
  ChatAreaContext,
  type ChatAreaContextValue,
  type ChatAreaState,
  type ChatAreaActions,
  type ChatAreaMeta,
  type ChatAreaLayout,
};
