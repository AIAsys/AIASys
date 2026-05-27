"""
Sub Agent 跟踪服务

跟踪 Sub Agent 生命周期，维护执行树结构
用于前端展示 Host Agent 和 Sub Agents 的执行状态
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import WORKSPACE_DIR

logger = logging.getLogger(__name__)


def _normalize_execution_tree_status(status: Optional[str], *, default: str = "idle") -> str:
    """将后端内部生命周期状态归一为执行树接口使用的前端状态集合。"""
    normalized = (status or "").strip().lower()
    if not normalized:
        return default

    if normalized in {"completed", "failed", "cancelled", "queued", "running", "idle"}:
        return normalized
    if normalized == "finished":
        return "completed"
    if normalized == "interrupted":
        return "cancelled"
    if normalized in {"awaiting_user", "blocked", "paused"}:
        return "running"

    return default


def _normalize_optional_string(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _get_user_uuid(user_id: str) -> str:
    """单用户部署下，user_id 直接作为目录名使用。

    当前阶段为单用户版本，不需要 UUID 解析层。
    多用户支持时再引入数据库查询和 UUID 转换。
    """
    return user_id


def _get_session_subagents_dir(user_id: str, session_id: str) -> Path:
    """获取 Sub Agents 存储目录

    Subagents 存储在: workspaces/{user_uuid}/{session_id}/.aiasys/session/{session_id}/subagents/
    """
    user_uuid = _get_user_uuid(user_id)
    return WORKSPACE_DIR / user_uuid / session_id / ".aiasys" / "session" / "subagents"


@dataclass
class SubAgentOwnershipProjection:
    """协作节点 ownership 投影。"""

    host_session_id: str
    parent_tool_call_id: Optional[str]
    agent_id: str
    subagent_type: str


@dataclass
class SubAgentSummary:
    """Sub Agent 摘要信息（用于执行树概览）"""

    id: str
    name: str
    status: str  # queued, running, completed, failed, cancelled
    description: str = ""
    ownership: SubAgentOwnershipProjection | None = None
    progress: Dict[str, int] = field(
        default_factory=dict
    )  # {current_step, total_steps, tool_calls}
    duration_ms: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    triggered_by_step: int = 0  # Host Agent 的哪一步触发的
    task_tool_call_id: str = ""


@dataclass
class HostExecutionTree:
    """Host Agent 执行树"""

    host_status: str
    host_current_step: int
    host_total_steps: int
    subagent_calls: List[Dict[str, Any]]  # 包含 trigger 信息和 SubAgentSummary


@dataclass
class SubAgentDetail:
    """Sub Agent 完整详情"""

    id: str
    name: str
    status: str
    description: str
    meta: Dict[str, Any]
    events: List[Dict[str, Any]]  # wire.jsonl 内容
    context: List[Dict[str, Any]]  # context.jsonl 内容
    output_files: List[Dict[str, Any]]
    ownership: SubAgentOwnershipProjection | None = None
    duration_ms: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SubAgentTrackingService:
    """
    Sub Agent 跟踪服务

    负责：
    1. 扫描 session 的 subagents/ 目录
    2. 解析 meta.json 和 wire.jsonl
    3. 关联 Host Agent 的 Task Call 和 Sub Agent
    4. 提供执行树查询接口
    """

    def _get_session_dir(self, user_id: str, session_id: str) -> Path:
        """获取 session 工作目录"""
        return WORKSPACE_DIR / user_id / session_id

    def _get_subagents_dir(self, user_id: str, session_id: str) -> Path:
        """获取 subagents 目录"""
        return _get_session_subagents_dir(user_id, session_id)

    def _parse_meta_json(self, meta_path: Path) -> Optional[Dict[str, Any]]:
        """解析 meta.json"""
        try:
            if not meta_path.exists():
                return None
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("解析 meta.json 失败: %s, error=%s", meta_path, e)
            return None

    def _build_ownership_projection(
        self,
        *,
        session_id: str,
        agent_id: str,
        meta: Dict[str, Any],
    ) -> SubAgentOwnershipProjection:
        launch_spec = meta.get("launch_spec", {})
        launch_spec_payload = launch_spec if isinstance(launch_spec, dict) else {}
        normalized_agent_id = (
            _normalize_optional_string(meta.get("agent_id"))
            or _normalize_optional_string(launch_spec_payload.get("agent_id"))
            or agent_id
        )
        subagent_type = (
            _normalize_optional_string(meta.get("subagent_type"))
            or _normalize_optional_string(launch_spec_payload.get("subagent_type"))
            or "unknown"
        )
        return SubAgentOwnershipProjection(
            host_session_id=_normalize_optional_string(meta.get("host_session_id")) or session_id,
            parent_tool_call_id=_normalize_optional_string(meta.get("last_task_id")),
            agent_id=normalized_agent_id,
            subagent_type=subagent_type,
        )

    def _serialize_ownership_projection(
        self,
        ownership: SubAgentOwnershipProjection,
    ) -> Dict[str, Any]:
        return {
            "host_session_id": ownership.host_session_id,
            "parent_tool_call_id": ownership.parent_tool_call_id,
            "agent_id": ownership.agent_id,
            "subagent_type": ownership.subagent_type,
        }

    def _parse_wire_jsonl(self, wire_path: Path) -> List[Dict[str, Any]]:
        """解析 wire.jsonl 并转换为前端友好的事件格式

        wire.jsonl 格式:
        - 第一行: metadata {"type": "metadata", "protocol_version": "..."}
        - 后续行: WireMessageRecord {"timestamp": ..., "message": {"type": "...", "payload": {...}}}
        """
        events = []
        tool_name_map: Dict[str, str] = {}
        try:
            if not wire_path.exists():
                return events
            with open(wire_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        # 跳过 metadata
                        if record.get("type") == "metadata":
                            continue
                        # 提取 message 部分
                        message = record.get("message", {})
                        timestamp = record.get("timestamp")
                        converted = self._convert_wire_event(message, timestamp)
                        if converted:
                            tool_call_id = converted.get("tool_call_id")
                            if (
                                converted.get("type") == "tool_call"
                                and isinstance(tool_call_id, str)
                                and tool_call_id
                            ):
                                tool_name = converted.get("tool_name")
                                if isinstance(tool_name, str) and tool_name:
                                    tool_name_map[tool_call_id] = tool_name
                            elif (
                                converted.get("type") == "tool_result"
                                and isinstance(tool_call_id, str)
                                and tool_call_id
                            ):
                                mapped_tool_name = tool_name_map.get(tool_call_id)
                                if mapped_tool_name:
                                    converted["tool_name"] = mapped_tool_name
                            events.append(converted)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning("解析 wire.jsonl 失败: %s, error=%s", wire_path, e)
        return events

    def _parse_context_jsonl(self, context_path: Path) -> List[Dict[str, Any]]:
        """解析 context.jsonl（普通消息 JSONL）。"""
        messages: List[Dict[str, Any]] = []
        try:
            if not context_path.exists():
                return messages
            with open(context_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(record, dict):
                        messages.append(record)
        except Exception as e:
            logger.warning("解析 context.jsonl 失败: %s, error=%s", context_path, e)
        return messages

    def _convert_wire_event(
        self, message: Dict[str, Any], timestamp: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """将 wire message 转换为前端友好的格式

        WireMessageEnvelope 格式: {"type": "...", "payload": {...}}
        注意: ContentPart (text, think) 在 payload 中
        """
        msg_type = message.get("type", "")
        payload = message.get("payload", message)

        # Turn 开始/结束 (注意：wire.jsonl 中使用 TurnBegin/TurnEnd)
        if msg_type == "TurnBegin":
            return {
                "type": "turn_begin",
                "timestamp": timestamp,
            }

        if msg_type == "TurnEnd":
            return {
                "type": "turn_end",
                "timestamp": timestamp,
            }

        # Step 开始 (注意：wire.jsonl 中使用 StepBegin)
        if msg_type == "StepBegin":
            return {
                "type": "step_begin",
                "step_n": payload.get("n", 0) if isinstance(payload, dict) else 0,
                "timestamp": timestamp,
            }

        # ContentPart - 内容片段 (text, think 等在 payload 中)
        if msg_type == "ContentPart":
            content_type = payload.get("type") if isinstance(payload, dict) else None

            if content_type == "text":
                text = payload.get("text", "").strip() if isinstance(payload, dict) else ""
                if text:
                    return {
                        "type": "text",
                        "text": text,
                        "timestamp": timestamp,
                    }
                return None

            if content_type == "think":
                think = payload.get("think", "").strip() if isinstance(payload, dict) else ""
                if think:
                    return {
                        "type": "think",
                        "think": think,
                        "timestamp": timestamp,
                    }
                return None

        # 工具调用 - ToolCall 类型
        if msg_type == "ToolCall":
            func = payload.get("function", {}) if isinstance(payload, dict) else {}
            return {
                "type": "tool_call",
                "tool_call_id": payload.get("id") if isinstance(payload, dict) else None,
                "tool_name": func.get("name", "unknown"),
                "arguments": func.get("arguments", "{}"),
                "timestamp": timestamp,
            }

        # 工具结果 - ToolResult 类型
        if msg_type == "ToolResult":
            return_value = payload.get("return_value", {}) if isinstance(payload, dict) else {}
            is_error = (
                return_value.get("is_error", False) if isinstance(return_value, dict) else False
            )

            # 提取 output，优先保留真实 stdout/stderr 内容，再补 brief/message
            output_sections: List[str] = []
            if isinstance(return_value, dict):
                raw_output = return_value.get("output", "")
                if isinstance(raw_output, str) and raw_output.strip():
                    output_sections.append(raw_output.strip())

                raw_message = return_value.get("message", "")
                if isinstance(raw_message, str) and raw_message.strip():
                    normalized_message = raw_message.strip()
                    if normalized_message not in output_sections:
                        output_sections.append(normalized_message)

                # 处理 display blocks
                display = return_value.get("display", [])
                if display and isinstance(display, list):
                    for d in display:
                        if isinstance(d, dict) and d.get("type") in ["brief", "text"]:
                            display_text = d.get("text", "")
                            if (
                                isinstance(display_text, str)
                                and display_text.strip()
                                and display_text.strip() not in output_sections
                            ):
                                output_sections.append(display_text.strip())

            output = "\n\n".join(output_sections)

            tool_call_id = payload.get("tool_call_id") if isinstance(payload, dict) else None

            return {
                "type": "tool_result",
                "tool_call_id": tool_call_id,
                "tool_name": "unknown",
                "content": output,
                "is_error": is_error,
                "timestamp": timestamp,
            }

        # StatusUpdate - 状态更新
        if msg_type == "StatusUpdate":
            return {
                "type": "status",
                "status": "running",
                "timestamp": timestamp,
            }

        # SubAgentEvent - 嵌套的子代理事件
        if msg_type == "subagent_event":
            event_payload = payload if isinstance(payload, dict) else message
            # 提取内部事件
            inner_event = event_payload.get("event", {})

            # 递归处理内部事件，但标记为子代理事件
            converted = self._convert_wire_event(inner_event, timestamp)
            if converted:
                converted["scope"] = "subagent"
                converted["parent_tool_call_id"] = event_payload.get("parent_tool_call_id")
                converted["agent_id"] = event_payload.get("agent_id")
                converted["subagent_type"] = event_payload.get("subagent_type")
            return converted

        # 不支持的类型，返回 None
        return None

    def _get_output_files(self, output_dir: Path) -> List[Dict[str, Any]]:
        """获取子 Agent output 目录文件列表。"""
        files = []
        try:
            if not output_dir.exists() or not output_dir.is_dir():
                return files
            for file_path in output_dir.iterdir():
                if file_path.is_file():
                    stat = file_path.stat()
                    files.append(
                        {
                            "name": file_path.name,
                            "path": str(file_path.relative_to(WORKSPACE_DIR)),
                            "size": stat.st_size,
                            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        }
                    )
        except Exception as e:
            logger.warning("扫描 output 目录失败: %s, error=%s", output_dir, e)
        return files

    def _get_subagent_workspace_files(self, workspace_dir: Path) -> List[Dict[str, Any]]:
        """获取 Sub Agent 工作区的所有文件（递归扫描）

        Worker 工作区路径: workspaces/{user_id}/{session_id}/subagents/{agent_id}/
        """
        files = []
        try:
            if not workspace_dir.exists() or not workspace_dir.is_dir():
                return files

            # 递归遍历所有文件，排除 .aiasys/session 和内部元数据
            for file_path in workspace_dir.rglob("*"):
                if not file_path.is_file():
                    continue

                # 跳过内部元数据文件
                relative_path = file_path.relative_to(workspace_dir)
                if str(relative_path).startswith(".") or ".aiasys/session/" in str(relative_path):
                    continue

                stat = file_path.stat()
                files.append(
                    {
                        "name": str(relative_path),
                        "path": str(file_path.relative_to(WORKSPACE_DIR)),
                        "size": stat.st_size,
                        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    }
                )

            # 按修改时间排序
            files.sort(key=lambda x: x["modified_at"], reverse=True)

        except Exception as e:
            logger.warning("扫描 Worker 工作区失败: %s, error=%s", workspace_dir, e)
        return files

    def _calculate_progress(self, events: List[Dict[str, Any]]) -> Dict[str, int]:
        """从 events 计算进度"""
        current_step = 0
        step_events = 0
        tool_calls = 0

        for event in events:
            event_type = event.get("type", "")
            if event_type == "step_begin":
                step_events += 1
                reported_step = event.get("step_n", 0)
                if isinstance(reported_step, int):
                    current_step = max(current_step, reported_step, step_events)
                else:
                    current_step = max(current_step, step_events)
            elif event_type == "tool_call":
                tool_calls += 1

        return {
            "current_step": current_step,
            "total_steps": current_step if current_step > 0 else 0,
            "tool_calls": tool_calls,
        }

    def _calculate_duration(self, meta: Dict[str, Any], events: List[Dict[str, Any]]) -> int:
        """计算运行时长（毫秒）"""
        created_at = meta.get("created_at", 0)
        updated_at = meta.get("updated_at", 0)

        if created_at and updated_at:
            return int((updated_at - created_at) * 1000)

        # 从 events 估算
        if len(events) >= 2:
            first_time = events[0].get("timestamp", 0)
            last_time = events[-1].get("timestamp", 0)
            if first_time and last_time:
                return int((last_time - first_time) * 1000)

        return 0

    def get_execution_tree(
        self, user_id: str, session_id: str, host_events: Optional[List[Dict[str, Any]]] = None
    ) -> HostExecutionTree:
        """
        获取 Host Agent 执行树

        扫描 subagents/ 目录，组装执行树结构
        如果提供 host_events，从中提取 Task Call 信息来关联 Sub Agent
        """
        subagents_dir = self._get_subagents_dir(user_id, session_id)
        logger.debug("Scanning subagents_dir: %s", subagents_dir)
        logger.debug("subagents_dir exists: %s", subagents_dir.exists())

        # 解析 Host Agent 状态
        host_status = "idle"
        host_current_step = 0
        host_total_steps = 0
        host_step_events = 0

        if host_events:
            for event in host_events:
                event_type = event.get("type", "")
                if event_type == "step_begin":
                    host_step_events += 1
                    reported_step = event.get("step_n", 0)
                    if isinstance(reported_step, int):
                        host_current_step = max(
                            host_current_step,
                            reported_step,
                            host_step_events,
                        )
                    else:
                        host_current_step = max(host_current_step, host_step_events)
                elif event_type == "turn_begin":
                    host_status = "running"
                elif event_type == "turn_end":
                    host_status = "completed"
                elif event_type == "worker.lifecycle.changed":
                    if event.get("scope") == "host":
                        host_status = _normalize_execution_tree_status(
                            event.get("status"),
                            default=host_status,
                        )

        # 扫描 Sub Agents
        subagent_calls = []

        if subagents_dir.exists():
            agent_dirs = [d for d in subagents_dir.iterdir() if d.is_dir()]
            logger.debug("Found %s agent dirs in %s", len(agent_dirs), subagents_dir)

            for agent_dir in agent_dirs:
                agent_id = agent_dir.name
                meta_path = agent_dir / "meta.json"
                wire_path = agent_dir / "wire.jsonl"

                logger.debug("Checking agent: %s, meta exists: %s", agent_id, meta_path.exists())

                meta = self._parse_meta_json(meta_path)
                if not meta:
                    logger.warning("[DEBUG] No meta.json for agent: %s", agent_id)
                    continue

                events = self._parse_wire_jsonl(wire_path) if wire_path.exists() else []
                progress = self._calculate_progress(events)
                duration = self._calculate_duration(meta, events)
                ownership = self._build_ownership_projection(
                    session_id=session_id,
                    agent_id=agent_id,
                    meta=meta,
                )

                description = _normalize_optional_string(meta.get("description")) or ""
                display_name = description or ownership.subagent_type

                subagent_call = {
                    "tool_call_id": ownership.parent_tool_call_id or "",  # 关联的 Task Call
                    "parent_tool_call_id": ownership.parent_tool_call_id,
                    "step_number": 0,  # 暂时无法知道，需要从 host_events 匹配
                    "subagent": {
                        "id": ownership.agent_id,
                        "agent_id": ownership.agent_id,
                        "name": display_name,
                        "description": description,
                        "subagent_type": ownership.subagent_type,
                        "status": _normalize_execution_tree_status(
                            meta.get("status"),
                            default="idle",
                        ),
                        "host_session_id": ownership.host_session_id,
                        "parent_tool_call_id": ownership.parent_tool_call_id,
                        "parent_agent_id": _normalize_optional_string(meta.get("parent_agent_id")),
                        "agent_path": _normalize_optional_string(meta.get("agent_path")),
                        "depth": meta.get("depth") if isinstance(meta.get("depth"), int) else 0,
                        "nickname": _normalize_optional_string(meta.get("nickname")),
                        "node_role": "collaboration_node",
                        "hosting_controller": False,
                        "ownership": self._serialize_ownership_projection(ownership),
                        "progress": progress,
                        "duration_ms": duration,
                        "created_at": (
                            datetime.fromtimestamp(meta.get("created_at", 0)).isoformat()
                            if meta.get("created_at")
                            else None
                        ),
                        "updated_at": (
                            datetime.fromtimestamp(meta.get("updated_at", 0)).isoformat()
                            if meta.get("updated_at")
                            else None
                        ),
                    },
                }
                subagent_calls.append(subagent_call)
                logger.debug("Added subagent call: %s, name: %s", agent_id, display_name)

        # 按创建时间排序
        subagent_calls.sort(key=lambda x: x["subagent"].get("created_at", ""), reverse=False)

        # 尝试从 host_events 匹配 step_number
        if host_events:
            step_number_map = {}
            current_step = 0
            step_events = 0
            for _i, event in enumerate(host_events):
                if event.get("type") == "step_begin":
                    step_events += 1
                    reported_step = event.get("step_n", current_step)
                    if isinstance(reported_step, int):
                        current_step = max(current_step, reported_step, step_events)
                    else:
                        current_step = max(current_step, step_events)
                elif event.get("type") == "tool_call":
                    tool_call_id = event.get("tool_call_id", "")
                    if tool_call_id:
                        step_number_map[tool_call_id] = current_step

            for call in subagent_calls:
                task_id = call.get("tool_call_id", "")
                if task_id in step_number_map:
                    call["step_number"] = step_number_map[task_id]
                    call["subagent"]["triggered_by_step"] = step_number_map[task_id]

        for index, call in enumerate(subagent_calls):
            if call.get("step_number", 0) > 0:
                continue
            fallback_step = index + 1
            call["step_number"] = fallback_step
            call["subagent"]["triggered_by_step"] = fallback_step

        # 计算 Host Agent 的步骤：
        # 1. 如果有 step_begin 事件，使用事件中的 step_n
        # 2. 否则，如果有 Sub Agents，用 Sub Agents 数量作为步骤近似
        # 3. 最后保底使用默认值
        if host_current_step == 0 and subagent_calls:
            # 从 Sub Agents 推断步骤：已完成的 Sub Agent 数量作为当前步骤
            completed_subagents = sum(
                1
                for call in subagent_calls
                if call.get("subagent", {}).get("status") in ["completed", "failed"]
            )
            host_current_step = completed_subagents
            host_total_steps = len(subagent_calls)

        # 如果仍然没有 total_steps，使用当前步骤或默认值
        if host_total_steps == 0:
            host_total_steps = max(host_current_step, 1)

        return HostExecutionTree(
            host_status=host_status,
            host_current_step=host_current_step,
            host_total_steps=host_total_steps,
            subagent_calls=subagent_calls,
        )

    def _get_subagent_workspace_dir(self, user_id: str, session_id: str, agent_id: str) -> Path:
        """获取 Sub Agent 工作区目录

        Worker 工作区: workspaces/{user_id}/{session_id}/.aiasys/session/{session_id}/subagents/{agent_id}/work/
        """
        return _get_session_subagents_dir(user_id, session_id) / agent_id / "work"

    def get_subagent_detail(
        self, user_id: str, session_id: str, agent_id: str
    ) -> Optional[SubAgentDetail]:
        """获取 Sub Agent 完整详情"""
        # Sub Agent 元数据目录（在 .aiasys/session 下）
        agent_dir = self._get_subagents_dir(user_id, session_id) / agent_id

        if not agent_dir.exists():
            return None

        meta_path = agent_dir / "meta.json"
        wire_path = agent_dir / "wire.jsonl"
        context_path = agent_dir / "context.jsonl"

        meta = self._parse_meta_json(meta_path)
        if not meta:
            return None

        events = self._parse_wire_jsonl(wire_path) if wire_path.exists() else []
        context = self._parse_context_jsonl(context_path) if context_path.exists() else []

        # 获取 Worker 工作区的文件（而不是 output 目录）
        workspace_dir = self._get_subagent_workspace_dir(user_id, session_id, agent_id)
        output_files = self._get_subagent_workspace_files(workspace_dir)
        ownership = self._build_ownership_projection(
            session_id=session_id,
            agent_id=agent_id,
            meta=meta,
        )
        description = _normalize_optional_string(meta.get("description")) or ""
        display_name = description or ownership.subagent_type
        duration = self._calculate_duration(meta, events)

        return SubAgentDetail(
            id=ownership.agent_id,
            name=display_name,
            status=_normalize_execution_tree_status(meta.get("status"), default="idle"),
            description=description,
            ownership=ownership,
            duration_ms=duration,
            created_at=(
                datetime.fromtimestamp(meta.get("created_at", 0)).isoformat()
                if meta.get("created_at")
                else None
            ),
            updated_at=(
                datetime.fromtimestamp(meta.get("updated_at", 0)).isoformat()
                if meta.get("updated_at")
                else None
            ),
            meta=meta,
            events=events,
            context=context,
            output_files=output_files,
        )

    def list_subagents(self, user_id: str, session_id: str) -> List[SubAgentSummary]:
        """列出所有 Sub Agent 摘要"""
        subagents_dir = self._get_subagents_dir(user_id, session_id)
        summaries = []

        if not subagents_dir.exists():
            return summaries

        for agent_dir in subagents_dir.iterdir():
            if not agent_dir.is_dir():
                continue

            agent_id = agent_dir.name
            meta = self._parse_meta_json(agent_dir / "meta.json")
            if not meta:
                continue

            events = self._parse_wire_jsonl(agent_dir / "wire.jsonl")
            progress = self._calculate_progress(events)
            duration = self._calculate_duration(meta, events)
            ownership = self._build_ownership_projection(
                session_id=session_id,
                agent_id=agent_id,
                meta=meta,
            )
            description = _normalize_optional_string(meta.get("description")) or ""
            display_name = description or ownership.subagent_type

            summaries.append(
                SubAgentSummary(
                    id=ownership.agent_id,
                    name=display_name,
                    status=_normalize_execution_tree_status(meta.get("status"), default="idle"),
                    description=description,
                    ownership=ownership,
                    progress=progress,
                    duration_ms=duration,
                    created_at=(
                        datetime.fromtimestamp(meta.get("created_at", 0)).isoformat()
                        if meta.get("created_at")
                        else None
                    ),
                    updated_at=(
                        datetime.fromtimestamp(meta.get("updated_at", 0)).isoformat()
                        if meta.get("updated_at")
                        else None
                    ),
                    task_tool_call_id=ownership.parent_tool_call_id or "",
                )
            )

        return summaries


# 全局服务实例
_subagent_tracking_service: Optional[SubAgentTrackingService] = None


def get_subagent_tracking_service() -> SubAgentTrackingService:
    """获取 SubAgent 跟踪服务实例"""
    global _subagent_tracking_service
    if _subagent_tracking_service is None:
        _subagent_tracking_service = SubAgentTrackingService()
    return _subagent_tracking_service
