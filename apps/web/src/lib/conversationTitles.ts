// 产品文案统一使用“会话”口径（见 aiasys-runtime-semantics），默认标题只有一个
export const DEFAULT_CONVERSATION_TITLE = "新会话";

export function getDefaultConversationTitle(): string {
  return DEFAULT_CONVERSATION_TITLE;
}
