/**
 * Simple Event Bus for cross-component communication
 * Used to notify execution tree refresh when Sub Agent events arrive
 */

type EventCallback = (data?: unknown) => void;

const DEDUP_WINDOW_MS = 500;

class EventBus {
  private events: Map<string, EventCallback[]> = new Map();
  // 最近 N 毫秒内已发出的事件 key，用于 SSE 重连后去重
  private recentKeys: Map<string, number> = new Map();

  on(event: string, callback: EventCallback): () => void {
    if (!this.events.has(event)) {
      this.events.set(event, []);
    }
    this.events.get(event)!.push(callback);

    // Return unsubscribe function
    return () => {
      const callbacks = this.events.get(event);
      if (callbacks) {
        const index = callbacks.indexOf(callback);
        if (index > -1) {
          callbacks.splice(index, 1);
        }
      }
    };
  }

  private _makeDedupKey(event: string, data: unknown): string | null {
    if (data === undefined || data === null) {
      return null;
    }
    if (typeof data === "object" && data !== null) {
      const record = data as Record<string, unknown>;
      const id =
        record.event_id ?? record.id ?? record.request_id ?? record.task_id;
      if (typeof id === "string" || typeof id === "number") {
        return `${event}::id::${id}`;
      }
    }
    try {
      return `${event}::hash::${JSON.stringify(data)}`;
    } catch {
      return null;
    }
  }

  emit(event: string, data?: unknown): void {
    const key = this._makeDedupKey(event, data);
    const now = Date.now();
    if (key !== null) {
      const lastSeen = this.recentKeys.get(key);
      if (lastSeen !== undefined && now - lastSeen <= DEDUP_WINDOW_MS) {
        // 500ms 内重复事件，丢弃
        return;
      }
      this.recentKeys.set(key, now);
    }

    // 清理过期 key，避免 Map 无限增长
    for (const [k, ts] of this.recentKeys.entries()) {
      if (now - ts > DEDUP_WINDOW_MS) {
        this.recentKeys.delete(k);
      }
    }

    const callbacks = this.events.get(event);
    if (callbacks) {
      callbacks.forEach((callback) => {
        try {
          callback(data);
        } catch (error) {
          console.error(`[EventBus] Error in callback for "${event}":`, error);
        }
      });
    }
  }

  off(event: string, callback: EventCallback): void {
    const callbacks = this.events.get(event);
    if (callbacks) {
      const index = callbacks.indexOf(callback);
      if (index > -1) {
        callbacks.splice(index, 1);
      }
    }
  }
}

// Global event bus instance
export const eventBus = new EventBus();

// Event names
export const EVENTS = {
  SUBAGENT_EVENT: "subagent:event",
  SUBAGENT_CREATED: "subagent:created",
  SUBAGENT_STATUS_CHANGED: "subagent:status_changed",
  CODE_EXECUTION_EVENT: "code:execution",
  EXECUTION_ACTIVITY: "execution:activity",
} as const;
