import type { Conversation } from "../types";

export function sessionsEqual(
  previousSessions: Conversation[],
  nextSessions: Conversation[],
): boolean {
  if (previousSessions.length !== nextSessions.length) {
    return false;
  }

  return previousSessions.every(
    (session, index) =>
      session.session_id === nextSessions[index].session_id &&
      session.title === nextSessions[index].title &&
      session.updated_at === nextSessions[index].updated_at,
  );
}
