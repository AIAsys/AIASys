import type { Conversation } from "../types";

const hiddenSessionIds = new Set<string>();

export function registerHiddenSession(sessionId: string | null | undefined): void {
  if (!sessionId) {
    return;
  }
  hiddenSessionIds.add(sessionId);
}

export function unregisterHiddenSession(sessionId: string | null | undefined): void {
  if (!sessionId) {
    return;
  }
  hiddenSessionIds.delete(sessionId);
}

export function isHiddenSession(sessionId: string | null | undefined): boolean {
  if (!sessionId) {
    return false;
  }
  return hiddenSessionIds.has(sessionId);
}

export function filterVisibleConversations(
  sessions: Conversation[],
): Conversation[] {
  if (sessions.length === 0) {
    return sessions;
  }
  return sessions.filter((session) => !isHiddenSession(session.session_id));
}
