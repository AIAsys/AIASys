import {
  createWorkspaceConversation,
  type CreateConversationPayload,
} from "@/lib/api/workspaces";

interface CreateAndActivateWorkspaceConversationOptions {
  workspaceId: string;
  title?: string;
  branchedFromConversationId?: string;
  loadWorkspaces: () => Promise<unknown>;
  activatePreparedSession: (
    sessionId: string,
  ) => Promise<string>;
}

export async function createAndActivateWorkspaceConversation({
  workspaceId: _workspaceId,
  title,
  branchedFromConversationId,
  loadWorkspaces,
  activatePreparedSession,
}: CreateAndActivateWorkspaceConversationOptions): Promise<void> {
  const payload: CreateConversationPayload = {
    title,
    branchedFromConversationId,
  };

  const createdConversation = await createWorkspaceConversation(_workspaceId, payload);
  await loadWorkspaces();
  // activatePreparedSession 内部已通过当前 URL 的 workspace_id 处理路由同步，
  // 这里不再重复调用 navigateToAnalysisSession，避免双重导航导致页面刷新。
  await activatePreparedSession(createdConversation.session_id);
}
