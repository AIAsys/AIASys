import type { AgentEvent, ExecutionEvent } from "@/types/api";
import type { TaskEvent } from "@/types/task";
import { shouldTrackExecutionFlowTool } from "@/lib/runtimeToolEvents";

export function convertAgentEventToTaskEvent(event: AgentEvent): TaskEvent | null {
  // 处理 subagent_event - 从 payload 中提取实际事件
  if (event.type === "subagent_event") {
    const payload = event.payload;
    if (!payload) return null;
    
    // 根据 payload 中的 type 进一步处理
    switch (payload.type) {
      case "subagent_tool_call": {
        if (!shouldTrackExecutionFlowTool(payload.tool_name)) return null;
        const args = payload.arguments || {};
        const code = args.code || "";
        return {
          event: "tool_start",
          tool_name: payload.tool_name || "unknown",
          tool_params: code || args,
          agent_name: "专家",
          source_agent: "专家",
          task_tool_call_id: event.task_tool_call_id,
        } as unknown as TaskEvent;
      }
      case "subagent_tool_result": {
        if (!shouldTrackExecutionFlowTool(payload.tool_name)) return null;
        return {
          event: "tool_output",
          tool_name: payload.tool_name || "unknown",
          content: payload.content || "",
          is_error: payload.is_error || false,
          agent_name: "专家",
          source_agent: "专家",
          task_tool_call_id: event.task_tool_call_id,
        } as TaskEvent;
      }
      case "subagent_content":
      case "subagent_step_begin":
      default:
        return null;
    }
  }

  switch (event.type) {
    case "subagent_content":
      return null;
    case "subagent_tool_call": {
      if (!shouldTrackExecutionFlowTool(event.tool_name)) return null;
      const args = event.arguments || {};
      const code = args.code || "";
      return {
        event: "tool_start",
        tool_name: event.tool_name || "unknown",
        tool_params: code || args,
        agent_name: "专家",
        source_agent: "专家",
      } as TaskEvent;
    }
    case "subagent_tool_result":
      if (!shouldTrackExecutionFlowTool(event.tool_name)) return null;
      return {
        event: "tool_output",
        tool_name: event.tool_name || "unknown",
        content: event.content || "",
        is_error: event.is_error || false,
        agent_name: "专家",
        source_agent: "专家",
      } as TaskEvent;
    case "subagent_step_begin":
      return null;
  }

  switch (event.type) {
    case "content":
      return null;
    case "tool_call": {
      if (!shouldTrackExecutionFlowTool(event.tool_name)) return null;
      const toolArgs = event.arguments || {};
      const toolCode = toolArgs.code || "";
      return {
        event: "tool_start",
        tool_name: event.tool_name,
        tool_params: toolCode || toolArgs,
      } as TaskEvent;
    }
    case "tool_result":
      if (!shouldTrackExecutionFlowTool(event.tool_name)) return null;
      return {
        event: "tool_output",
        tool_name: event.tool_name,
        content: event.content,
      } as TaskEvent;
    case "status":
      return null;
    default:
      return null;
  }
}

export function mapExecutionEventsToTaskEvents(
  taskId: string,
  events: ExecutionEvent[],
): TaskEvent[] {
  return events
    .filter((e) => e.agent === "subagent" && e.task_tool_call_id === taskId)
    .filter((e) => shouldTrackExecutionFlowTool(e.tool_name))
    .map((e) => {
      switch (e.event_type) {
        case "tool_call":
          return {
            event: "tool_start",
            tool_name: e.tool_name || "unknown",
            tool_params: e.tool_arguments || {},
            agent_name: e.subagent_name || "专家",
            source_agent: e.subagent_name || "专家",
          } as TaskEvent;
        case "tool_result":
          return {
            event: "tool_output",
            tool_name: e.tool_name || "unknown",
            content: e.tool_output || "",
            status: e.tool_success ? "success" : "error",
            agent_name: e.subagent_name || "专家",
            source_agent: e.subagent_name || "专家",
          } as TaskEvent;
        default:
          return null;
      }
    })
    .filter((e): e is TaskEvent => e !== null);
}
