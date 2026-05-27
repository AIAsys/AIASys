import type {
  ChatItem,
  ChatSegment,
  SessionHistoryContentItem,
  SessionHistoryMessage,
} from "../types";

export type HistoryMessage = SessionHistoryMessage;

function getHistoryTextContent(
  content?: SessionHistoryContentItem[] | string,
): string {
  if (typeof content === "string") {
    return content;
  }
  if (Array.isArray(content)) {
    return content.map((item) => item.text || item.think || "").join("");
  }
  return "";
}

function getHistoryAttachmentPaths(
  content?: SessionHistoryContentItem[] | string,
): string[] {
  if (!Array.isArray(content)) {
    return [];
  }

  const results: string[] = [];
  const seen = new Set<string>();
  for (const item of content) {
    if (item.type !== "image_url") {
      continue;
    }
    const candidate =
      (typeof item.source_path === "string" && item.source_path.startsWith("/workspace/")
        ? item.source_path
        : undefined) ||
      (typeof item.image_url?.url === "string" &&
      item.image_url.url.startsWith("/workspace/")
        ? item.image_url.url
        : undefined);
    if (!candidate || seen.has(candidate)) {
      continue;
    }
    seen.add(candidate);
    results.push(candidate);
  }
  return results;
}

function buildSegmentsFromSDKMessage(
  msg: HistoryMessage,
  turnN?: number,
): ChatSegment[] | undefined {
  const segments: ChatSegment[] = [];

  if (turnN !== undefined) {
    segments.push({
      type: "turn",
      content: `Turn ${turnN}`,
      turnN,
    });
  }

  const reasoningContent =
    typeof msg.reasoning_content === "string"
      ? msg.reasoning_content.trim()
      : "";
  let hasStructuredThink = false;

  if (typeof msg.content === "string") {
    if (reasoningContent) {
      segments.push({
        type: "think",
        content: reasoningContent,
        isComplete: true,
      });
      hasStructuredThink = true;
    }

    if (msg.content.trim()) {
      segments.push({
        type: "text",
        content: msg.content,
      });
    }
  } else if (Array.isArray(msg.content)) {
    for (const item of msg.content) {
      if (item.type === "think" && item.think) {
        hasStructuredThink = true;
        segments.push({
          type: "think",
          content: item.think,
          isComplete: true,
        });
      } else if (item.type === "text" && item.text) {
        segments.push({
          type: "text",
          content: item.text,
        });
      }
    }
  }

  if (reasoningContent && !hasStructuredThink) {
    segments.unshift({
      type: "think",
      content: reasoningContent,
      isComplete: true,
    });
  }

  if (msg.tool_calls && msg.tool_calls.length > 0) {
    for (const toolCall of msg.tool_calls) {
      segments.push({
        type: "tool_call",
        content: "",
        toolCallId: toolCall.id,
        toolName: toolCall.function?.name || "unknown",
        toolParams: toolCall.function?.arguments || "{}",
      });
    }
  }

  // 按类型排序：turn → think → tool_call → tool_output → text → monitor
  const SEGMENT_ORDER: Record<string, number> = {
    turn: 0,
    think: 0,
    tool_call: 1,
    tool_output: 2,
    text: 3,
    monitor: 4,
  };
  segments.sort((a, b) => {
    const orderA = SEGMENT_ORDER[a.type] ?? 99;
    const orderB = SEGMENT_ORDER[b.type] ?? 99;
    return orderA - orderB;
  });

  return segments.length > 0 ? segments : undefined;
}

