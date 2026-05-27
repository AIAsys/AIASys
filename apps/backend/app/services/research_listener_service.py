"""研究事件监听服务的空实现。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ResearchListenerContext:
    user_id: str = ""
    workspace_id: str = ""
    workspace_root: Path | None = None
    session_id: str = ""
    session_source: str | None = None
    automation_continuation_id: str | None = None
    automation_continuation_target_kind: str | None = None


class _StubListenerService:
    def build_context(self, **kwargs) -> None:
        return None

    def append_session_started(self, **kwargs) -> bool:
        return False

    def append_worker_lifecycle_event(self, **kwargs) -> bool:
        return False

    def append_host_completed_fallback(self, **kwargs) -> bool:
        return False


_service = _StubListenerService()


def get_research_listener_service() -> _StubListenerService:
    return _service
