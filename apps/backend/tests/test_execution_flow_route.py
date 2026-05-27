from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from app.core.workspace_path import WorkspacePath

from app.api.routes import agent as agent_route
from app.models.user import UserInfo


class _FakeJournal:
    def __init__(self, session_dir: Path, session_id: str):
        assert isinstance(session_dir, Path)
        self.session_dir = session_dir
        self.session_id = session_id
        self.stdout_dir = session_dir / ".aiasys" / "session" / "execution" / "artifacts" / "stdout"
        self.stderr_dir = session_dir / ".aiasys" / "session" / "execution" / "artifacts" / "stderr"

    def has_structure(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_execution_flow_route_converts_kaospath_for_journal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir(parents=True, exist_ok=True)
    work_dir = WorkspacePath.from_local_path(workspace_path)

    monkeypatch.setattr(
        "app.services.agent.get_work_dir",
        lambda user_id, session_id: work_dir,
    )
    monkeypatch.setattr(
        "app.services.history.SessionExecutionJournal",
        _FakeJournal,
    )

    current_user = UserInfo(
        user_id="local_default",
        role="admin",
        auth_provider="local",
    )

    result = await agent_route.get_execution_flow(
        user_id="local_default",
        session_id="session-1",
        current_user=current_user,
    )

    assert result == {"history": []}