function mergeAssistantMessages(messages: HistoryMessage[]): HistoryMessage[] {
  const toolNameMap = new Map<string, string>();
  const mergedMessages: HistoryMessage[] = [];

  for (const msg of messages) {
    if (msg.tool_calls) {
      msg.tool_calls.forEach((call) => {
        toolNameMap.set(call.id, call.function?.name || "unknown");
      });
    }

    if (msg.role === "assistant" && mergedMessages.length > 0) {
      const lastMsg = mergedMessages[mergedMessages.length - 1];
      if (lastMsg.role === "assistant") {
        const lastContent = Array.isArray(lastMsg.content)
          ? lastMsg.content
          : typeof lastMsg.content === "string" && lastMsg.content.trim()
            ? [{ type: "text", text: lastMsg.content }]
            : [];
        const nextContent = Array.isArray(msg.content)
          ? msg.content
          : typeof msg.content === "string" && msg.content.trim()
            ? [{ type: "text", text: msg.content }]
            : [];

        lastMsg.content = [...lastContent, ...nextContent];
        if (msg.tool_calls) {
          lastMsg.tool_calls = [...(lastMsg.tool_calls || []), ...msg.tool_calls];
        }
        continue;
      }
    }

    mergedMessages.push({ ...msg });
  }

  return mergedMessages.map((msg) => ({
    ...msg,
    tool_calls: msg.tool_calls?.map((call) => ({
      ...call,
      function: {
        ...call.function,
        name: toolNameMap.get(call.id) || call.function?.name || "unknown",
      },
    })),
  }));
}

export function restoreChatItemsFromHistory(
  sessionId: string,
  messages: HistoryMessage[],
): ChatItem[] {
  const restoredItems: ChatItem[] = [];
  const mergedMessages = mergeAssistantMessages(messages);
  const toolNameMap = new Map<string, string>();
  let turnIndex = 0;

  mergedMessages.forEach((msg, index) => {
    const timeValue = Date.now() + index;

    if (msg.tool_calls) {
      msg.tool_calls.forEach((call) => {
        toolNameMap.set(call.id, call.function?.name || "unknown");
      });
    }

    if (msg.role === "user") {
      const renderedContent = msg.display_content ?? msg.content;
      const content = getHistoryTextContent(renderedContent);
      const attachments = getHistoryAttachmentPaths(renderedContent);
      // 过滤 SDK 内部注入的 system-reminder 消息
      if (content.trim().startsWith("<system-reminder>")) {
        return;
      }
      restoredItems.push({
        type: "message",
        id: msg.id || `msg-${sessionId}-${timeValue}-${index}`,
        sender: "user",
        role: "user",
        content: content,
        attachments: attachments.length > 0 ? attachments : undefined,
        timestamp: new Date(timeValue),
        isStreaming: false,
      });
      return;
    }

    if (msg.role === "assistant") {
      turnIndex++;
      const segments = buildSegmentsFromSDKMessage(msg, turnIndex);
      const lastItem = restoredItems[restoredItems.length - 1];

      if (lastItem && lastItem.type === "message" && lastItem.sender === "ai") {
        const existingSegments = lastItem.segments || [];
        const allSegments = [...existingSegments, ...(segments || [])];
        lastItem.segments = allSegments;
        lastItem.content = allSegments
          .filter((segment) => segment.type === "text" || segment.type === "think")
          .map((segment) => segment.content)
          .join("");
        return;
      }

      restoredItems.push({
        type: "message",
        id: msg.id || `msg-${sessionId}-${timeValue}-${index}`,
        sender: "ai",
        role: "assistant",
        content:
          segments
            ?.filter((segment) => segment.type === "text" || segment.type === "think")
            .map((segment) => segment.content)
            .join("") || "",
        segments,
        timestamp: new Date(timeValue),
        isStreaming: false,
      });
      return;
    }

    if (msg.role === "system") {
      // System prompt 不显示给用户，直接跳过
      return;
    }

    const content = typeof msg.content === "string" ? msg.content : "";
    const lastItem = restoredItems[restoredItems.length - 1];
    const toolName = toolNameMap.get(msg.tool_call_id || "") || "unknown";

    if (lastItem && lastItem.type === "message" && lastItem.sender === "ai") {
      const toolOutputSeg: ChatSegment = {
        type: "tool_output",
        content,
        toolCallId: msg.tool_call_id,
        toolName,
      };
      lastItem.segments = [...(lastItem.segments || []), toolOutputSeg];
      return;
    }

    restoredItems.push({
      type: "message",
      id: msg.id || `tool-${sessionId}-${timeValue}-${index}`,
      sender: "tool",
      role: "tool",
      content,
      timestamp: new Date(timeValue),
      isStreaming: false,
    });
  });

  return restoredItems;
}
