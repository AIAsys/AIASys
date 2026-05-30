import type { UploadedFile } from "@/hooks/useAgentFileUpload";
import type { WorkspaceFile } from "@/types/task";
import type { ChatItem } from "../../types";
import { refreshWorkspaceFiles } from "./workspaceFiles";

interface SwitchToSessionDeps {
  /** 切换聊天 session */
  switchChatSession: (fromId: string, toId: string) => void;
  /** 切换多任务 session */
  switchMultiTaskSession: (fromId: string, toId: string) => void;
  /** 设置活跃流 session */
  setActiveStreamSession: (toId: string) => void;
  /** 设置 session ID */
  setSessionId: (sid: string) => void;
  /** 完成 Host */
  completeHost: () => void;
  /** 刷新工作区文件 */
  reloadWorkspaceFiles: (
    workspaceId?: string,
    options?: { force?: boolean },
  ) => Promise<UploadedFile[]>;
  /** 更新工作区文件 */
  updateWorkspaceFilesForSession: (
    sessionId: string,
    files: WorkspaceFile[],
  ) => void;
  /** 同步执行历史 */
  syncExecutionHistory: (taskId: string, sessionId: string) => Promise<void>;
  /** 当前任务工作区 ID */
  getWorkspaceId?: () => string | null | undefined;
}

/**
 * 非破坏性 Session 切换
 *
 * 不再调用 resetAgentStream/resetMultiTask 杀后台流。
 * 只切换视图：保存当前 session 状态到 Map，从 Map 加载目标 session。
 */
export async function switchToSession(
  fromId: string,
  toId: string,
  deps: SwitchToSessionDeps,
) {
  if (fromId === toId) return;

  const {
    switchChatSession,
    switchMultiTaskSession,
    setActiveStreamSession,
    setSessionId,
    completeHost,
    reloadWorkspaceFiles,
    updateWorkspaceFilesForSession,
    syncExecutionHistory,
    getWorkspaceId,
  } = deps;

  // 1. 切换聊天视图
  switchChatSession(fromId, toId);

  // 2. 切换多任务视图
  switchMultiTaskSession(fromId, toId);

  // 3. 切换流活跃 session（只更改哪个 session 同步到 React state）
  setActiveStreamSession(toId);

  // 4. 更新 session ID
  setSessionId(toId);

  // 5. 刷新工作区文件
  await refreshWorkspaceFiles(
    reloadWorkspaceFiles,
    updateWorkspaceFilesForSession,
    toId,
    getWorkspaceId?.(),
  );

  // 6. 同步执行历史
  await syncExecutionHistory("host", toId);

  completeHost();
}

interface RestoreSessionDeps extends SwitchToSessionDeps {
  /** 设置聊天内容（用于历史 session 加载） */
  setChatItems: (items: ChatItem[]) => void;
  /** 初始化 session */
  initChatSession: (id: string) => void;
  initMultiTaskSession: (id: string) => void;
}

/**
 * 恢复历史会话状态
 *
 * 用于加载一个历史 session（带聊天记录）。
 * 不破坏后台正在运行的流。
 */
export async function restoreSessionState(
  fromId: string,
  sid: string,
  items: ChatItem[],
  deps: RestoreSessionDeps,
) {
  const {
    setChatItems,
    initChatSession,
    initMultiTaskSession,
    switchChatSession,
    switchMultiTaskSession,
    setActiveStreamSession,
    setSessionId,
    completeHost,
    reloadWorkspaceFiles,
    updateWorkspaceFilesForSession,
    syncExecutionHistory,
    getWorkspaceId,
  } = deps;

  // 确保目标 session 已初始化
  initChatSession(sid);
  initMultiTaskSession(sid);

  // 保存当前 session 到 Map 并切换
  if (fromId && fromId !== sid) {
    switchChatSession(fromId, sid);
    switchMultiTaskSession(fromId, sid);
  }

  // 设置目标 session 的聊天内容
  setChatItems(items);

  // 切换流活跃 session
  setActiveStreamSession(sid);

  // 更新 session ID
  setSessionId(sid);

  // 刷新工作区文件和执行历史
  await refreshWorkspaceFiles(
    reloadWorkspaceFiles,
    updateWorkspaceFilesForSession,
    sid,
    getWorkspaceId?.(),
  );
  await syncExecutionHistory("host", sid);

  completeHost();
}
