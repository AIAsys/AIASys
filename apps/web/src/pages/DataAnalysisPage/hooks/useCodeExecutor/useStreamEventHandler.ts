import { useCallback, useEffect, useRef } from "react";
import type { ChatItem, ChatSegment } from "../../types";
import type { TaskEvent } from "@/types/task";
import type { AskUserRequest } from "@/types/askUser";
import type { AgentEvent, MonitorOutputEvent } from "@/types/api";
import type { SessionSlot } from "./sessionRegistry";
import { eventBus, EVENTS } from "@/lib/eventBus";
import { shouldTrackExecutionFlowTool } from "@/lib/runtimeToolEvents";

interface AskUserRequestEvent {
  type: "ask_user_request";
  request: AskUserRequest;
}

type StreamEvent = AgentEvent | AskUserRequestEvent;

interface UseStreamEventHandlerProps {
  /** 查找指定 session 的 slot */
  getSessionSlot: (sessionId: string) => SessionSlot;
  /** 更新指定 session 的 chatItems */
  updateChatItems: (
    sessionId: string,
    updater: (prev: ChatItem[]) => ChatItem[],
  ) => void;
  /** 添加事件到指定 session 的 Task */
  addStreamEventsForSession: (
    sessionId: string,
    taskId: string,
    events: TaskEvent[],
    sourceAgent: string,
  ) => void;
  /** 当前活跃 session ID（用于判断 agentState.isRunning） */
  isSessionRunning: (sessionId: string) => boolean;
  onAskUserRequest?: (request: AskUserRequest, sessionId: string) => void;
  /** 当收到 Sub Agent 事件时调用（用于刷新执行树） */
  onSubAgentEvent?: (event: unknown) => void;
}

