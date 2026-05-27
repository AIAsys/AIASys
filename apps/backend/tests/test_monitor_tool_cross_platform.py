from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from app.services.agent.runtime_backends.aiasys.tools.monitor_tool import (
    MonitorService,
    SpawnMonitorTool,
)
from app.services.runtime.runtime_execution import RuntimeExecutionPlan


@pytest.mark.asyncio
async def test_monitor_without_session_root_uses_platform_temp_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

    service = MonitorService()
    session = await service.spawn(
        "echo ok",
        "invalid-session-key",
        cwd=str(tmp_path),
        timeout_seconds=5,
    )

    try:
        await session.process.wait()
        assert session.stdout_path is not None
        assert session.stderr_path is not None
        assert session.stdout_path.parent == tmp_path / "aiasys"
        assert session.stderr_path.parent == tmp_path / "aiasys"
        assert "/tmp/aiasys-monitor" not in session.stdout_path.as_posix()
    finally:
        await service.cleanup_all()


@pytest.mark.asyncio
async def test_monitor_dangerous_command_uses_platform_null_device(
    tmp_path: Path,
) -> None:
    service = MonitorService()

    session = await service.spawn(
        "rm -rf /",
        "invalid-session-key",
        cwd=str(tmp_path),
    )

    assert session.status == "error"
    assert session.out_file == Path(os.devnull)


@pytest.mark.asyncio
async def test_spawn_monitor_blocks_dangerous_command_before_runtime_wrapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    tool = SpawnMonitorTool()

    async def fake_spawn(_self=None, *, command: str, **kwargs):
        del kwargs
        calls.append(command)
        raise AssertionError("dangerous command should not reach MonitorService.spawn")

    monkeypatch.setattr(
        "app.services.agent.runtime_backends.aiasys.tools.monitor_tool.get_monitor_service",
        lambda: type("_Service", (), {"spawn": fake_spawn})(),
    )

    result = await tool.invoke(
        ctx={
            "user_id": "local_default",
            "session_id": "session-alpha",
            "workspace": tmp_path,
        },
        command="rm -rf /",
    )

    assert result.is_error
    assert "危险操作" in result.message
    assert calls == []


@pytest.mark.asyncio
async def test_spawn_monitor_uses_sanitized_runtime_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    tool = SpawnMonitorTool()

    class _Session:
        id = "mon_test"
        status = "running"
        mode = "silent"
        out_file = tmp_path / "monitor.log"

    async def fake_spawn(_self=None, **kwargs):
        captured.update(kwargs)
        return _Session()

    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("PUBLIC_FLAG", "kept")
    monkeypatch.setattr(
        "app.services.agent.runtime_backends.aiasys.tools.monitor_tool.get_monitor_service",
        lambda: type("_Service", (), {"spawn": fake_spawn})(),
    )
    monkeypatch.setattr(
        "app.services.agent.runtime_backends.aiasys.tools.monitor_tool.resolve_runtime_execution_plan",
        lambda **kwargs: RuntimeExecutionPlan(
            sandbox_mode="local",
            env_id="workspace-default",
            display_name="Workspace UV",
            workspace=tmp_path,
            env=None,
        ),
    )

    result = await tool.invoke(
        ctx={
            "user_id": "local_default",
            "session_id": "session-alpha",
            "workspace": tmp_path,
        },
        command="echo ok",
        mode="silent",
    )

    assert not result.is_error
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["PUBLIC_FLAG"] == "kept"
    assert env["AIASYS_RUNTIME_ENV_ID"] == "workspace-default"
    assert "OPENAI_API_KEY" not in env
