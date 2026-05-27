"""
事件处理 Mixin

负责底层 runtime wire 事件的转换和处理
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any, Optional

from app.models.worker_lifecycle import (
    build_worker_lifecycle_event,
    project_host_lifecycle_from_wire,
    project_subagent_lifecycle_from_task_result,
    project_subagent_lifecycle_from_wire,
)
from app.services.agent.runtime_backends import (
    AgentRuntimeEvent,
)
from app.services.runtime_tooling import (
    extract_subagent_display_name,
    is_subagent_dispatch_tool_name,
    project_runtime_tool_event_name,
)

if TYPE_CHECKING:
    from app.services.agent import AgentService


class EventMixin:
    """事件处理功能"""

    def _new_event_projection_state(self: "AgentService") -> dict[str, Any]:
        return {
            "tool_call_map": {},
            "task_call_map": {},
            "current_task_call": None,
            "pending_tool_call": None,
            "turn_started": False,
            "turn_n": 0,
            "current_host_step": 0,
            "pending_host_step": False,
        }

    def _build_worker_lifecycle_event(
        self: "AgentService",
        *,
        scope: str,
        status: str,
        reason: str,
        task_tool_call_id: str | None = None,
        parent_tool_call_id: str | None = None,
        agent_id: str | None = None,
        subagent_type: str | None = None,
        subagent_name: str | None = None,
    ) -> dict[str, Any]:
        return build_worker_lifecycle_event(
            scope=scope,
            status=status,
            reason=reason,
            task_tool_call_id=task_tool_call_id,
            parent_tool_call_id=parent_tool_call_id,
            agent_id=agent_id,
            subagent_type=subagent_type,
            subagent_name=subagent_name,
        )

    def _project_task_result_lifecycle_event(
        self: "AgentService",
        event: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        if event.get("type") != "tool_result":
            return None

        tool_call_id = str(event.get("tool_call_id") or "")
        if not tool_call_id:
            return None

        tool_name = event.get("tool_name")
        if not is_subagent_dispatch_tool_name(
            str(tool_name) if isinstance(tool_name, str) else None
        ):
            return None

        lifecycle_projection = project_subagent_lifecycle_from_task_result(
            is_error=bool(event.get("is_error")),
            content=str(event.get("content") or ""),
        )
        if lifecycle_projection is None:
            return None

        return self._build_worker_lifecycle_event(
            scope="subagent",
            status=lifecycle_projection.status,
            reason=lifecycle_projection.reason,
            task_tool_call_id=tool_call_id,
            parent_tool_call_id=(
                str(event.get("parent_tool_call_id"))
                if event.get("parent_tool_call_id")
                else tool_call_id
            ),
            agent_id=(str(event.get("agent_id")) if event.get("agent_id") else None),
            subagent_type=(
                str(event.get("subagent_type")) if event.get("subagent_type") else None
            ),
            subagent_name=(
                str(event.get("subagent_name")) if event.get("subagent_name") else None
            ),
        )

    def _convert_to_event(
        self: "AgentService",
        item: AgentRuntimeEvent,
    ) -> Optional[dict]:
        """
        将底层 runtime 的输出项转换为 SSE 事件

        返回当前前端兼容的统一事件格式，便于 SSE 消费和落盘

        Args:
            item: runtime 输出的消息项
        """
        if item.kind == "worker_lifecycle":
            return self._build_worker_lifecycle_event(
                scope=item.scope or "host",
                status=item.status or "failed",
                reason=item.reason or "unknown",
                task_tool_call_id=item.task_tool_call_id,
                parent_tool_call_id=item.parent_tool_call_id,
                agent_id=item.agent_id,
                subagent_type=item.subagent_type,
                subagent_name=item.subagent_name,
            )

        if item.kind == "content" and item.content_type == "text":
            return {
                "type": "content",
                "content_type": "text",
                "text": item.text or "",
            }

        if item.kind == "content" and item.content_type == "think":
            return {
                "type": "content",
                "content_type": "think",
                "think": item.think or "",
            }

        if item.kind == "tool_call":
            event = {
                "type": "tool_call",
                "tool_call_id": item.tool_call_id,
                "tool_name": item.tool_name or "unknown",
                "arguments": item.arguments or {},
            }
            if item.subagent_name is not None:
                event["subagent_name"] = item.subagent_name
            if item.subagent_type is not None:
                event["subagent_type"] = item.subagent_type
            if item.parent_tool_call_id is not None:
                event["parent_tool_call_id"] = item.parent_tool_call_id
            return event

        if item.kind == "tool_result":
            event = {
                "type": "tool_result",
                "tool_call_id": item.tool_call_id,
                "tool_name": item.tool_name or "unknown",
                "content": item.content or "",
                "is_error": bool(item.is_error),
                "subagent_name": item.subagent_name,
            }
            if item.parent_tool_call_id is not None:
                event["parent_tool_call_id"] = item.parent_tool_call_id
            if item.agent_id is not None:
                event["agent_id"] = item.agent_id
            if item.subagent_type is not None:
                event["subagent_type"] = item.subagent_type
            return event

        if item.kind == "subagent_content":
            event = {
                "type": "subagent_content",
                "content_type": item.content_type,
                "text": item.text,
                "think": item.think,
                "task_tool_call_id": item.task_tool_call_id,
                "subagent_name": item.subagent_name,
            }
            if item.parent_tool_call_id is not None:
                event["parent_tool_call_id"] = item.parent_tool_call_id
            if item.agent_id is not None:
                event["agent_id"] = item.agent_id
            if item.subagent_type is not None:
                event["subagent_type"] = item.subagent_type
            return event

        if item.kind == "subagent_tool_call":
            event = {
                "type": "subagent_tool_call",
                "tool_call_id": item.tool_call_id,
                "tool_name": item.tool_name or "unknown",
                "arguments": item.arguments or {},
                "task_tool_call_id": item.task_tool_call_id,
                "subagent_name": item.subagent_name,
            }
            if item.parent_tool_call_id is not None:
                event["parent_tool_call_id"] = item.parent_tool_call_id
            if item.agent_id is not None:
                event["agent_id"] = item.agent_id
            if item.subagent_type is not None:
                event["subagent_type"] = item.subagent_type
            return event

        if item.kind == "subagent_tool_result":
            event = {
                "type": "subagent_tool_result",
                "tool_call_id": item.tool_call_id,
                "tool_name": item.tool_name or "unknown",
                "content": item.content or "",
                "is_error": bool(item.is_error),
                "task_tool_call_id": item.task_tool_call_id,
                "subagent_name": item.subagent_name,
            }
            if item.parent_tool_call_id is not None:
                event["parent_tool_call_id"] = item.parent_tool_call_id
            if item.agent_id is not None:
                event["agent_id"] = item.agent_id
            if item.subagent_type is not None:
                event["subagent_type"] = item.subagent_type
            return event

        if item.kind == "token_usage":
            return {
                "type": "token_usage",
                "input": item.input_tokens or 0,
                "output": item.output_tokens or 0,
            }

        if item.kind == "budget_limited":
            return {
                "type": "budget_limited",
                "text": item.text or "当前会话预算已耗尽，本轮不会继续执行。",
            }

        if item.kind == "budget_updated":
            payload: dict[str, Any] = {}
            if item.text:
                try:
                    payload = json.loads(item.text)
                except json.JSONDecodeError:
                    payload = {}
            return {
                "type": "budget_updated",
                **payload,
            }

        if item.kind in {"task_call_begin", "task_call_end"}:
            return None

        if item.kind == "data":
            return {"type": "data", "content": item.content or ""}

        if item.kind == "ask_user_request":
            import json

            return {
                "type": "ask_user_request",
                "request": json.loads(item.content or "{}"),
            }

        return None

    def _project_output_item(
        self: "AgentService",
        item: Any,
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        if _is_tool_call_part(item):
            pending_tool_call = state.get("pending_tool_call")
            if pending_tool_call is not None:
                pending_tool_call.setdefault("arguments_parts", []).append(
                    getattr(item, "arguments_part", "") or ""
                )
            return events

        if _merge_pending_tool_call_item(state, item):
            return events

        if state.get(
            "pending_tool_call"
        ) is not None and _should_flush_pending_tool_call_before_item(item):
            flushed_event = self._flush_pending_tool_call(state)
            if flushed_event is not None:
                events.append(flushed_event)

        control_events = self._project_host_control_event(item, state)
        if control_events:
            events.extend(control_events)
            return events

        if _is_tool_call(item):
            self._ensure_host_turn_started(state, events)
            self._maybe_prepend_host_step_for_tool_call(state, events)
            func = getattr(item, "function", None)
            state["pending_tool_call"] = {
                "tool_call_id": getattr(item, "id", str(uuid.uuid4())),
                "tool_name": (getattr(func, "name", None) if func is not None else None)
                or "unknown",
                "arguments_text": (
                    getattr(func, "arguments", None) if func is not None else None
                ),
                "arguments_parts": [],
            }
            return events

        runtime_event = (
            item
            if isinstance(item, AgentRuntimeEvent)
            else self._coerce_runtime_event(item, state)
        )
        if runtime_event is None:
            return events

        event = self._convert_to_event(runtime_event)
        if event is not None:
            if _is_host_execution_event(event):
                self._ensure_host_turn_started(state, events)
                if event.get("type") == "tool_call":
                    self._maybe_prepend_host_step_for_tool_call(state, events)
            events.append(event)

        if runtime_event.kind == "tool_call":
            tool_call_id = str(runtime_event.tool_call_id or "").strip()
            tool_name = str(runtime_event.tool_name or "unknown").strip() or "unknown"
            if tool_call_id:
                state["tool_call_map"][tool_call_id] = tool_name
                if is_subagent_dispatch_tool_name(tool_name):
                    subagent_name = (
                        str(runtime_event.subagent_name or "").strip() or None
                    )
                    if subagent_name is None:
                        subagent_name = extract_subagent_display_name(
                            tool_name,
                            runtime_event.arguments or {},
                        )
                    subagent_type = (
                        str(runtime_event.subagent_type or "").strip() or None
                    )
                    raw_subagent_type = (runtime_event.arguments or {}).get(
                        "subagent_type"
                    )
                    if subagent_type is None and isinstance(raw_subagent_type, str):
                        subagent_type = raw_subagent_type.strip() or None
                    state["task_call_map"][tool_call_id] = {
                        "tool_call_id": tool_call_id,
                        "parent_tool_call_id": runtime_event.parent_tool_call_id
                        or tool_call_id,
                        "subagent_name": subagent_name,
                        "subagent_type": subagent_type,
                        "agent_id": runtime_event.agent_id,
                        "tool_call_map": {},
                    }
        elif runtime_event.kind == "task_call_begin":
            state["current_task_call"] = {
                "tool_call_id": runtime_event.tool_call_id,
                "parent_tool_call_id": runtime_event.parent_tool_call_id
                or runtime_event.tool_call_id,
                "subagent_name": runtime_event.subagent_name,
                "subagent_type": runtime_event.subagent_type,
                "agent_id": runtime_event.agent_id,
                "tool_call_map": {},
            }
        elif runtime_event.kind == "task_call_end":
            state["current_task_call"] = None

        return events

    def _project_host_control_event(
        self: "AgentService",
        item: Any,
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if _is_turn_begin_item(item):
            state["turn_started"] = True
            state["pending_host_step"] = False
            state["turn_n"] = state.get("turn_n", 0) + 1
            return [{"type": "turn_begin", "turn_n": state["turn_n"]}]

        if _is_step_begin_item(item):
            return []

        if _is_status_update(item):
            if project_host_lifecycle_from_wire(item) is not None:
                return []
            events: list[dict[str, Any]] = []
            self._ensure_host_turn_started(state, events)
            status_value = getattr(item, "status", None)
            if not isinstance(status_value, str) or not status_value.strip():
                status_value = "running"
            events.append({"type": "status", "status": status_value.strip().lower()})
            return events

        return []

    def _ensure_host_turn_started(
        self: "AgentService",
        state: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> None:
        if state.get("turn_started"):
            return
        state["turn_started"] = True
        state["turn_n"] = state.get("turn_n", 0) + 1
        events.append({"type": "turn_begin", "turn_n": state["turn_n"]})

    def _maybe_prepend_host_step_for_tool_call(
        self: "AgentService",
        state: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> None:
        pass

    def _flush_projected_output(
        self: "AgentService",
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        flushed_event = self._flush_pending_tool_call(state)
        return [flushed_event] if flushed_event is not None else []

    def _flush_pending_tool_call(
        self: "AgentService",
        state: dict[str, Any],
    ) -> dict[str, Any] | None:
        pending_tool_call = state.get("pending_tool_call")
        if pending_tool_call is None:
            return None

        arguments = _parse_tool_argument_fragments(
            pending_tool_call.get("arguments_text"),
            pending_tool_call.get("arguments_parts", []),
        )
        tool_call_id = str(pending_tool_call["tool_call_id"])
        raw_tool_name = str(pending_tool_call["tool_name"])
        tool_name = project_runtime_tool_event_name(raw_tool_name) or "unknown"
        subagent_name = extract_subagent_display_name(raw_tool_name, arguments)
        requested_subagent_type = arguments.get("subagent_type")
        if (
            not isinstance(requested_subagent_type, str)
            or not requested_subagent_type.strip()
        ):
            requested_subagent_type = None
        is_dispatch_tool = is_subagent_dispatch_tool_name(raw_tool_name)

        state["tool_call_map"][tool_call_id] = tool_name
        if is_dispatch_tool:
            state["task_call_map"][tool_call_id] = {
                "tool_call_id": tool_call_id,
                "parent_tool_call_id": tool_call_id,
                "subagent_name": subagent_name,
                "subagent_type": requested_subagent_type,
                "tool_call_map": {},
            }

        state["pending_tool_call"] = None
        event = {
            "type": "tool_call",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "arguments": arguments,
        }
        if subagent_name is not None:
            event["subagent_name"] = subagent_name
        if requested_subagent_type is not None:
            event["subagent_type"] = requested_subagent_type
        if is_dispatch_tool:
            event["parent_tool_call_id"] = tool_call_id
        return event

    def _coerce_runtime_event(
        self: "AgentService",
        item: Any,
        state: dict[str, Any],
    ) -> AgentRuntimeEvent | None:
        host_lifecycle_projection = project_host_lifecycle_from_wire(item)
        if host_lifecycle_projection is not None:
            return AgentRuntimeEvent(
                kind="worker_lifecycle",
                scope="host",
                status=host_lifecycle_projection.status,
                reason=host_lifecycle_projection.reason,
            )

        if _class_name(item) in {"TurnBegin", "StepBegin", "StatusUpdate"}:
            return None

        if _is_text_part(item):
            return AgentRuntimeEvent(
                kind="content",
                content_type="text",
                text=getattr(item, "text", ""),
            )

        if _is_think_part(item):
            return AgentRuntimeEvent(
                kind="content",
                content_type="think",
                think=getattr(item, "think", ""),
            )

        if _is_tool_result(item):
            return_value = getattr(item, "return_value", None)
            is_error = bool(getattr(return_value, "is_error", False))
            raw_output = return_value
            if hasattr(return_value, "output") and getattr(return_value, "output"):
                raw_output = return_value.output
            elif hasattr(return_value, "message") and getattr(return_value, "message"):
                raw_output = return_value.message

            tool_call_id = getattr(item, "tool_call_id", None)
            tool_name = state["tool_call_map"].get(tool_call_id, "unknown")
            task_context = state["task_call_map"].get(tool_call_id)
            return AgentRuntimeEvent(
                kind="tool_result",
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                content=_serialize_tool_output(raw_output),
                is_error=is_error,
                parent_tool_call_id=tool_call_id if task_context else None,
                agent_id=(
                    str(task_context.get("agent_id"))
                    if task_context and task_context.get("agent_id")
                    else None
                ),
                subagent_type=(
                    str(task_context.get("subagent_type"))
                    if task_context and task_context.get("subagent_type")
                    else None
                ),
                subagent_name=(
                    str(task_context.get("subagent_name"))
                    if task_context and task_context.get("subagent_name")
                    else None
                ),
            )

        if _is_subagent_event(item):
            return self._coerce_subagent_runtime_event(item, state)

        item_type = getattr(item, "type", None)
        if item_type == "task_call_begin":
            tool_call_id = getattr(item, "tool_call_id", None)
            subagent_name = getattr(item, "name", None)
            if tool_call_id:
                task_context = state["task_call_map"].setdefault(tool_call_id, {})
                task_context["parent_tool_call_id"] = tool_call_id
                task_context["subagent_name"] = subagent_name
                task_context.setdefault("tool_call_map", {})
            return AgentRuntimeEvent(
                kind="task_call_begin",
                tool_call_id=tool_call_id,
                parent_tool_call_id=tool_call_id,
                subagent_name=subagent_name,
            )

        if item_type == "task_call_end":
            return AgentRuntimeEvent(
                kind="task_call_end",
                tool_call_id=getattr(item, "tool_call_id", None),
            )

        return AgentRuntimeEvent(kind="data", content=str(item))

    def _coerce_subagent_runtime_event(
        self: "AgentService",
        msg: Any,
        state: dict[str, Any],
    ) -> AgentRuntimeEvent | None:
        parent_tool_call_id = getattr(msg, "parent_tool_call_id", None)
        task_tool_call_id = parent_tool_call_id or getattr(
            msg, "task_tool_call_id", None
        )
        task_context = None
        if task_tool_call_id and task_tool_call_id in state["task_call_map"]:
            task_context = state["task_call_map"][task_tool_call_id]
        elif state.get("current_task_call") is not None:
            task_context = state["current_task_call"]
        raw_agent_id = getattr(msg, "agent_id", None)
        raw_subagent_type = getattr(msg, "subagent_type", None)
        if task_context is not None:
            if isinstance(raw_agent_id, str) and raw_agent_id.strip():
                task_context["agent_id"] = raw_agent_id.strip()
            if isinstance(raw_subagent_type, str) and raw_subagent_type.strip():
                task_context["subagent_type"] = raw_subagent_type.strip()
        raw_subagent_name = getattr(msg, "subagent_name", None)
        if (
            task_context is not None
            and isinstance(raw_subagent_name, str)
            and raw_subagent_name.strip()
        ):
            task_context["subagent_name"] = raw_subagent_name.strip()

        agent_id = (
            str(task_context.get("agent_id"))
            if task_context and task_context.get("agent_id")
            else (
                raw_agent_id.strip()
                if isinstance(raw_agent_id, str) and raw_agent_id.strip()
                else None
            )
        )
        subagent_type = (
            str(task_context.get("subagent_type"))
            if task_context and task_context.get("subagent_type")
            else (
                raw_subagent_type.strip()
                if isinstance(raw_subagent_type, str) and raw_subagent_type.strip()
                else None
            )
        )

        subagent_name = (
            str(task_context.get("subagent_name"))
            if task_context and task_context.get("subagent_name")
            else (
                raw_subagent_name.strip()
                if isinstance(raw_subagent_name, str) and raw_subagent_name.strip()
                else None
            )
        )
        event = getattr(msg, "event", None)
        lifecycle_projection = project_subagent_lifecycle_from_wire(event)
        if lifecycle_projection is not None:
            return AgentRuntimeEvent(
                kind="worker_lifecycle",
                scope="subagent",
                status=lifecycle_projection.status,
                reason=lifecycle_projection.reason,
                task_tool_call_id=task_tool_call_id,
                parent_tool_call_id=task_tool_call_id,
                agent_id=agent_id,
                subagent_type=subagent_type,
                subagent_name=subagent_name,
            )

        if _is_text_part(event):
            text = str(getattr(event, "text", "") or "").strip()
            if not text:
                return None
            return AgentRuntimeEvent(
                kind="subagent_content",
                content_type="text",
                text=text,
                task_tool_call_id=task_tool_call_id,
                parent_tool_call_id=task_tool_call_id,
                agent_id=agent_id,
                subagent_type=subagent_type,
                subagent_name=subagent_name,
            )

        if _is_think_part(event):
            think = str(getattr(event, "think", "") or "").strip()
            if not think:
                return None
            return AgentRuntimeEvent(
                kind="subagent_content",
                content_type="think",
                think=think,
                task_tool_call_id=task_tool_call_id,
                parent_tool_call_id=task_tool_call_id,
                agent_id=agent_id,
                subagent_type=subagent_type,
                subagent_name=subagent_name,
            )

        if _is_tool_call(event):
            func = getattr(event, "function", None)
            tool_call_id = getattr(event, "id", str(uuid.uuid4()))
            raw_tool_name = (
                getattr(func, "name", None) if func is not None else None
            ) or "unknown"
            tool_name = project_runtime_tool_event_name(raw_tool_name) or "unknown"
            if task_context is not None:
                task_context.setdefault("tool_call_map", {})[tool_call_id] = tool_name
            return AgentRuntimeEvent(
                kind="subagent_tool_call",
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                arguments=_parse_tool_arguments(
                    getattr(func, "arguments", None) if func is not None else None
                ),
                task_tool_call_id=task_tool_call_id,
                parent_tool_call_id=task_tool_call_id,
                agent_id=agent_id,
                subagent_type=subagent_type,
                subagent_name=subagent_name,
            )

        event_type = getattr(event, "type", None)
        if event_type == "tool_result" or _is_tool_result(event):
            tool_call_id = getattr(event, "tool_call_id", None)
            tool_name = None
            if task_context is not None:
                tool_name = task_context.get("tool_call_map", {}).get(tool_call_id)

            content = getattr(event, "content", None)
            if content is None and hasattr(event, "return_value"):
                return_value = getattr(event, "return_value", None)
                if hasattr(return_value, "output") and getattr(return_value, "output"):
                    content = return_value.output
                elif hasattr(return_value, "message") and getattr(
                    return_value, "message"
                ):
                    content = return_value.message

            return AgentRuntimeEvent(
                kind="subagent_tool_result",
                tool_call_id=tool_call_id,
                tool_name=tool_name or "unknown",
                content=_serialize_tool_output(content),
                is_error=bool(getattr(event, "is_error", False)),
                task_tool_call_id=task_tool_call_id,
                parent_tool_call_id=task_tool_call_id,
                agent_id=agent_id,
                subagent_type=subagent_type,
                subagent_name=subagent_name,
            )

        if event_type == "token_usage":
            token_usage = getattr(event, "token_usage", None)
            return AgentRuntimeEvent(
                kind="token_usage",
                input_tokens=(
                    getattr(token_usage, "input_other", 0) if token_usage else 0
                ),
                output_tokens=getattr(token_usage, "output", 0) if token_usage else 0,
            )

        return None

    def _is_system_reminder_message(self: "AgentService", msg: dict) -> bool:
        """检查消息是否为底层 runtime 注入的 system-reminder 消息。"""
        if msg.get("role") != "user":
            return False
        content = msg.get("content")
        if not isinstance(content, str):
            return False
        return content.strip().startswith("<system-reminder>")


def _class_name(item: Any) -> str:
    return item.__class__.__name__ if item is not None else ""


def _is_text_part(item: Any) -> bool:
    return _class_name(item) == "TextPart" and hasattr(item, "text")


def _is_think_part(item: Any) -> bool:
    return _class_name(item) == "ThinkPart" and hasattr(item, "think")


def _is_tool_call(item: Any) -> bool:
    return (
        _class_name(item) == "ToolCall"
        and hasattr(item, "id")
        and hasattr(item, "function")
    )


def _is_tool_call_part(item: Any) -> bool:
    return _class_name(item) == "ToolCallPart" and hasattr(item, "arguments_part")


def _is_tool_result(item: Any) -> bool:
    return _class_name(item) == "ToolResult" and hasattr(item, "tool_call_id")


def _is_turn_begin_item(item: Any) -> bool:
    item_type = getattr(item, "type", None)
    if isinstance(item_type, str) and item_type.strip().lower() == "turn_begin":
        return True
    return _class_name(item) == "TurnBegin"


def _is_step_begin_item(item: Any) -> bool:
    item_type = getattr(item, "type", None)
    if isinstance(item_type, str) and item_type.strip().lower() == "step_begin":
        return True
    return _class_name(item) == "StepBegin"


def _is_status_update(item: Any) -> bool:
    return _class_name(item) == "StatusUpdate"


def _should_flush_pending_tool_call_before_item(item: Any) -> bool:
    return not _is_status_update(item)


def _merge_pending_tool_call_item(state: dict[str, Any], item: Any) -> bool:
    pending_tool_call = state.get("pending_tool_call")
    if pending_tool_call is None or not _is_tool_call(item):
        return False

    func = getattr(item, "function", None)
    tool_call_id = str(getattr(item, "id", str(uuid.uuid4())))
    if tool_call_id != str(pending_tool_call.get("tool_call_id")):
        return False

    arguments_text = getattr(func, "arguments", None) if func is not None else None
    current_arguments_text = pending_tool_call.get("arguments_text")
    if isinstance(arguments_text, str) and arguments_text:
        if (
            not isinstance(current_arguments_text, str)
            or not current_arguments_text
            or len(arguments_text) >= len(current_arguments_text)
        ):
            pending_tool_call["arguments_text"] = arguments_text

    tool_name = (getattr(func, "name", None) if func is not None else None) or "unknown"
    pending_tool_call["tool_name"] = tool_name
    return True


def _is_subagent_event(item: Any) -> bool:
    return _class_name(item) == "SubagentEvent" and hasattr(item, "event")


def _is_host_execution_event(event: dict[str, Any]) -> bool:
    event_type = str(event.get("type") or "").strip().lower()
    if event_type in {"content", "tool_call", "tool_result", "status"}:
        return True
    if event_type == "worker.lifecycle.changed":
        return event.get("scope") == "host"
    return False


def _try_parse_tool_arguments(raw_arguments: str | None) -> dict[str, Any] | None:
    if not raw_arguments:
        return None

    stripped = raw_arguments.strip()
    if not stripped:
        return None

    candidates = [stripped]
    if stripped and not stripped.startswith("{"):
        candidates.append("{" + stripped)

    open_braces = stripped.count("{")
    close_braces = stripped.count("}")
    if open_braces > close_braces:
        candidates.append(stripped + ("}" * (open_braces - close_braces)))
    elif close_braces > open_braces:
        candidates.append(("{" * (close_braces - open_braces)) + stripped)

    if stripped and not stripped.startswith("{") and open_braces >= close_braces:
        candidates.append("{" + stripped + ("}" * max(1, open_braces - close_braces)))

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    return None


def _parse_tool_arguments(raw_arguments: str | None) -> dict[str, Any]:
    parsed = _try_parse_tool_arguments(raw_arguments)
    if parsed is not None:
        return parsed
    return {}


def _parse_tool_argument_fragments(
    arguments_text: str | None,
    arguments_parts: list[str] | None,
) -> dict[str, Any]:
    parts_text = "".join(arguments_parts or [])
    prefix_text = arguments_text or ""

    seen: set[str] = set()
    for candidate in (
        prefix_text + parts_text,
        parts_text,
        prefix_text,
    ):
        if candidate in seen:
            continue
        seen.add(candidate)
        parsed = _try_parse_tool_arguments(candidate)
        if parsed is not None:
            return parsed
    return {}


def _serialize_tool_output(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(_serialize_tool_output(item) for item in content)
    if hasattr(content, "text"):
        return str(content.text)
    if hasattr(content, "image_url"):
        image_url = getattr(content, "image_url")
        url = image_url.url if hasattr(image_url, "url") else str(image_url)
        return f"![image]({url})"
    return "" if content is None else str(content)
