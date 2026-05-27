export const DEFAULT_CONVERSATION_TITLE = "新对话";
export const DEFAULT_BRANCH_TITLE = "新会话";

export function getDefaultConversationTitle(
  branchedFromConversationId?: string | null,
): string {
  return branchedFromConversationId
    ? DEFAULT_BRANCH_TITLE
    : DEFAULT_CONVERSATION_TITLE;
}
