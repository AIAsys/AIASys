import { useCallback, useState } from "react";
import type { ChatItem } from "../types";
import {
  extractToolOutput,
  parseToolParams,
  type ToolPreviewData,
} from "@/lib/toolPreview";

interface UseToolPreviewReturn {
  toolPreviewOpen: boolean;
  toolPreviewData: ToolPreviewData | null;
  handleViewToolDetails: (
    toolCallId: string,
    taskId: string | undefined,
    triggerRect: DOMRect,
  ) => void;
  closeToolPreview: () => void;
}

export function useToolPreview(chatItems: ChatItem[]): UseToolPreviewReturn {
  const [toolPreviewOpen, setToolPreviewOpen] = useState(false);
  const [toolPreviewData, setToolPreviewData] = useState<ToolPreviewData | null>(
    null,
  );

  const handleViewToolDetails = useCallback(
    (toolCallId: string, taskId: string | undefined, triggerRect: DOMRect) => {
      let toolName: string | undefined;
      let toolParams: Record<string, unknown> | undefined;
      let toolOutput: string | undefined;

      for (const item of chatItems) {
        if (item.type !== "message" || item.sender !== "ai" || !item.segments) {
          continue;
        }

        const toolCallSegment = item.segments.find(
          (segment) =>
            segment.type === "tool_call" &&
            (segment.toolCallId === toolCallId || segment.toolName === toolCallId),
        );
        if (toolCallSegment) {
          toolName = toolCallSegment.toolName;
          if (toolCallSegment.toolParams) {
            toolParams = parseToolParams(toolCallSegment.toolParams) ?? toolParams;
          }
        }

        const toolOutputSegment = item.segments.find(
          (segment) =>
            segment.type === "tool_output" &&
            (segment.toolCallId === toolCallId || segment.toolName === toolCallId),
        );
        if (toolOutputSegment) {
          toolOutput =
            extractToolOutput({ content: toolOutputSegment.content }) || toolOutput;
        }
      }

      setToolPreviewData({
        toolName: toolName || toolCallId,
        toolParams,
        toolOutput,
        taskId,
        triggerRect,
      });
      setToolPreviewOpen(true);
    },
    [chatItems],
  );

  const closeToolPreview = useCallback(() => {
    setToolPreviewOpen(false);
  }, []);

  return {
    toolPreviewOpen,
    toolPreviewData,
    handleViewToolDetails,
    closeToolPreview,
  };
}
