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

function _hasSubstantiveContent(msg: HistoryMessage): boolean {
  const content = msg.content;
  const hasText =
    (typeof content === "string" && content.trim().length > 0) ||
    (Array.isArray(content) &&
      content.some(
        (item) =>
          (item.type === "text" && (item.text || "").trim().length > 0) ||
          (item.type === "think" && (item.think || "").trim().length > 0),
      ));
  const hasReasoning =
    typeof msg.reasoning_content === "string" &&
    msg.reasoning_content.trim().length > 0;
  const hasToolCalls = (msg.tool_calls?.length || 0) > 0;
  return hasText || hasReasoning || hasToolCalls;
}

function buildSegmentsFromSDKMessage(
  msg: HistoryMessage,
  turnN?: number,
): ChatSegment[] | undefined {
  const segments: ChatSegment[] = [];

  // 只有 assistant 消息有实质内容时才生成 turn 分隔线
  if (turnN !== undefined && _hasSubstantiveContent(msg)) {
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
    // 将 reasoning_content 的 think 段插入到 turn 标记之后，保持 turn 在首位的视觉顺序
    const turnIndex = segments.findIndex((seg) => seg.type === "turn");
    const insertIndex = turnIndex >= 0 ? turnIndex + 1 : 0;
    segments.splice(insertIndex, 0, {
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
      // 只有同 turn 的 assistant 消息才合并，避免破坏 turn 边界
      // 没有 turn_n 的旧数据无法判断同 turn，保守不合并
      if (
        lastMsg.role === "assistant" &&
        typeof lastMsg.turn_n === "number" &&
        typeof msg.turn_n === "number" &&
        lastMsg.turn_n === msg.turn_n
      ) {
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
        // 合并 reasoning_content，避免思考内容丢失
        const nextReasoning =
          typeof msg.reasoning_content === "string" ? msg.reasoning_content.trim() : "";
        if (nextReasoning) {
          const existingReasoning =
            typeof lastMsg.reasoning_content === "string"
              ? lastMsg.reasoning_content.trim()
              : "";
          lastMsg.reasoning_content = existingReasoning
            ? `${existingReasoning}\n${nextReasoning}`
            : nextReasoning;
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
  let legacyTurnIndex = 0;

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

      // 压缩摘要消息使用特殊 UI 展示，不作为普通用户消息。
      if (msg.origin === "compaction_summary") {
        restoredItems.push({
          type: "message",
          id: msg.id || `compaction-${sessionId}-${timeValue}-${index}`,
          sender: "system",
          role: "system",
          content: content,
          segments: [{ type: "compaction_summary", content }],
          timestamp: new Date(timeValue),
          isStreaming: false,
        });
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
      const hasContent = _hasSubstantiveContent(msg);
      // 优先使用后端返回的 turn_n，无则退化为旧的自增逻辑（兼容旧会话）
      let turnN: number | undefined;
      if (hasContent) {
        if (typeof msg.turn_n === "number") {
          turnN = msg.turn_n;
        } else {
          legacyTurnIndex++;
          turnN = legacyTurnIndex;
        }
      }
      const segments = buildSegmentsFromSDKMessage(msg, turnN);
      const lastItem = restoredItems[restoredItems.length - 1];

      if (lastItem && lastItem.type === "message" && lastItem.sender === "ai") {
        const existingSegments = lastItem.segments || [];
        const allSegments = [...existingSegments, ...(segments || [])];
        // 不可变更新：替换数组中的对象而非直接修改
        const lastIdx = restoredItems.length - 1;
        restoredItems[lastIdx] = {
          ...lastItem,
          segments: allSegments,
          content: allSegments
            .filter((segment) => segment.type === "text" || segment.type === "think")
            .map((segment) => segment.content)
            .join(""),
        };
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

    const content = getHistoryTextContent(msg.content);
    const lastItem = restoredItems[restoredItems.length - 1];
    const toolName = toolNameMap.get(msg.tool_call_id || "") || "unknown";

    if (lastItem && lastItem.type === "message" && lastItem.sender === "ai") {
      const toolOutputSeg: ChatSegment = {
        type: "tool_output",
        content,
        toolCallId: msg.tool_call_id,
        toolName,
      };
      // 不可变更新：替换数组中的对象而非直接修改
      const lastIdx = restoredItems.length - 1;
      restoredItems[lastIdx] = {
        ...lastItem,
        segments: [...(lastItem.segments || []), toolOutputSeg],
      };
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
