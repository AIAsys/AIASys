/**
 * AiMessageContent Context
 *
 * 提供 AI 消息内容渲染所需的状态和动作
 */
import { createContext, useContext } from "react";
import type { ChatSegment, WorkerRecord } from "@/pages/WorkspacePage/types";
import type { PreviewFile } from "@/components/layout/WorkspaceSidebar/preview";

// Context 状态接口
interface AiMessageState {
  /** 思考内容 */
  thoughts: string;
  /** Host Agent 思考过程 (think segments) */
  thinks: ChatSegment[];
  /** 是否正在思考 */
  isThinking: boolean;
  /** 是否已终止 */
  isStopped: boolean;
  /** 是否为空 */
  isEmpty: boolean;
  /** 是否正在流式输出 */
  isStreaming: boolean;
  /** 工具列表 */
  tools: ChatSegment[];
  /** 最终回答内容 */
  finalAnswer: string;
  /** Worker 活动记录 */
  workerActivities: WorkerRecord[];
  /** Monitor 后台命令输出 */
  monitors: ChatSegment[];
}

// Context Actions 接口
interface AiMessageActions {
  /** Worker 点击回调 */
  onWorkerClick?: (workerName: string) => void;
}

// Context Meta 接口
interface AiMessageMeta {
  /** 认证 token */
  token?: string;
  /** 会话 ID (用于加载工作区图片) */
  sessionId?: string;
  /** 在主画布打开工作区产物 */
  onOpenWorkspaceArtifact?: (file: PreviewFile) => void;
}

// 完整的 Context Value 接口
interface AiMessageContextValue {
  state: AiMessageState;
  actions: AiMessageActions;
  meta: AiMessageMeta;
}

const AiMessageContext = createContext<AiMessageContextValue | null>(null);

export function useAiMessageContext() {
  const context = useContext(AiMessageContext);
  if (!context) {
    throw new Error(
      "useAiMessageContext must be used within AiMessageProvider",
    );
  }
  return context;
}

export {
  AiMessageContext,
  type AiMessageContextValue,
  type AiMessageState,
  type AiMessageActions,
  type AiMessageMeta,
  type ChatSegment,
  type WorkerRecord,
};
