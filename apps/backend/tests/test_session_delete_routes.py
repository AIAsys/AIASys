from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from fastapi import BackgroundTasks

from app.api.routes import sessions as sessions_module
from app.api.routes.sessions_branches import delete_session
from app.core.config import WORKSPACE_DIR
from app.models.user import UserInfo


TEST_USER_ID = "session_delete_test_user"
TEST_SESSION_ID = "session_delete_test_session"

CURRENT_USER = UserInfo(
    user_id=TEST_USER_ID,
    role="admin",
    auth_provider="none",
)


def test_delete_session_detaches_directory_before_background_cleanup(monkeypatch) -> None:
    user_dir = WORKSPACE_DIR / TEST_USER_ID
    session_dir = user_dir / TEST_SESSION_ID
    trash_dir = WORKSPACE_DIR / ".trash" / TEST_USER_ID
    original_stop_session = sessions_module.agent_service.stop_session

    stop_calls: list[tuple[str, str]] = []

    async def fake_stop_session(user_id: str, session_id: str) -> None:
        stop_calls.append((user_id, session_id))

    shutil.rmtree(user_dir, ignore_errors=True)
    shutil.rmtree(trash_dir, ignore_errors=True)

    try:
        sessions_module.session_manager.create_session(
            session_id=TEST_SESSION_ID,
            user_id=TEST_USER_ID,
            title="删除测试",
            sandbox_mode="local",
        )
        (session_dir / "report.md").write_text("# report\n", encoding="utf-8")

        sessions_module.agent_service.stop_session = fake_stop_session

        background_tasks = BackgroundTasks()
        response = asyncio.run(
            delete_session(
                TEST_USER_ID,
                TEST_SESSION_ID,
                background_tasks,
                CURRENT_USER,
            )
        )

        assert response["success"] is True
        assert stop_calls == [(TEST_USER_ID, TEST_SESSION_ID)]
        assert not session_dir.exists()

        detached_dirs = sorted(trash_dir.glob(f"{TEST_SESSION_ID}-*"))
        assert len(detached_dirs) == 1
        assert detached_dirs[0].exists()

        sessions = sessions_module.session_manager.list_user_sessions(TEST_USER_ID, include_drafts=True)
        assert all(item["session_id"] != TEST_SESSION_ID for item in sessions)

        assert len(background_tasks.tasks) == 1
        assert sessions_module.session_manager.purge_detached_session(detached_dirs[0]) is True
        assert not detached_dirs[0].exists()
    finally:
        sessions_module.agent_service.stop_session = original_stop_session
        shutil.rmtree(user_dir, ignore_errors=True)
        shutil.rmtree(trash_dir, ignore_errors=True)
