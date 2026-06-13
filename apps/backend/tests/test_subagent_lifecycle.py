"""测试 AIASys 子 Agent 生命周期管理器。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.services.agent.runtime_backends.base import AgentRuntimeEvent
from app.services.agent.subagent_lifecycle import SubAgentLifecycleManager
from app.services.agent.subagent_registry import SubAgentRegistry


class FakeSession:
    def __init__(self, events=None, raise_cancel=False):
        self.events = events or []
        self.raise_cancel = raise_cancel
        self.closed = False
        self.cancelled = False
        self.messages = [{"role": "system", "content": "sys"}]
        self.is_active_value = True

    def is_active(self):
        return not self.closed

    def prompt(self, user_input):
        async def _gen():
            if self.raise_cancel:
                raise asyncio.CancelledError("cancelled")
            for event in self.events:
                yield event

        return _gen()

    def cancel(self):
        self.cancelled = True

    async def close(self):
        self.closed = True


@pytest.fixture
def registry():
    reg = SubAgentRegistry()
    reg.clear()
    return reg


@pytest.fixture
def lifecycle(registry):
    return SubAgentLifecycleManager(registry=registry)


@pytest.fixture
def fake_storage(tmp_path):
    storage = MagicMock()
    storage.subagent_dir = tmp_path
    storage.read_meta.return_value = {"last_task_id": "task-1"}
    storage.append_context_message = AsyncMock()
    storage.append_wire_agent_runtime_event = AsyncMock()
    storage.update_status = Mock()
    storage.flush = AsyncMock()
    return storage


@pytest.mark.asyncio
async def test_run_subagent_session_keeps_session_alive(lifecycle, registry, fake_storage):
    """spawn_and_run 运行结束后应保持 session 注册状态为 idle。"""
    session = FakeSession(
        events=[
            AgentRuntimeEvent(kind="content", content_type="text", text="hello"),
        ]
    )

    await registry.register("agent_1", session, host_session_id="host-1")

    results = []
    async for item in lifecycle.run_subagent_session(
        subagent_session=session,
        agent_id="agent_1",
        subagent_name="worker",
        prompt="do it",
        storage=fake_storage,
    ):
        results.append(item)

    assert len(results) == 2  # streaming event + final result
    assert registry.is_active("agent_1")
    assert registry.get_status("agent_1") == SubAgentRegistry.STATUS_IDLE
    assert fake_storage.update_status.call_args_list[-1].args[0] == "idle"


@pytest.mark.asyncio
async def test_run_subagent_session_not_keep_alive(lifecycle, registry, fake_storage):
    """keep_alive=False 时运行结束后应关闭并注销 session。"""
    session = FakeSession(
        events=[
            AgentRuntimeEvent(kind="content", content_type="text", text="hello"),
        ]
    )

    await registry.register("agent_1", session, host_session_id="host-1")

    results = []
    async for item in lifecycle.run_subagent_session(
        subagent_session=session,
        agent_id="agent_1",
        subagent_name="worker",
        prompt="do it",
        storage=fake_storage,
        keep_alive=False,
    ):
        results.append(item)

    assert not registry.is_active("agent_1")
    assert session.closed


@pytest.mark.asyncio
async def test_send_input_continues_conversation(lifecycle, registry, fake_storage):
    """send_input 应向 idle 子 Agent 追加输入并继续对话。"""
    session = FakeSession(
        events=[
            AgentRuntimeEvent(kind="content", content_type="text", text="reply"),
        ]
    )
    await registry.register(
        "agent_1",
        session,
        host_session_id="host-1",
        launch_spec={
            "user_id": "u1",
            "host_session_id": "host-1",
            "subagent_type": "worker",
            "subagent_name": "worker",
            "parent_tool_call_id": "task-1",
            "workspace": "/tmp",
            "session_root": "/tmp",
        },
    )

    with patch(
        "app.services.agent.subagent_lifecycle.SubAgentStorage",
        return_value=fake_storage,
    ):
        events = []
        async for event in lifecycle.send_input("agent_1", "go on"):
            events.append(event)

    assert len(events) == 1
    assert events[0].text == "reply"
    assert registry.get_status("agent_1") == SubAgentRegistry.STATUS_IDLE
    fake_storage.append_context_message.assert_any_call(
        {"role": "user", "content": "go on", "parent_tool_call_id": "task-1"}
    )


@pytest.mark.asyncio
async def test_send_input_rejects_running_session(lifecycle, registry, fake_storage):
    """send_input 应拒绝向非 idle 状态的子 Agent 发消息。"""
    session = FakeSession()
    await registry.register(
        "agent_1",
        session,
        host_session_id="host-1",
        launch_spec={
            "user_id": "u1",
            "host_session_id": "host-1",
            "subagent_type": "worker",
        },
    )
    registry.set_status("agent_1", SubAgentRegistry.STATUS_RUNNING)

    with patch(
        "app.services.agent.subagent_lifecycle.SubAgentStorage",
        return_value=fake_storage,
    ):
        events = []
        async for event in lifecycle.send_input("agent_1", "go on"):
            events.append(event)

    assert len(events) == 1
    assert events[0].kind == "system_warning"


@pytest.mark.asyncio
async def test_close_agent_closes_session(lifecycle, registry, fake_storage):
    """close_agent 应关闭并注销子 Agent session。"""
    session = FakeSession()
    await registry.register(
        "agent_1",
        session,
        host_session_id="host-1",
        launch_spec={
            "user_id": "u1",
            "host_session_id": "host-1",
            "subagent_type": "worker",
        },
    )

    closed = await lifecycle.close_agent("agent_1")
    assert closed
    assert not registry.is_active("agent_1")
    assert session.closed


@pytest.mark.asyncio
async def test_close_agent_unknown(lifecycle):
    """close_agent 对未注册 agent 返回 False。"""
    closed = await lifecycle.close_agent("unknown")
    assert not closed


@pytest.mark.asyncio
async def test_run_subagent_session_cancelled_error(lifecycle, registry, fake_storage):
    """CancelledError 应关闭 session 并将状态设为 cancelled。"""
    session = FakeSession(raise_cancel=True)
    await registry.register("agent_1", session, host_session_id="host-1")

    with pytest.raises(asyncio.CancelledError):
        async for _ in lifecycle.run_subagent_session(
            subagent_session=session,
            agent_id="agent_1",
            subagent_name="worker",
            prompt="do it",
            storage=fake_storage,
        ):
            pass

    assert not registry.is_active("agent_1")
    assert fake_storage.update_status.call_args_list[-1].args[0] == "cancelled"


@pytest.mark.asyncio
async def test_resume_agent_reconstructs_session(tmp_path, lifecycle, registry):
    """resume_agent 应从持久化文件重建 session 并注册为 idle。"""
    subagent_dir = tmp_path / "u1" / "host-1" / ".aiasys" / "session" / "subagents" / "agent_1"
    subagent_dir.mkdir(parents=True)

    launch_spec = {
        "user_id": "u1",
        "host_session_id": "host-1",
        "subagent_type": "worker",
        "agent_file": str(subagent_dir / "agent.toml"),
        "session_root": str(tmp_path / "u1" / "host-1"),
        "workspace": str(tmp_path / "u1" / "host-1"),
        "llm_config": {
            "default_model": "test-model",
            "providers": {},
            "models": {
                "test-model": {
                    "model": "test-model",
                    "provider": "test-provider",
                }
            },
        },
    }
    meta = {
        "agent_id": "agent_1",
        "launch_spec": launch_spec,
        "status": "completed",
    }
    (subagent_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (subagent_dir / "agent.toml").write_text(
        '[agent]\nname = "worker"\nsystem_prompt = "You are a worker."\n',
        encoding="utf-8",
    )
    (subagent_dir / "context.jsonl").write_text(
        json.dumps({"role": "user", "content": "hi"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with patch("app.services.agent.subagent_lifecycle.SubAgentStorage") as mock_storage_cls:
        mock_storage = MagicMock()
        mock_storage.subagent_dir = subagent_dir
        mock_storage.meta_file = subagent_dir / "meta.json"
        mock_storage.context_file = subagent_dir / "context.jsonl"
        mock_storage.wire_file = subagent_dir / "wire.jsonl"
        mock_storage.read_meta.return_value = meta
        mock_storage.update_status = Mock()
        mock_storage_cls.return_value = mock_storage

        with patch(
            "app.services.agent.runtime_backends.aiasys.backend.AiasysRuntimeBackend"
        ) as mock_backend_cls:
            mock_session = FakeSession()
            mock_backend = MagicMock()
            mock_backend.create_session = AsyncMock(return_value=mock_session)
            mock_backend_cls.return_value = mock_backend

            resumed = await lifecycle.resume_agent("u1", "host-1", "agent_1")

    assert resumed
    assert registry.is_active("agent_1")
    assert registry.get_status("agent_1") == SubAgentRegistry.STATUS_IDLE
    assert mock_session.messages == [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
