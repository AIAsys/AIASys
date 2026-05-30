/**
 * Per-Session State Registry
 *
 * 每个 session 独立维护流状态、聊天、任务等数据。
 * 只有活跃 session 同步到 React useState 驱动渲染，
 * 后台 session 的流回调只更新 Map，不触发重渲染。
 */

import type { ChatItem, ChatSegment } from "../../types";
import type { TaskEvent } from "@/types/task";
import type { AgentStreamState } from "@/hooks/useAgentStream";
import type {
  MultiTaskStreamState,
  WorkspaceFile,
} from "@/hooks/useMultiTaskEventStream";
import type { UploadedFile } from "@/hooks/useAgentFileUpload";

export interface SessionSlot {
  // 流状态
  streamState: AgentStreamState;
  abortController: AbortController | null;
  taskIdRef: string | undefined;
  // 聊天
  chatItems: ChatItem[];
  streamingMessageId: string | null;
  // 流式累积数据（命令式，不触发渲染）
  streamingSegments: ChatSegment[];
  outputAccumulators: Map<string, string>;
  toolCallMap: Map<string, string>;
  taskEventsMap: Record<string, TaskEvent[]>;
  flushTimer: ReturnType<typeof setTimeout> | null;
  // 多任务状态
  multiTaskState: MultiTaskStreamState;
  workspaceFiles: WorkspaceFile[];
  // 文件附件草稿（per-session 隔离）
  pendingFiles: UploadedFile[];
  }

export function createEmptySlot(): SessionSlot {
  return {
    streamState: {
      isConnected: false,
      isRunning: false,
      isComplete: false,
    },
    abortController: null,
    taskIdRef: undefined,
    chatItems: [],
    streamingMessageId: null,
    streamingSegments: [],
    outputAccumulators: new Map(),
    toolCallMap: new Map(),
    taskEventsMap: {},
    flushTimer: null,
    multiTaskState: {
      tasks: new Map(),
      taskOrder: [],
    },
    workspaceFiles: [],
    pendingFiles: [],
  };
}

/**
 * 获取或创建 session slot
 */
export function getOrCreateSlot(
  slots: Map<string, SessionSlot>,
  sessionId: string,
): SessionSlot {
  let slot = slots.get(sessionId);
  if (!slot) {
    slot = createEmptySlot();
    slots.set(sessionId, slot);
  }
  return slot;
}

/**
 * 清理 session slot 中的资源
 */
export function cleanupSlot(slot: SessionSlot): void {
  if (slot.abortController) {
    slot.abortController.abort();
    slot.abortController = null;
  }
  if (slot.flushTimer) {
    clearTimeout(slot.flushTimer);
    slot.flushTimer = null;
  }
  slot.streamingSegments = [];
  slot.outputAccumulators.clear();
  slot.toolCallMap.clear();
  slot.taskEventsMap = {};
  slot.streamingMessageId = null;
}
