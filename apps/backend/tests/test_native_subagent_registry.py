"""测试 AIASys 原生 SubAgentRegistry。"""

from __future__ import annotations

import asyncio

import pytest

from app.services.agent.subagent_registry import SubAgentRegistry, get_subagent_registry


class FakeSession:
    def __init__(self):
        self.cancelled = False
        self._cancel_event = asyncio.Event()

    def cancel(self):
        self.cancelled = True
        self._cancel_event.set()


class TestSubAgentRegistry:
    def test_register_and_get(self):
        reg = SubAgentRegistry()
        session = FakeSession()
        asyncio.run(reg.register("agent_1", session))
        assert reg.get("agent_1") is session
        assert reg.is_active("agent_1")
        assert reg.list_active() == ["agent_1"]

    def test_unregister(self):
        reg = SubAgentRegistry()
        session = FakeSession()
        asyncio.run(reg.register("agent_1", session))
        reg.unregister("agent_1")
        assert reg.get("agent_1") is None
        assert not reg.is_active("agent_1")

    def test_cancel(self):
        reg = SubAgentRegistry()
        session = FakeSession()
        asyncio.run(reg.register("agent_1", session))
        result = reg.cancel("agent_1")
        assert result is True
        assert session.cancelled is True

    def test_cancel_unknown(self):
        reg = SubAgentRegistry()
        result = reg.cancel("unknown")
        assert result is False

    def test_cancel_all(self):
        reg = SubAgentRegistry()
        s1 = FakeSession()
        s2 = FakeSession()
        asyncio.run(reg.register("agent_1", s1))
        asyncio.run(reg.register("agent_2", s2))
        cancelled = reg.cancel_all()
        assert sorted(cancelled) == ["agent_1", "agent_2"]
        assert s1.cancelled
        assert s2.cancelled

    def test_clear(self):
        reg = SubAgentRegistry()
        asyncio.run(reg.register("agent_1", FakeSession()))
        reg.clear()
        assert reg.list_active() == []

    def test_count_active_for_host(self):
        reg = SubAgentRegistry()
        asyncio.run(reg.register("agent_1", FakeSession(), host_session_id="host-1"))
        asyncio.run(reg.register("agent_2", FakeSession(), host_session_id="host-1"))
        asyncio.run(reg.register("agent_3", FakeSession(), host_session_id="host-2"))
        asyncio.run(reg.register("agent_4", FakeSession()))

        assert reg.count_active_for_host("host-1") == 2
        assert reg.count_active_for_host("host-2") == 1
        assert reg.count_active_for_host("missing") == 0

    def test_get_subagent_registry_singleton(self):
        reg1 = get_subagent_registry()
        reg2 = get_subagent_registry()
        assert reg1 is reg2
