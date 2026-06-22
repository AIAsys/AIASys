"""
子 Agent 独立 SSE 事件流与交互 API。

提供子 Agent 专属的事件通道，子 Agent 内部 content/tool_call/tool_result 等事件
不再全部投影到 Host SSE，而是通过本模块的 SSE 端点消费。
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.auth import require_auth
from app.models.user import UserInfo
from app.services.agent.subagent_lifecycle import get_subagent_lifecycle_manager
from app.services.agent.subagent_registry import SubAgentRegistry, get_subagent_registry
from app.services.agent.subagent_storage import SubAgentStorage
from app.services.tracking import SubAgentTrackingService, get_subagent_tracking_service
from app.utils.path_utils import as_system_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["subagent-events"])

SSE_DONE_MARKER = "data: [DONE]\n\n"


def _get_subagent_registry() -> SubAgentRegistry:
    return get_subagent_registry()


def _get_tracking_service() -> SubAgentTrackingService:
    return get_subagent_tracking_service()


def _wire_record_to_event(record: dict[str, Any]) -> dict[str, Any] | None:
    """把 wire.jsonl 的记录转换为前端事件格式。"""
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    msg_type = message.get("type")
    payload = message.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}

    # 直接复用 SubAgentTrackingService 的 wire 格式
    if msg_type == "ContentPart":
        return {
            "type": "content",
            "content_type": payload.get("type", "text"),
            "text": payload.get("text", ""),
            "think": payload.get("think", ""),
        }
    if msg_type == "ToolCall":
        function = payload.get("function", {})
        return {
            "type": "tool_call",
            "tool_call_id": payload.get("id"),
            "tool_name": function.get("name"),
            "arguments": _safe_parse_arguments(function.get("arguments")),
        }
    if msg_type == "ToolResult":
        return_value = payload.get("return_value", {})
        return {
            "type": "tool_result",
            "tool_call_id": payload.get("tool_call_id"),
            "content": return_value.get("output", ""),
            "is_error": return_value.get("is_error", False),
        }
    if msg_type == "TurnEnd":
        return {"type": "worker.lifecycle.changed", "status": "finished"}
    if msg_type == "StepInterrupted":
        return {
            "type": "worker.lifecycle.changed",
            "status": "interrupted",
            "reason": payload.get("reason", ""),
        }
    if msg_type == "StatusUpdate":
        return {"type": "worker.lifecycle.changed", "status": payload.get("status", "unknown")}
    if msg_type == "metadata":
        return None
    return {"type": "data", "message": message}


def _safe_parse_arguments(raw: Any) -> dict[str, Any]:
    """安全解析工具参数 JSON。"""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {}


def _event_to_sse(event: dict[str, Any]) -> str:
    """将事件字典格式化为 SSE data 行。"""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _sync_read_wire_records(
    wire_file: Any,
    event_id: int,
    last_size: int,
) -> tuple[int, int, list[dict[str, Any]]]:
    """同步读取 wire.jsonl 新增记录，返回 (next_event_id, new_last_size, records)。"""
    next_event_id = event_id
    new_records: list[dict[str, Any]] = []
    try:
        sys_wire_file = as_system_path(str(wire_file))
        if not Path(sys_wire_file).exists():
            return next_event_id, last_size, new_records
        current_size = Path(sys_wire_file).stat().st_size
        if current_size <= last_size:
            return next_event_id, last_size, new_records
        with open(sys_wire_file, "r", encoding="utf-8") as f:
            f.seek(last_size)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                new_records.append(record)
                next_event_id += 1
        return next_event_id, current_size, new_records
    except Exception:
        return next_event_id, last_size, new_records


async def _tail_subagent_wire_file(
    storage: SubAgentStorage,
    last_event_id: int,
    poll_interval_ms: float = 500,
) -> AsyncGenerator[tuple[int, dict[str, Any]], None]:
    """从 wire.jsonl 的指定位置开始 tail，产出 (event_id, event)。"""
    event_id = last_event_id
    last_size = 0
    try:
        if await asyncio.to_thread(storage.wire_file.exists):
            last_size = (await asyncio.to_thread(storage.wire_file.stat)).st_size
    except Exception:
        pass

    while True:
        try:
            event_id, last_size, new_records = await asyncio.to_thread(
                _sync_read_wire_records,
                storage.wire_file,
                event_id,
                last_size,
            )
        except Exception as exc:
            logger.warning("读取子 Agent wire 文件失败: %s", exc)
            new_records = []

        for record in new_records:
            converted = _wire_record_to_event(record)
            if converted is not None:
                yield event_id, converted

        await asyncio.sleep(poll_interval_ms / 1000)


@router.get("/{user_id}/{session_id}/subagents/{agent_id}")
async def get_subagent_detail_endpoint(
    user_id: str,
    session_id: str,
    agent_id: str,
    current_user: UserInfo = Depends(require_auth()),
    tracking_service: SubAgentTrackingService = Depends(_get_tracking_service),
):
    """获取子 Agent 详情（状态、元数据、事件、上下文）。"""
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(status_code=403, detail="You can only access your own sessions")

    detail = tracking_service.get_subagent_detail(user_id, session_id, agent_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Sub Agent not found")

    return asdict(detail)


@router.get("/{user_id}/{session_id}/subagents/{agent_id}/events")
async def subagent_events_stream(
    user_id: str,
    session_id: str,
    agent_id: str,
    last_event_id: int = Query(default=0, ge=0),
    current_user: UserInfo = Depends(require_auth()),
    registry: SubAgentRegistry = Depends(_get_subagent_registry),
    tracking_service: SubAgentTrackingService = Depends(_get_tracking_service),
):
    """子 Agent 独立 SSE 事件流。

    从 wire.jsonl 的指定事件位置开始 tail，实时推送子 Agent 内部事件。
    """
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(status_code=403, detail="You can only access your own sessions")

    detail = tracking_service.get_subagent_detail(user_id, session_id, agent_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Sub Agent not found")

    storage = SubAgentStorage(user_id, session_id, agent_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for event_id, event in _tail_subagent_wire_file(storage, last_event_id):
                event["event_id"] = event_id
                yield _event_to_sse(event)
        except asyncio.CancelledError:
            logger.debug("子 Agent SSE 连接取消: agent_id=%s", agent_id)
            raise
        finally:
            yield SSE_DONE_MARKER

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/{user_id}/{session_id}/subagents/{agent_id}/message")
async def send_message_to_subagent(
    user_id: str,
    session_id: str,
    agent_id: str,
    request: dict[str, Any],
    current_user: UserInfo = Depends(require_auth()),
    registry: SubAgentRegistry = Depends(_get_subagent_registry),
    tracking_service: SubAgentTrackingService = Depends(_get_tracking_service),
):
    """向子 Agent 发送消息并流式返回其产生的事件。"""
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(status_code=403, detail="You can only access your own sessions")

    detail = tracking_service.get_subagent_detail(user_id, session_id, agent_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Sub Agent not found")

    message = str(request.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    if not await registry.ais_active(agent_id):
        raise HTTPException(status_code=409, detail="子 Agent 未运行或已关闭")

    lifecycle = get_subagent_lifecycle_manager()

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for event in lifecycle.send_input(agent_id, message):
                payload: dict[str, Any] = {"type": event.kind}
                for field in dataclasses.fields(event):
                    value = getattr(event, field.name)
                    if value is not None:
                        payload[field.name] = value
                yield _event_to_sse(payload)
        except asyncio.CancelledError:
            logger.debug("子 Agent message SSE 连接取消: agent_id=%s", agent_id)
            raise
        finally:
            yield SSE_DONE_MARKER

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/{user_id}/{session_id}/subagents/{agent_id}/close")
async def close_subagent(
    user_id: str,
    session_id: str,
    agent_id: str,
    current_user: UserInfo = Depends(require_auth()),
    registry: SubAgentRegistry = Depends(_get_subagent_registry),
    tracking_service: SubAgentTrackingService = Depends(_get_tracking_service),
):
    """显式关闭子 Agent。"""
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(status_code=403, detail="You can only access your own sessions")

    detail = tracking_service.get_subagent_detail(user_id, session_id, agent_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Sub Agent not found")

    lifecycle = get_subagent_lifecycle_manager()
    closed = await lifecycle.close_agent(agent_id)
    # 兜底：即使运行态未加载（如后端重启后），也把持久化状态标记为 closed
    if not closed and detail:
        storage = SubAgentStorage(user_id, session_id, agent_id)
        storage.update_status("closed")
        closed = True
    return {"success": closed, "agent_id": agent_id}


@router.post("/{user_id}/{session_id}/subagents/{agent_id}/resume")
async def resume_subagent(
    user_id: str,
    session_id: str,
    agent_id: str,
    current_user: UserInfo = Depends(require_auth()),
    tracking_service: SubAgentTrackingService = Depends(_get_tracking_service),
):
    """从持久化存储恢复子 Agent 运行态。"""
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(status_code=403, detail="You can only access your own sessions")

    detail = tracking_service.get_subagent_detail(user_id, session_id, agent_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Sub Agent not found")

    lifecycle = get_subagent_lifecycle_manager()
    resumed = await lifecycle.resume_agent(user_id, session_id, agent_id)
    return {"success": resumed, "agent_id": agent_id}
