"""
子 Agent 文件系统存储管理。

自研 subagent 存储层，维护 meta.json / wire.jsonl / context.jsonl，
保持路径和格式与 SubAgentTrackingService 兼容。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from app.core.config import WORKSPACE_DIR

logger = logging.getLogger(__name__)


def _get_subagents_dir(user_id: str, session_id: str) -> Path:
    """获取 Sub Agents 存储目录。

    路径约定：workspaces/{user_id}/{session_id}/.aiasys/session/subagents/
    """
    return WORKSPACE_DIR / user_id / session_id / ".aiasys" / "session" / "subagents"


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """原子写入 JSON 文件（先写临时文件再重命名）。"""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


class SubAgentStorage:
    """子 Agent 存储管理器。

    负责创建和维护单个 subagent 的目录结构：
    subagents/{agent_id}/
        ├── meta.json      # 元数据（创建、状态、launch_spec）
        ├── wire.jsonl     # 实时执行事件流
        ├── context.jsonl  # OpenAI 格式对话历史
        └── work/          # 子 Agent 临时运行产物，不是独立工作区
    """

    def __init__(self, user_id: str, session_id: str, agent_id: str) -> None:
        self.user_id = user_id
        self.session_id = session_id
        self.agent_id = agent_id
        self._subagent_dir = _get_subagents_dir(user_id, session_id) / agent_id
        self._wire_file: Path | None = None
        self._context_file: Path | None = None
        self._meta_file: Path | None = None
        self._lock = asyncio.Lock()

    @property
    def subagent_dir(self) -> Path:
        return self._subagent_dir

    @property
    def work_dir(self) -> Path:
        return self._subagent_dir / "work"

    @property
    def meta_file(self) -> Path:
        if self._meta_file is None:
            self._meta_file = self._subagent_dir / "meta.json"
        return self._meta_file

    @property
    def wire_file(self) -> Path:
        if self._wire_file is None:
            self._wire_file = self._subagent_dir / "wire.jsonl"
        return self._wire_file

    @property
    def context_file(self) -> Path:
        if self._context_file is None:
            self._context_file = self._subagent_dir / "context.jsonl"
        return self._context_file

    def create_workspace(
        self,
        *,
        parent_tool_call_id: str,
        subagent_type: str,
        description: str = "",
        effective_model: str | None = None,
        model_override: str | None = None,
        host_session_id: str | None = None,
        parent_agent_id: str | None = None,
        agent_path: str | None = None,
        depth: int = 0,
        nickname: str | None = None,
    ) -> None:
        """创建子 Agent 运行实例目录并写入初始 meta.json。"""
        self._subagent_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)

        now = time.time()
        meta: dict[str, Any] = {
            "agent_id": self.agent_id,
            "subagent_type": subagent_type,
            "status": "running",
            "description": description,
            "host_session_id": host_session_id or self.session_id,
            "parent_agent_id": parent_agent_id,
            "agent_path": agent_path,
            "depth": depth,
            "nickname": nickname,
            "created_at": now,
            "updated_at": now,
            "last_task_id": parent_tool_call_id,
            "launch_spec": {
                "agent_id": self.agent_id,
                "subagent_type": subagent_type,
                "model_override": model_override,
                "effective_model": effective_model or "unknown",
                "host_session_id": host_session_id or self.session_id,
                "parent_agent_id": parent_agent_id,
                "agent_path": agent_path,
                "depth": depth,
                "nickname": nickname,
                "created_at": now,
            },
        }
        _atomic_write_json(self.meta_file, meta)
        self._upsert_instance_record(meta)

        # 初始化 wire.jsonl（写入 metadata 首行）
        self.wire_file.write_text(
            json.dumps({"type": "metadata", "protocol_version": "1.0"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        # 初始化空的 context.jsonl
        self.context_file.write_text("", encoding="utf-8")

        logger.info(
            "SubAgent workspace created: user=%s session=%s agent=%s task=%s",
            self.user_id,
            self.session_id,
            self.agent_id,
            parent_tool_call_id,
        )

    def update_status(self, status: str) -> None:
        """更新 meta.json 中的状态。"""
        try:
            meta = self.read_meta()
            if meta is None:
                return
            meta["status"] = status
            meta["updated_at"] = time.time()
            _atomic_write_json(self.meta_file, meta)
            self._upsert_instance_record(meta)
        except Exception:
            logger.warning("更新 subagent meta 状态失败: agent_id=%s", self.agent_id, exc_info=True)

    def read_meta(self) -> dict[str, Any] | None:
        """读取 meta.json。"""
        try:
            if not self.meta_file.exists():
                return None
            return json.loads(self.meta_file.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("读取 meta.json 失败: %s", self.meta_file, exc_info=True)
            return None

    def _upsert_instance_record(self, meta: dict[str, Any]) -> None:
        """把运行实例镜像到 SQLite，文件系统记录仍是兼容主线。"""
        try:
            from app.core.database import SubAgentInstanceORM, db_session, engine

            SubAgentInstanceORM.__table__.create(bind=engine, checkfirst=True)
            launch_spec = (
                meta.get("launch_spec") if isinstance(meta.get("launch_spec"), dict) else {}
            )
            with db_session() as db:
                try:
                    db.query(SubAgentInstanceORM).filter(
                        SubAgentInstanceORM.agent_id == self.agent_id
                    ).delete(synchronize_session=False)
                    db.add(
                        SubAgentInstanceORM(
                            agent_id=self.agent_id,
                            user_id=self.user_id,
                            workspace_id=meta.get("workspace_id"),
                            host_session_id=str(meta.get("host_session_id") or self.session_id),
                            parent_agent_id=meta.get("parent_agent_id"),
                            parent_tool_call_id=meta.get("last_task_id"),
                            subagent_type=str(meta.get("subagent_type") or "unknown"),
                            agent_path=meta.get("agent_path"),
                            depth=int(meta.get("depth") or 0),
                            status=str(meta.get("status") or "running"),
                            model=launch_spec.get("effective_model"),
                            nickname=meta.get("nickname"),
                            meta_info=meta,
                        )
                    )
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
        except Exception:
            logger.debug(
                "镜像子 Agent 实例到 SQLite 失败: agent_id=%s",
                self.agent_id,
                exc_info=True,
            )

    async def append_wire_event(
        self,
        message_type: str,
        payload: dict[str, Any],
        timestamp: float | None = None,
    ) -> None:
        """追加事件到 wire.jsonl。

        格式与 SubAgentTrackingService._parse_wire_jsonl 兼容：
        {"timestamp": <float>, "message": {"type": "<message_type>", "payload": {...}}}
        """
        ts = timestamp if timestamp is not None else time.time()
        record = {
            "timestamp": ts,
            "message": {"type": message_type, "payload": payload},
        }
        async with self._lock:
            try:
                with open(self.wire_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except Exception:
                logger.warning("追加 wire 事件失败: agent_id=%s", self.agent_id, exc_info=True)

    async def append_context_message(self, message: dict[str, Any]) -> None:
        """追加消息到 context.jsonl（OpenAI 格式）。"""
        async with self._lock:
            try:
                with open(self.context_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(message, ensure_ascii=False) + "\n")
            except Exception:
                logger.warning("追加 context 消息失败: agent_id=%s", self.agent_id, exc_info=True)

    async def append_wire_agent_runtime_event(
        self,
        event: dict[str, Any],
        timestamp: float | None = None,
    ) -> None:
        """将 AgentRuntimeEvent（已转为 dict）追加到 wire.jsonl。

        自动映射 AgentRuntimeEvent 的 kind 到 wire message type：
        - content(text)  -> ContentPart {type: "text", text: ...}
        - content(think) -> ContentPart {type: "think", think: ...}
        - tool_call      -> ToolCall {id, function: {name, arguments}}
        - tool_result    -> ToolResult {tool_call_id, return_value: {output, is_error}}
        - worker_lifecycle -> TurnEnd / StepInterrupted / StatusUpdate
        - token_usage    -> 跳过（不写入 wire）
        """
        kind = event.get("kind")
        ts = timestamp if timestamp is not None else time.time()

        if kind == "content":
            content_type = event.get("content_type")
            if content_type == "text" and event.get("text"):
                await self.append_wire_event(
                    "ContentPart",
                    {"type": "text", "text": event["text"]},
                    ts,
                )
            elif content_type == "think" and event.get("think"):
                await self.append_wire_event(
                    "ContentPart",
                    {"type": "think", "think": event["think"]},
                    ts,
                )

        elif kind == "tool_call":
            await self.append_wire_event(
                "ToolCall",
                {
                    "id": event.get("tool_call_id"),
                    "function": {
                        "name": event.get("tool_name"),
                        "arguments": json.dumps(event.get("arguments") or {}),
                    },
                },
                ts,
            )

        elif kind == "tool_result":
            return_value: dict[str, Any] = {"output": event.get("content", "")}
            if event.get("is_error"):
                return_value["is_error"] = True
                return_value["message"] = event.get("content", "")
            await self.append_wire_event(
                "ToolResult",
                {
                    "tool_call_id": event.get("tool_call_id"),
                    "return_value": return_value,
                },
                ts,
            )

        elif kind == "worker_lifecycle":
            status = event.get("status")
            if status == "finished":
                await self.append_wire_event("TurnEnd", {}, ts)
            elif status == "interrupted":
                await self.append_wire_event(
                    "StepInterrupted", {"reason": event.get("reason", "")}, ts
                )
            elif status in ("cancelled", "failed"):
                await self.append_wire_event("StatusUpdate", {"status": status}, ts)

        # token_usage / task_call_begin / task_call_end / data 不写入 wire
