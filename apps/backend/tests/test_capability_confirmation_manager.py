"""CapabilityConfirmationManager 单元测试。"""

from __future__ import annotations

import asyncio

import pytest

from app.services.agent.runtime_backends.aiasys.capability_confirmation import (
    CapabilityConfirmationManager,
)


@pytest.fixture
def manager():
    return CapabilityConfirmationManager()


class TestAutoApprove:
    @pytest.mark.asyncio
    async def test_is_auto_approved_default_false(self, manager):
        assert await manager.is_auto_approved("Shell") is False

    @pytest.mark.asyncio
    async def test_add_auto_approved(self, manager):
        await manager.add_auto_approved("Shell")
        assert await manager.is_auto_approved("Shell") is True
        assert await manager.is_auto_approved("Write") is False


class TestWaitForConfirmation:
    @pytest.mark.asyncio
    async def test_wait_then_resolve(self, manager):
        task = asyncio.create_task(
            manager.wait_for_confirmation(
                tool_call_id="tc1",
                tool_name="Shell",
                arguments={"command": "ls"},
                prompt="Run ls?",
                timeout=5.0,
            )
        )
        # 给事件循环一点时间创建 future
        await asyncio.sleep(0.05)

        resolved = await manager.resolve("tc1", approved=True)
        assert resolved is True

        approved, feedback = await task
        assert approved is True
        assert feedback == ""
        assert manager._pending["tc1"].status == "approved"

    @pytest.mark.asyncio
    async def test_wait_then_reject(self, manager):
        task = asyncio.create_task(
            manager.wait_for_confirmation(
                tool_call_id="tc2",
                tool_name="Write",
                arguments={"path": "x"},
                prompt="Write file?",
                timeout=5.0,
            )
        )
        await asyncio.sleep(0.05)

        resolved = await manager.resolve("tc2", approved=False, feedback="don't touch this")
        assert resolved is True

        approved, feedback = await task
        assert approved is False
        assert feedback == "don't touch this"
        assert manager._pending["tc2"].status == "denied"

    @pytest.mark.asyncio
    async def test_auto_approved_skips_wait(self, manager):
        await manager.add_auto_approved("Shell")
        approved, feedback = await manager.wait_for_confirmation(
            tool_call_id="tc3",
            tool_name="Shell",
            arguments={},
            prompt="Run?",
        )
        assert approved is True
        assert feedback == ""

    @pytest.mark.asyncio
    async def test_timeout(self, manager):
        approved, feedback = await manager.wait_for_confirmation(
            tool_call_id="tc4",
            tool_name="Shell",
            arguments={},
            prompt="Run?",
            timeout=0.1,
        )
        assert approved is False
        assert "超时" in feedback
        assert manager._pending["tc4"].status == "timeout"

    @pytest.mark.asyncio
    async def test_resolve_unknown_id_returns_false(self, manager):
        assert await manager.resolve("nope", approved=True) is False

    @pytest.mark.asyncio
    async def test_resolve_already_resolved_returns_false(self, manager):
        task = asyncio.create_task(
            manager.wait_for_confirmation(
                tool_call_id="tc5",
                tool_name="Shell",
                arguments={},
                prompt="Run?",
                timeout=5.0,
            )
        )
        await asyncio.sleep(0.05)
        assert await manager.resolve("tc5", approved=True) is True
        await task
        # 第二次 resolve 同一个 id 应该失败
        assert await manager.resolve("tc5", approved=True) is False


class TestSessionScope:
    @pytest.mark.asyncio
    async def test_approve_for_session_remembers(self, manager):
        # 第一次请求，approve_for_session
        task = asyncio.create_task(
            manager.wait_for_confirmation(
                tool_call_id="tc6",
                tool_name="Shell",
                arguments={},
                prompt="Run?",
                timeout=5.0,
            )
        )
        await asyncio.sleep(0.05)
        await manager.resolve("tc6", approved=True, scope="session")
        await task

        # 第二次同工具名请求应该自动批准
        approved, feedback = await manager.wait_for_confirmation(
            tool_call_id="tc7",
            tool_name="Shell",
            arguments={},
            prompt="Run?",
        )
        assert approved is True
        assert feedback == ""


class TestCancelAll:
    @pytest.mark.asyncio
    async def test_cancel_all_pending(self, manager):
        task = asyncio.create_task(
            manager.wait_for_confirmation(
                tool_call_id="tc8",
                tool_name="Shell",
                arguments={},
                prompt="Run?",
                timeout=5.0,
            )
        )
        await asyncio.sleep(0.05)
        await manager.cancel_all("test cleanup")
        approved, feedback = await task
        assert approved is False
        assert feedback == "test cleanup"


class TestListPending:
    @pytest.mark.asyncio
    async def test_list_pending(self, manager):
        task = asyncio.create_task(
            manager.wait_for_confirmation(
                tool_call_id="tc9",
                tool_name="Shell",
                arguments={"cmd": "ls"},
                prompt="Run ls?",
                timeout=5.0,
                subagent_name="coder",
            )
        )
        await asyncio.sleep(0.05)
        pending = await manager.list_pending()
        assert len(pending) == 1
        assert pending[0].tool_call_id == "tc9"
        assert pending[0].subagent_name == "coder"
        await manager.resolve("tc9", approved=True)
        await task