export function useStreamEventHandler({
  getSessionSlot,
  updateChatItems,
  addStreamEventsForSession,
  isSessionRunning,
  onAskUserRequest,
  onSubAgentEvent,
}: UseStreamEventHandlerProps) {
  // 用 ref 持有频繁变化的外部回调，避免 handleStreamEvent 每帧重建
  const onAskUserRequestRef = useRef(onAskUserRequest);
  onAskUserRequestRef.current = onAskUserRequest;
  const onSubAgentEventRef = useRef(onSubAgentEvent);
  onSubAgentEventRef.current = onSubAgentEvent;
  const isSessionRunningRef = useRef(isSessionRunning);
  isSessionRunningRef.current = isSessionRunning;

  // 流式过程中不排序，保持后端到达的原始时序
  // 历史恢复时排序由 AiMessageContent 和 sessionManagementHistory 各自处理

  // Synchronize segments back to React state array for a specific session
  // 流式过程中保持到达时序，不做全局排序
  const syncSegmentsToUI = useCallback((sessionId: string) => {
    const slot = getSessionSlot(sessionId);
    const currentSegments = slot.streamingSegments.map((s) => ({ ...s }));
    const content = currentSegments
      .filter((s) => s.type === "text" || s.type === "think")
      .map((s) => s.content)
      .join("");

    const streamingMsgId = slot.streamingMessageId;

    updateChatItems(sessionId, (prev: ChatItem[]) => {
      // 使用 streamingMessageId 精确匹配，消除靠 isStreaming 模糊匹配的风险
      const aiMsgIdx = streamingMsgId
        ? prev.findIndex((item) => item.id === streamingMsgId)
        : prev.findIndex(
            (item) => item.type === "message" && item.sender === "ai" && item.isStreaming,
          );
      if (aiMsgIdx === -1) {
        if (!streamingMsgId) {
          console.warn("[syncSegmentsToUI] No streaming AI message found");
          return prev;
        }
        return [
          ...prev,
          {
            type: "message" as const,
            id: streamingMsgId,
            sender: "ai" as const,
            role: "assistant" as const,
            content,
            segments: currentSegments,
            timestamp: new Date(),
            isStreaming: true,
          },
        ];
      }
      const newItems = [...prev];
      const target = newItems[aiMsgIdx];
      if (target.type === "message") {
        newItems[aiMsgIdx] = { ...target, segments: currentSegments, content };
      }
      return newItems;
    });
  }, [getSessionSlot, updateChatItems]);

  // Debounced flush for a specific session
  const scheduleFlush = useCallback((sessionId: string) => {
    const slot = getSessionSlot(sessionId);
    if (slot.flushTimer) return;
    slot.flushTimer = setTimeout(() => {
      slot.flushTimer = null;
      syncSegmentsToUI(sessionId);
    }, 50);
  }, [getSessionSlot, syncSegmentsToUI]);

  // 当新的非 think segment 到达时，将前面未完成的 think segment 标记为已完成
  // 使其 spinner 立即停止，而非等到整个消息结束
  const closePendingThink = (segments: ChatSegment[]) => {
    const lastSeg = segments[segments.length - 1];
    if (lastSeg && lastSeg.type === "think" && !lastSeg.isComplete) {
      segments[segments.length - 1] = { ...lastSeg, isComplete: true };
    }
  };

  const handleStreamEvent = useCallback((sessionId: string, event: StreamEvent) => {
    const eventType = event.type;
    const slot = getSessionSlot(sessionId);
    const segments = slot.streamingSegments;
    const streamingMsgId = slot.streamingMessageId;

    // Type: Turn Begin — 添加 turn 标记 segment
    if (eventType === "turn_begin" && "turn_n" in event) {
      closePendingThink(segments);
      segments.push({
        type: "turn",
        content: `Turn ${event.turn_n}`,
        turnN: event.turn_n,
      });
      scheduleFlush(sessionId);
    }

    // Type: Content (Text or Think)
    if (eventType === "content" && "content_type" in event) {
      if (event.content_type === "text" && event.text) {
        const lastSeg = segments[segments.length - 1];
        closePendingThink(segments);
        if (lastSeg && lastSeg.type === "text" && !lastSeg.isComplete) {
          segments[segments.length - 1] = {
            ...lastSeg,
            content: lastSeg.content + event.text,
          };
        } else {
          segments.push({ type: "text", content: event.text });
        }
        scheduleFlush(sessionId);
      } else if (event.content_type === "think" && event.think) {
        const lastSeg = segments[segments.length - 1];
        const isStreaming = isSessionRunningRef.current(sessionId);
        if (
          lastSeg &&
          lastSeg.type === "think" &&
          !lastSeg.isComplete &&
          isStreaming
        ) {
          segments[segments.length - 1] = {
            ...lastSeg,
            content: lastSeg.content + event.think,
          };
        } else {
          segments.push({
            type: "think",
            content: event.think,
            isComplete: false,
          });
        }
        scheduleFlush(sessionId);
      }
    }

    // Type: Tool Call Start
    if (eventType === "tool_call" && "tool_name" in event) {
      closePendingThink(segments);
      segments.push({
        type: "tool_call",
        content: "",
        toolName: event.tool_name,
        toolCallId: event.tool_call_id,
        toolParams: JSON.stringify(event.arguments || {}),
      });
      scheduleFlush(sessionId);

      if (event.tool_call_id) {
        slot.toolCallMap.set(event.tool_call_id, event.tool_name);
      }

      const hostTaskId = "host";
      updateChatItems(sessionId, (prev: ChatItem[]) => {
        const aiMsgIdx = streamingMsgId
          ? prev.findIndex((item) => item.id === streamingMsgId)
          : prev.findIndex(
              (item) => item.type === "message" && item.sender === "ai" && item.isStreaming,
            );
        if (aiMsgIdx === -1) return prev;
        const newItems = [...prev];
        const target = newItems[aiMsgIdx];
        if (target.type === "message" && !target.taskId) {
          newItems[aiMsgIdx] = { ...target, taskId: hostTaskId };
        }
        return newItems;
      });

      if (shouldTrackExecutionFlowTool(event.tool_name)) {
        eventBus.emit(EVENTS.EXECUTION_ACTIVITY, {
          session_id: sessionId,
          type: eventType,
          tool_name: event.tool_name,
          tool_call_id: event.tool_call_id,
        });

        const toolCallEvent: TaskEvent = {
          event: "tool_start",
          agent_name: "Host",
          agent_role: "host",
          source_agent: "Host",
          tool_name: event.tool_name,
          tool_params: event.arguments || {},
          timestamp: new Date().toISOString(),
        };

        if (!slot.taskEventsMap[hostTaskId])
          slot.taskEventsMap[hostTaskId] = [];
        slot.taskEventsMap[hostTaskId].push(toolCallEvent);
        addStreamEventsForSession(sessionId, hostTaskId, [toolCallEvent], "当前会话");
        
        // 发送代码执行事件到执行记录
        eventBus.emit(EVENTS.CODE_EXECUTION_EVENT, {
          type: "tool_call",
          session_id: sessionId,
          tool_call_id: event.tool_call_id,
          tool_name: event.tool_name,
          arguments: event.arguments,
        });
      }
    }

    // Type: Tool Result
    if (eventType === "tool_result" && "tool_call_id" in event) {
      closePendingThink(segments);
      const isError = event.is_error === true;
      const outputContent = event.content || "";
      const toolName = slot.toolCallMap.get(event.tool_call_id) || event.tool_name || "未知工具";

      segments.push({
        type: "tool_output",
        content: outputContent,
        toolName: toolName,
        toolCallId: event.tool_call_id,
        isError: isError,
      });
      syncSegmentsToUI(sessionId);

      if (shouldTrackExecutionFlowTool(toolName)) {
        eventBus.emit(EVENTS.EXECUTION_ACTIVITY, {
          session_id: sessionId,
          type: eventType,
          tool_name: toolName,
          tool_call_id: event.tool_call_id,
          is_error: isError,
        });

        const hostTaskId = "host";
        const toolResultEvent: TaskEvent = {
          event: "tool_output",
          agent_name: "Host",
          agent_role: "host",
          source_agent: "Host",
          tool_name: toolName,
          content: outputContent,
          is_error: isError,
          timestamp: new Date().toISOString(),
        };

        if (!slot.taskEventsMap[hostTaskId])
          slot.taskEventsMap[hostTaskId] = [];
        slot.taskEventsMap[hostTaskId].push(toolResultEvent);
        addStreamEventsForSession(sessionId, hostTaskId, [toolResultEvent], "当前会话");
        
        // 发送代码执行结果事件到执行记录
        eventBus.emit(EVENTS.CODE_EXECUTION_EVENT, {
          type: "tool_result",
          session_id: sessionId,
          tool_call_id: event.tool_call_id,
          tool_name: toolName,
          content: outputContent,
          is_error: isError,
        });
      }
    }

    // Type: SubAgent Tasks Events
    // 处理新的 subagent_event 格式（包含 payload）
    if (eventType === "subagent_event") {
      // 通知外部有 Sub Agent 事件（用于刷新执行树）
      onSubAgentEventRef.current?.(event);
      
      // 通过事件总线通知执行树刷新
      eventBus.emit(EVENTS.SUBAGENT_EVENT, event);
      
      const payload = event.payload;
      const taskId = event.task_tool_call_id;
      const subagentName = event.subagent_name || "专家";

      if (!payload || !taskId) {
        return;
      }

      updateChatItems(sessionId, (prev: ChatItem[]) => {
        const aiMsgIdx = streamingMsgId
          ? prev.findIndex((item) => item.id === streamingMsgId)
          : prev.findIndex(
              (item) => item.type === "message" && item.sender === "ai" && item.isStreaming,
            );
        if (aiMsgIdx === -1) return prev;
        const newItems = [...prev];
        const target = newItems[aiMsgIdx];
        if (target.type === "message" && !target.taskId) {
          newItems[aiMsgIdx] = { ...target, taskId };
        }
        return newItems;
      });

      // 根据 payload 类型处理
      if (payload.type === "subagent_tool_call") {
        if (!shouldTrackExecutionFlowTool(payload.tool_name)) {
          return;
        }
        const taskEvent: TaskEvent = {
          event: "tool_start",
          agent_name: subagentName,
          agent_role: "worker",
          source_agent: subagentName,
          tool_name: payload.tool_name,
          tool_params: payload.arguments,
          timestamp: new Date().toISOString(),
        };
        if (!slot.taskEventsMap[taskId])
          slot.taskEventsMap[taskId] = [];
        slot.taskEventsMap[taskId].push(taskEvent);
        addStreamEventsForSession(sessionId, taskId, [taskEvent], subagentName);
        
        // 发送代码执行事件到执行记录
        eventBus.emit(EVENTS.CODE_EXECUTION_EVENT, {
          type: "subagent_event",
          session_id: sessionId,
          payload: {
            type: "subagent_tool_call",
            tool_call_id: payload.tool_call_id,
            tool_name: payload.tool_name,
            arguments: payload.arguments,
          },
        });
      } else if (payload.type === "subagent_tool_result") {
        if (!shouldTrackExecutionFlowTool(payload.tool_name)) {
          return;
        }
        const taskEvent: TaskEvent = {
          event: "tool_output",
          agent_name: subagentName,
          agent_role: "worker",
          source_agent: subagentName,
          tool_name: payload.tool_name,
          content: payload.content,
          is_error: payload.is_error,
          timestamp: new Date().toISOString(),
        };
        if (!slot.taskEventsMap[taskId])
          slot.taskEventsMap[taskId] = [];
        slot.taskEventsMap[taskId].push(taskEvent);
        addStreamEventsForSession(sessionId, taskId, [taskEvent], subagentName);
        
        // 发送代码执行结果事件到执行记录
        eventBus.emit(EVENTS.CODE_EXECUTION_EVENT, {
          type: "subagent_event",
          session_id: sessionId,
          payload: {
            type: "subagent_tool_result",
            tool_call_id: payload.tool_call_id,
            tool_name: payload.tool_name,
            content: payload.content,
            is_error: payload.is_error,
          },
        });
      }
      return;
    }

    // 处理后端直接发出的 subagent 事件分支
    const isSubagentEvent =
      eventType === "subagent_content" ||
      eventType === "subagent_tool_call" ||
      eventType === "subagent_tool_result" ||
      eventType === "subagent_step_begin";
    if (isSubagentEvent) {
      const taskId = event.task_tool_call_id;
      const subagentName = "专家";

      if (!taskId) return;

      updateChatItems(sessionId, (prev: ChatItem[]) => {
        const aiMsgIdx = streamingMsgId
          ? prev.findIndex((item) => item.id === streamingMsgId)
          : prev.findIndex(
              (item) => item.type === "message" && item.sender === "ai" && item.isStreaming,
            );
        if (aiMsgIdx === -1) return prev;
        const newItems = [...prev];
        const target = newItems[aiMsgIdx];
        if (target.type === "message" && !target.taskId) {
          newItems[aiMsgIdx] = { ...target, taskId };
        }
        return newItems;
      });

      if (eventType === "subagent_tool_call") {
        if (!shouldTrackExecutionFlowTool(event.tool_name)) {
          return;
        }
        const taskEvent: TaskEvent = {
          event: "tool_start",
          agent_name: subagentName,
          agent_role: "worker",
          source_agent: subagentName,
          tool_name: event.tool_name,
          tool_params: event.arguments,
          timestamp: new Date().toISOString(),
        };
        if (!slot.taskEventsMap[taskId])
          slot.taskEventsMap[taskId] = [];
        slot.taskEventsMap[taskId].push(taskEvent);
        addStreamEventsForSession(sessionId, taskId, [taskEvent], subagentName);
      } else if (eventType === "subagent_tool_result") {
        if (!shouldTrackExecutionFlowTool(event.tool_name)) {
          return;
        }
        const taskEvent: TaskEvent = {
          event: "tool_output",
          agent_name: subagentName,
          agent_role: "worker",
          source_agent: subagentName,
          tool_name: event.tool_name,
          content: event.content,
          is_error: event.is_error,
          timestamp: new Date().toISOString(),
        };
        if (!slot.taskEventsMap[taskId])
          slot.taskEventsMap[taskId] = [];
        slot.taskEventsMap[taskId].push(taskEvent);
        addStreamEventsForSession(sessionId, taskId, [taskEvent], subagentName);
      }
    }

    // Type: Monitor Output
    if (eventType === "monitor.output") {
      const monEvent = event as MonitorOutputEvent;
      const monitorId = monEvent.monitor_id;
      const output = monEvent.output;
      const status = monEvent.status;
      const command = monEvent.command;
      const exitCode = monEvent.exit_code;

      // 查找是否已有该 monitor 的 segment
      const existingIdx = segments.findIndex(
        (s) => s.type === "monitor" && s.monitorId === monitorId,
      );

      if (existingIdx >= 0) {
        // 追加输出到现有 segment
        const existing = segments[existingIdx];
        segments[existingIdx] = {
          ...existing,
          content: existing.content + output,
          monitorStatus: status,
          monitorExitCode: exitCode,
          isComplete: status === "completed" || status === "error" || status === "killed",
          isError: status === "error" || status === "killed" || (exitCode !== null && exitCode !== 0),
        };
      } else {
        // 创建新 monitor segment
        segments.push({
          type: "monitor",
          content: output,
          monitorId,
          monitorCommand: command,
          monitorStatus: status,
          monitorExitCode: exitCode,
          isComplete: status === "completed" || status === "error" || status === "killed",
          isError: status === "error" || status === "killed" || (exitCode !== null && exitCode !== 0),
        });
      }
      syncSegmentsToUI(sessionId);
    }

    // Type: Ask User Request
    if (eventType === "ask_user_request" && "request" in event) {
      onAskUserRequestRef.current?.(event.request, sessionId);
    }

    // Type: Budget Limited
    if (eventType === "budget_limited" && "text" in event) {
      updateChatItems(sessionId, (prev: ChatItem[]) => [
        ...prev,
        {
          type: "message" as const,
          id: `budget-limit-${Date.now()}`,
          sender: "system" as const,
          role: "system" as const,
          content: event.text || "当前会话预算已耗尽，本轮不会继续执行。",
          timestamp: new Date(),
        },
      ]);
    }
  }, [getSessionSlot, updateChatItems, addStreamEventsForSession, scheduleFlush, syncSegmentsToUI]);

  // Cleanup effect — clean up any flush timers
  useEffect(() => {
    return () => {
      // Note: specific session cleanup is handled by the caller
    };
  }, []);

  return { handleStreamEvent, syncSegmentsToUI };
}
