from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.services.agent.mixins import context as context_module
from app.services.runtime import session_runtime_state as runtime_state_module


def test_build_session_runtime_summary_reports_not_started_uv_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        runtime_state_module,
        "_resolve_workspace_runtime_env",
        lambda **kwargs: ("ws-1", {
            "kind": "uv",
            "status": "registered",
            "display_name": "Workspace UV",
        }),
    )

    summary = runtime_state_module.build_session_runtime_summary(
        session_dir=tmp_path,
        session_id="session-1",
        user_id="user-1",
        sandbox_mode="local",
        env_id="workspace-default",
        last_runtime_state="fresh",
        runtime_busy=False,
    )

    assert summary["runtime_kind"] == "uv"
    assert summary["status"] == "registered"
    assert summary["status_label"] == "已登记"
    assert summary["kernel_active"] is False


def test_runtime_prompt_context_explains_uv_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        runtime_state_module,
        "_resolve_workspace_runtime_env",
        lambda **kwargs: ("ws-1", {
            "kind": "uv",
            "status": "ready",
            "display_name": "Workspace UV",
        }),
    )

    summary = runtime_state_module.build_session_runtime_summary(
        session_dir=tmp_path,
        session_id="session-2",
        user_id="user-2",
        sandbox_mode="local",
        env_id="workspace-default",
        last_runtime_state="available",
        runtime_busy=False,
    )
    prompt_context = runtime_state_module.format_runtime_summary_for_prompt(summary)

    assert "Shell 和代码工具会使用工作区 UV 环境" in prompt_context
    assert "当前执行环境: Workspace UV" in prompt_context


def test_runtime_prompt_context_explains_missing_python_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        runtime_state_module,
        "_resolve_workspace_runtime_env",
        lambda **kwargs: (None, None),
    )

    summary = runtime_state_module.build_session_runtime_summary(
        session_dir=tmp_path,
        session_id="session-plain",
        user_id="user-plain",
        sandbox_mode=None,
        env_id=None,
        last_runtime_state="fresh",
        runtime_busy=False,
        workspace_id="ws-plain",
    )
    prompt_context = runtime_state_module.format_runtime_summary_for_prompt(summary)

    assert summary["runtime_kind"] == "plain_shell"
    assert summary["env_id"] is None
    assert "当前任务未绑定 Python/UV 环境" in prompt_context
    assert "不会自动进入 UV 环境或创建虚拟环境" in prompt_context
    assert "Shell 和代码工具会使用工作区 UV 环境" not in prompt_context


def test_runtime_prompt_context_includes_workspace_and_session_identity() -> None:
    prompt_context = runtime_state_module.format_runtime_summary_for_prompt(
        {
            "display_name": "本地 Python",
            "status_label": "尚未使用",
            "runtime_kind": runtime_state_module.LOCAL_RUNTIME_KIND,
            "kernel_active": False,
            "runtime_busy": False,
            "workspace_id": "workspace-123",
            "session_id": "session-456",
        }
    )

    assert "当前工作区 ID: workspace-123" in prompt_context
    assert "当前会话 session_id: session-456" in prompt_context


@pytest.mark.asyncio
async def test_cleanup_session_resources_shuts_down_local_runtime_when_requested(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: dict[str, object] = {}

    class FakeAgentService(context_module.ContextMixin):
        def __init__(self) -> None:
            self._active_sessions = {"user-1/session-1": object()}
            self._locks_lock = asyncio.Lock()
            self._session_locks = {"user-1/session-1": asyncio.Lock()}

    class FakeAskUserStore:
        def cancel_by_session(self, *, session_id: str, user_id: str) -> None:
            calls["cancel_by_session"] = (session_id, user_id)

    class FakeJournal:
        def __init__(self, session_dir: Path, session_id: str) -> None:
            calls["journal_init"] = (session_dir, session_id)

        def update_recovery_config(self, **kwargs: object) -> None:
            calls["journal_update"] = kwargs

    monkeypatch.setattr(context_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(context_module, "AskUserStore", FakeAskUserStore)
    monkeypatch.setattr(
        context_module.AskUser,
        "clear_event_sender",
        staticmethod(lambda session_id: calls.setdefault("clear_event_sender", session_id)),
    )
    monkeypatch.setattr(context_module, "SessionExecutionJournal", FakeJournal)

    from app.agents.tools.local_ipython_box import LocalIPythonBox

    monkeypatch.setattr(
        LocalIPythonBox,
        "has_kernel",
        staticmethod(lambda session_id, user_id="default": True),
    )
    monkeypatch.setattr(
        LocalIPythonBox,
        "shutdown_kernel",
        staticmethod(
            lambda session_id, user_id="default": calls.setdefault(
                "shutdown_kernel",
                (session_id, user_id),
            )
        ),
    )

    (tmp_path / "user-1" / "session-1").mkdir(parents=True)

    service = FakeAgentService()
    await service._cleanup_session_resources(
        user_id="user-1",
        session_id="session-1",
        session_key="user-1/session-1",
        remove_runtime_instance=True,
    )

    assert "user-1/session-1" not in service._active_sessions
    assert "user-1/session-1" not in service._session_locks
    assert calls["shutdown_kernel"] == ("session-1", "user-1")
    assert calls["journal_init"] == (tmp_path / "user-1" / "session-1", "session-1")
    assert calls["journal_update"] == {"last_runtime_state": "discarded"}


def test_reset_session_context_ignores_cross_context_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    class FakeContextVar:
        def __init__(self, name: str, should_raise: bool = False) -> None:
            self.name = name
            self.should_raise = should_raise

        def reset(self, token) -> None:
            _ = token
            if self.should_raise:
                raise ValueError(f"{self.name} reset in different Context")
            calls.append((self.name, "reset"))

    monkeypatch.setattr(context_module, "current_code_timeout", FakeContextVar("code_timeout", should_raise=True))
    monkeypatch.setattr(context_module, "current_env_id", FakeContextVar("env_id"))
    monkeypatch.setattr(context_module, "current_session_root", FakeContextVar("session_root"))
    monkeypatch.setattr(context_module, "current_workspace", FakeContextVar("workspace"))
    monkeypatch.setattr(context_module, "current_session_id", FakeContextVar("session_id"))
    monkeypatch.setattr(context_module, "current_user_id", FakeContextVar("user_id"))

    class FakeAgentService(context_module.ContextMixin):
        pass

    service = FakeAgentService()
    service._reset_session_context(
        {
            "code_timeout": object(),
            "env_id": object(),
            "session_root": object(),
            "workspace": object(),
            "session_id": object(),
            "user_id": object(),
        }
    )

    assert ("env_id", "reset") in calls
    assert ("session_root", "reset") in calls
    assert ("workspace", "reset") in calls
    assert ("session_id", "reset") in calls
    assert ("user_id", "reset") in calls
