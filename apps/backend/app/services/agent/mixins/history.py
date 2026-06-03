"""
历史记录 Mixin

负责会话历史、执行事件和会话列表查询
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

from app.core.config import WORKSPACE_DIR
from app.services.agent.utils import get_work_dir
from app.services.history import (
    apply_display_content_to_history,
    load_display_history_entries,
)

if TYPE_CHECKING:
    from app.services.agent import AgentService

logger = logging.getLogger(__name__)


def _load_host_turn_reasoning_chunks(session_dir: Path) -> list[dict[str, Any]]:
    wire_file = session_dir / "wire.jsonl"
    if not wire_file.exists():
        return []

    turns: list[dict[str, Any]] = []
    current_parts: list[str] = []
    current_started_at: float | None = None
    current_ended_at: float | None = None

    def append_current_turn() -> None:
        text = "".join(current_parts)
        if not text.strip():
            return
        turns.append(
            {
                "text": text,
                "started_at": current_started_at,
                "ended_at": current_ended_at or current_started_at,
            }
        )

    try:
        with open(wire_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue

                event_type = event.get("type")
                event_timestamp = event.get("timestamp")
                numeric_timestamp = (
                    float(event_timestamp) if isinstance(event_timestamp, (int, float)) else None
                )
                if event_type == "turn_begin":
                    if current_parts:
                        append_current_turn()
                    current_parts = []
                    current_started_at = numeric_timestamp
                    current_ended_at = numeric_timestamp
                    continue

                if (
                    event_type == "content"
                    and event.get("content_type") == "think"
                    and isinstance(event.get("think"), str)
                ):
                    current_parts.append(event["think"])
                    current_ended_at = numeric_timestamp or current_ended_at
                    continue

                if event_type == "turn_end":
                    current_ended_at = numeric_timestamp or current_ended_at
                    if current_parts:
                        append_current_turn()
                    current_parts = []
                    current_started_at = None
                    current_ended_at = None

        if current_parts:
            append_current_turn()
        return turns
    except Exception as exc:
        logger.warning("读取 host wire 推理内容失败: path=%s error=%s", wire_file, exc)
        return []


def _parse_history_timestamp(value: Any) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _select_reasoning_turn_index(
    reasoning_turns: list[dict[str, Any]],
    used_indices: set[int],
    message_timestamp: float | None,
) -> int | None:
    if message_timestamp is None:
        for index in range(len(reasoning_turns)):
            if index not in used_indices:
                return index
        return None

    best_index: int | None = None
    best_distance: float | None = None
    for index, turn in enumerate(reasoning_turns):
        if index in used_indices:
            continue
        ended_at = turn.get("ended_at")
        if not isinstance(ended_at, (int, float)):
            continue
        distance = message_timestamp - float(ended_at)
        if distance < -5 or distance > 120:
            continue
        if best_distance is None or abs(distance) < best_distance:
            best_index = index
            best_distance = abs(distance)
    return best_index


def _is_empty_assistant_message(msg: Dict[str, Any]) -> bool:
    """判断 assistant 消息是否没有实质展示内容（无 text、无 reasoning、无 tool_calls）。

    注意：tool_calls-only 的消息（无 text、无 reasoning）也被视为"空"，
    因为 tool_calls 的展示应该合并到相邻的有内容 turn 中，而不是单独生成空白分隔线。
    """
    if msg.get("role") != "assistant":
        return False
    content = msg.get("content")
    has_text = bool(content) and (
        (isinstance(content, str) and content.strip())
        or (isinstance(content, list) and any(
            (item.get("text") or "").strip() for item in content
        ))
    )
    has_reasoning = bool(msg.get("reasoning_content", "").strip())
    # tool_calls-only 的消息也被视为空（从展示角度）
    return not has_text and not has_reasoning


def _merge_empty_assistant_messages(
    history: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """合并连续的空白 assistant 消息到相邻的有内容消息中。

    策略：遍历消息列表，当遇到空 assistant 消息时，将其 tool_calls（如有）
    合并到前一个或后一个有内容的 assistant 消息中，自身被丢弃。
    这避免了前端历史恢复时为无实质内容的 ReAct 轮次生成空白 Turn 分隔线。
    """
    merged: List[Dict[str, Any]] = []
    pending_empty: List[Dict[str, Any]] = []

    def _flush_pending() -> None:
        nonlocal merged
        if not pending_empty:
            return
        # 尝试把 pending_empty 的 tool_calls 合并到最后一个非空 assistant
        tool_calls_to_merge: List[Dict[str, Any]] = []
        for m in pending_empty:
            if m.get("tool_calls"):
                tool_calls_to_merge.extend(m["tool_calls"])
        if tool_calls_to_merge:
            for i in range(len(merged) - 1, -1, -1):
                if merged[i].get("role") == "assistant":
                    existing = merged[i].get("tool_calls") or []
                    merged[i]["tool_calls"] = existing + tool_calls_to_merge
                    break
        pending_empty.clear()

    for msg in history:
        if _is_empty_assistant_message(msg):
            pending_empty.append(dict(msg))
            continue

        _flush_pending()

        if msg.get("role") == "assistant" and pending_empty:
            # 不应该走到这里，因为上面已经 continue 了
            pending_empty.clear()

        merged.append(dict(msg))

    _flush_pending()
    return merged


def _backfill_reasoning_content_from_wire(
    history: List[Dict[str, Any]],
    session_dir: Path,
) -> List[Dict[str, Any]]:
    reasoning_turns = _load_host_turn_reasoning_chunks(session_dir)
    if not reasoning_turns:
        return history

    hydrated: List[Dict[str, Any]] = []
    used_reasoning_indices: set[int] = set()
    for message in history:
        if message.get("role") != "assistant":
            hydrated.append(message)
            continue

        message_timestamp = _parse_history_timestamp(message.get("timestamp"))
        reasoning_index = _select_reasoning_turn_index(
            reasoning_turns,
            used_reasoning_indices,
            message_timestamp,
        )
        if not message.get("reasoning_content") and reasoning_index is not None:
            updated_message = dict(message)
            updated_message["reasoning_content"] = reasoning_turns[reasoning_index]["text"]
            hydrated.append(updated_message)
            used_reasoning_indices.add(reasoning_index)
            continue

        if message.get("reasoning_content") and reasoning_index is not None:
            used_reasoning_indices.add(reasoning_index)
        hydrated.append(message)

    return hydrated


class HistoryMixin:
    """历史记录功能"""

    async def get_session_history(
        self: "AgentService", user_id: str, session_id: str, limit: int = 0
    ) -> List[Dict[str, Any]]:
        """
        获取会话历史记录

        存储位置:
        - SDK 原始历史: workspaces/{user_id}/{session_id}/.aiasys/session/{session_id}/context.jsonl
        - UI 展示历史: workspaces/{user_id}/{session_id}/.aiasys/session/{session_id}/display_history.jsonl

        Args:
            limit: 限制返回最近 N 条消息，0 表示不限制。
                   实现方式为从文件尾部读取，避免全量加载大文件。
        """
        try:
            work_dir = get_work_dir(user_id, session_id)
            # 使用标准 Path 而不是 WorkspacePath，避免异步 exists() 问题
            from pathlib import Path as StdPath

            session_file = (
                StdPath(str(work_dir)) / ".aiasys" / "session" / session_id / "context.jsonl"
            )
            session_dir = session_file.parent

            history = []
            if session_file.exists():
                if limit > 0:
                    # 从文件尾部读取最近 N 条有效消息，避免全量解析
                    history = self._read_history_tail(session_file, limit)
                else:
                    with open(session_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    msg = json.loads(line)
                                    # 过滤内部 SDK 消息和 system-reminder 消息
                                    if msg.get("role") in ("_checkpoint", "_usage", "_system_prompt"):
                                        continue
                                    # 内联 system-reminder 检测，避免依赖 EventsMixin
                                    if (
                                        msg.get("role") == "user"
                                        and isinstance(msg.get("content"), str)
                                        and msg.get("content", "").strip().startswith("<system-reminder>")
                                    ):
                                        continue
                                    history.append(msg)
                                except json.JSONDecodeError:
                                    continue
            display_entries = load_display_history_entries(StdPath(str(work_dir)), session_id)
            if history:
                # 先合并连续的空白 assistant 消息，避免前端生成空白 Turn 分隔线
                history = _merge_empty_assistant_messages(history)
                hydrated_history = apply_display_content_to_history(
                    history,
                    display_entries,
                    allow_older_orphan_entries=False,
                )
                return _backfill_reasoning_content_from_wire(
                    hydrated_history,
                    session_dir,
                )

            return []
        except Exception as e:
            logger.error(f"读取会话历史失败: {e}")
            return []

    def _read_history_tail(
        self: "AgentService", session_file: Path, limit: int
    ) -> List[Dict[str, Any]]:
        """从 context.jsonl 尾部读取最近 limit 条有效消息。"""
        import mmap

        def _should_skip(msg: dict) -> bool:
            """过滤内部 SDK 消息和 system-reminder 消息。"""
            if msg.get("role") in ("_checkpoint", "_usage", "_system_prompt"):
                return True
            if msg.get("role") == "user":
                content = msg.get("content")
                if isinstance(content, str) and content.strip().startswith("<system-reminder>"):
                    return True
            return False

        history: List[Dict[str, Any]] = []
        try:
            with open(session_file, "r+b") as f:
                try:
                    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                except (ValueError, OSError):
                    # 空文件或无法 mmap，回退到普通读取
                    f.seek(0)
                    lines = f.readlines()
                    for line in reversed(lines):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = json.loads(line)
                            if _should_skip(msg):
                                continue
                            history.insert(0, msg)
                            if len(history) >= limit:
                                break
                        except json.JSONDecodeError:
                            continue
                    return history

                # 从文件末尾向前扫描，找到最近的 limit 条有效消息
                file_size = mm.size()
                pos = file_size
                line_buffer = bytearray()

                while pos > 0 and len(history) < limit:
                    pos -= 1
                    byte = mm[pos]
                    if byte == ord(b"\n"):
                        if line_buffer:
                            line = line_buffer[::-1].decode("utf-8", errors="replace").strip()
                            if line:
                                try:
                                    msg = json.loads(line)
                                    if not _should_skip(msg):
                                        history.insert(0, msg)
                                except json.JSONDecodeError:
                                    pass
                            line_buffer = bytearray()
                    else:
                        line_buffer.append(byte)

                # 处理最后一行（文件开头没有换行符的情况）
                if line_buffer and len(history) < limit:
                    line = line_buffer[::-1].decode("utf-8", errors="replace").strip()
                    if line:
                        try:
                            msg = json.loads(line)
                            if not _should_skip(msg):
                                history.insert(0, msg)
                        except json.JSONDecodeError:
                            pass

                mm.close()
        except Exception as e:
            logger.warning(f"尾部读取历史失败，回退到全量读取: {e}")
            # 回退到普通读取
            with open(session_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            msg = json.loads(line)
                            if _should_skip(msg):
                                continue
                            history.append(msg)
                        except json.JSONDecodeError:
                            continue
                if len(history) > limit:
                    history = history[-limit:]
        return history

    async def get_session_execution_events(
        self: "AgentService", user_id: str, session_id: str
    ) -> List[Dict[str, Any]]:
        """
        获取会话执行事件流（wire.jsonl）

        用于构建执行树和展示 Host Agent 的执行步骤
        """
        try:
            work_dir = get_work_dir(user_id, session_id)
            from pathlib import Path as StdPath

            # 尝试读取 wire.jsonl（如果存在）
            wire_file = StdPath(str(work_dir)) / ".aiasys" / "session" / session_id / "wire.jsonl"

            events = []
            if wire_file.exists():
                with open(wire_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                event = json.loads(line)
                                events.append(event)
                            except json.JSONDecodeError:
                                continue
                return events

            # 如果 wire.jsonl 不存在，尝试从 active session 获取
            from app.services.agent.utils import get_session_key

            session_key = get_session_key(user_id, session_id)
            session = self._active_sessions.get(session_key)

            if session:
                # 从 session 的 wire 记录中获取
                # 注意：当前实现中 wire 记录可能不完整，需要后续增强
                logger.debug(f"从 active session 获取事件: {session_key}")
                return []

            return []
        except Exception as e:
            logger.error(f"读取执行事件失败: {e}")
            return []

    def list_user_sessions(self: "AgentService", user_id: str) -> List[Dict[str, Any]]:
        """列出用户的所有可恢复会话"""
        sessions = []
        try:
            user_dir = WORKSPACE_DIR / user_id
            if user_dir.exists():
                for session_dir in user_dir.iterdir():
                    if session_dir.is_dir():
                        session_id = session_dir.name
                        meta_path = session_dir / "metadata.json"
                        if not meta_path.exists():
                            continue

                        # 读取 title 和 time_str
                        title = session_id
                        time_str = ""
                        if meta_path.exists():
                            try:
                                data = json.loads(meta_path.read_text(encoding="utf-8"))
                                title = data.get("title", session_id)
                                time_str = data.get("updated_at") or data.get("created_at") or ""
                            except Exception:
                                pass

                        if not time_str:
                            st_mtime = session_dir.stat().st_mtime
                            time_str = datetime.fromtimestamp(st_mtime).isoformat()

                        # 统计可见工作区文件数量
                        file_count = 0
                        seen_paths: set[str] = set()

                        for f in session_dir.rglob("*"):
                            if not f.is_file():
                                continue

                            relative_path = f.relative_to(session_dir).as_posix()
                            if relative_path.split("/", 1)[0] in {
                                "workspace",
                                ".aiasys",
                            }:
                                continue
                            if f.name.startswith("."):
                                continue
                            if f.name in {"metadata.json", "file_snapshots.json"}:
                                continue

                            seen_paths.add(relative_path)
                            file_count += 1

                        workspace_dir = session_dir / "workspace"
                        if workspace_dir.exists() and workspace_dir.is_dir():
                            for f in workspace_dir.rglob("*"):
                                if not f.is_file():
                                    continue

                                relative_path = f.relative_to(workspace_dir).as_posix()
                                if relative_path in seen_paths:
                                    continue
                                if f.name.startswith("."):
                                    continue
                                if f.name in {"metadata.json", "file_snapshots.json"}:
                                    continue

                                seen_paths.add(relative_path)
                                file_count += 1

                        sessions.append(
                            {
                                "user_id": user_id,
                                "session_id": session_id,
                                "workspace_id": (
                                    self.workspace_registry.find_workspace_id_by_session_id(
                                        user_id, session_id
                                    )
                                    if hasattr(self, "workspace_registry")
                                    else None
                                ),
                                "title": title,
                                "workspace_file_count": file_count,
                                "updated_at": time_str,
                                "created_at": time_str,
                            }
                        )
                # 按时间倒序排列
                sessions.sort(key=lambda x: x["updated_at"], reverse=True)
        except Exception as e:
            logger.error(f"列出会话失败: {e}")
        return sessions

    def list_all_sessions(self: "AgentService") -> List[Dict[str, Any]]:
        """列出所有可恢复会话（所有用户）"""
        sessions = []
        try:
            if WORKSPACE_DIR.exists():
                for user_dir in WORKSPACE_DIR.iterdir():
                    if user_dir.name.startswith(".") or not user_dir.is_dir():
                        continue
                    sessions.extend(self.list_user_sessions(user_dir.name))
        except Exception as e:
            logger.error(f"列出所有会话失败: {e}")
        return sessions

    def get_storage_info(self: "AgentService") -> Dict[str, Any]:
        """获取存储信息"""
        return {
            "workspace_dir": str(WORKSPACE_DIR),
            "storage_pattern": "workspaces/{user_id}/{session_id}/",
            "session_storage": "workspaces/{user_id}/{session_id}/.aiasys/session/",
            "file_storage": "workspaces/{user_id}/{session_id}/",
            "active_sessions": len(self._active_sessions),
            "active_locks": len(self._session_locks),
        }
