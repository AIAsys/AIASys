export interface DatabaseConnectorSyncEvent {
  scope: "connectors" | "attachments";
  sessionId?: string | null;
  timestamp: number;
}

const CHANNEL_NAME = "aiasys-database-connectors";
const WINDOW_EVENT_NAME = "aiasys:database-connectors-sync";

let sharedChannel: BroadcastChannel | null | undefined;

function getBroadcastChannel(): BroadcastChannel | null {
  if (typeof window === "undefined" || typeof BroadcastChannel === "undefined") {
    return null;
  }

  if (sharedChannel !== undefined) {
    return sharedChannel;
  }

  sharedChannel = new BroadcastChannel(CHANNEL_NAME);
  return sharedChannel;
}

export function emitDatabaseConnectorSync(
  event: Omit<DatabaseConnectorSyncEvent, "timestamp">,
): void {
  if (typeof window === "undefined") {
    return;
  }

  const payload: DatabaseConnectorSyncEvent = {
    ...event,
    timestamp: Date.now(),
  };

  window.dispatchEvent(
    new CustomEvent<DatabaseConnectorSyncEvent>(WINDOW_EVENT_NAME, {
      detail: payload,
    }),
  );
  getBroadcastChannel()?.postMessage(payload);
}

export function subscribeDatabaseConnectorSync(
  listener: (event: DatabaseConnectorSyncEvent) => void,
): () => void {
  if (typeof window === "undefined") {
    return () => undefined;
  }

  const handleWindowEvent = (event: Event) => {
    const customEvent = event as CustomEvent<DatabaseConnectorSyncEvent>;
    if (customEvent.detail) {
      listener(customEvent.detail);
    }
  };

  window.addEventListener(WINDOW_EVENT_NAME, handleWindowEvent);

  const channel = getBroadcastChannel();
  const handleChannelMessage = (event: MessageEvent<unknown>) => {
    const data = event.data;
    if (
      data &&
      typeof data === "object" &&
      (data as Record<string, unknown>).scope &&
      ["connectors", "attachments"].includes(
        (data as Record<string, unknown>).scope as string,
      )
    ) {
      listener(data as DatabaseConnectorSyncEvent);
    }
  };
  channel?.addEventListener("message", handleChannelMessage);

  return () => {
    window.removeEventListener(WINDOW_EVENT_NAME, handleWindowEvent);
    channel?.removeEventListener("message", handleChannelMessage);
  };
}
