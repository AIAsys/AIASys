"""自动任务信号工具。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.models.session import AutoTaskSignal, SessionMetadata

logger = logging.getLogger(__name__)


def _metadata_path(session_root: Path) -> Path:
    return session_root / "metadata.json"


def _load_metadata(session_root: Path) -> tuple[SessionMetadata | None, Path]:
    meta_path = _metadata_path(session_root)
    if not meta_path.exists():
        return None, meta_path
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return SessionMetadata(**data), meta_path
    except Exception:
        logger.warning("读取 metadata.json 失败: %s", meta_path, exc_info=True)
        return None, meta_path


def _save_metadata(meta_path: Path, metadata: SessionMetadata) -> None:
    meta_path.write_text(
        metadata.model_dump_json(indent=2),
        encoding="utf-8",
    )


class AutoTaskSignal(AiasysTool):
    """连续自动任务写回完成或暂停状态。"""

    name = "auto_task_signal"
    description = (
        "向当前连续自动任务写回完成或暂停信号。"
        "自动任务目标已完全达成时调用 action=complete；"
        "需要用户介入或无法继续时调用 action=pause。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get", "complete", "pause"],
                "description": "get 读取当前信号，complete 标记完成，pause 标记暂停",
            },
            "reason": {
                "type": "string",
                "description": "完成或暂停原因，可选",
            },
        },
        "required": ["action"],
    }

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        ctx = ctx or {}
        action = str(kwargs.get("action") or "").strip().lower()
        if action not in {"get", "complete", "pause"}:
            return ToolResult(
                content="action 只支持 get / complete / pause",
                is_error=True,
            )

        session_root = Path(str(ctx.get("session_root") or "."))
        metadata, meta_path = _load_metadata(session_root)
        if metadata is None:
            return ToolResult(content="无法读取会话元数据", is_error=True)

        signal = metadata.auto_task_signal
        if signal is None:
            return ToolResult(
                content=json.dumps(
                    {"auto_task_signal": None, "message": "当前会话没有自动任务信号"},
                    ensure_ascii=False,
                ),
                is_error=action != "get",
            )

        if action == "get":
            return ToolResult(
                content=json.dumps(
                    {"auto_task_signal": signal.model_dump(mode="json")},
                    ensure_ascii=False,
                )
            )

        next_status = "completed" if action == "complete" else "paused"
        metadata.auto_task_signal = AutoTaskSignal(
            auto_task_id=signal.auto_task_id,
            status=next_status,
            reason=str(kwargs.get("reason") or "").strip() or None,
            created_at=signal.created_at,
            updated_at=datetime.now().isoformat(),
        )
        _save_metadata(meta_path, metadata)
        return ToolResult(
            content=json.dumps(
                {"auto_task_signal": metadata.auto_task_signal.model_dump(mode="json")},
                ensure_ascii=False,
            )
        )
