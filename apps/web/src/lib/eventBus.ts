/**
 * Simple Event Bus for cross-component communication
 * Used to notify execution tree refresh when Sub Agent events arrive
 */

type EventCallback = (data?: unknown) => void;

class EventBus {
  private events: Map<string, EventCallback[]> = new Map();

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

  emit(event: string, data?: unknown): void {
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
