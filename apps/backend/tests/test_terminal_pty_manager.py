"""Tests for PtyManager detach/attach functionality."""
import asyncio
import sys
from unittest.mock import MagicMock

import pytest

from app.services.terminal.pty_manager import PtyManager, PtySession

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="PTY not supported on Windows")


@pytest.fixture
def pty_manager():
    return PtyManager()


@pytest.fixture
def mock_session():
    session = MagicMock(spec=PtySession)
    session.terminal_id = "term-test-001"
    session.pid = 12345
    session.master_fd = 10
    session._closed = False
    session.has_interaction = True
    session.read_task = None
    session.session_key = ""
    session._on_output = None
    session._on_exit = None
    return session


@pytest.mark.asyncio
async def test_detach_preserves_session(pty_manager, mock_session):
    """detach 后 session 仍在 _sessions 和 _session_index 中"""
    pty_manager._sessions["term-test-001"] = mock_session
    await pty_manager.detach("term-test-001", "user:session")

    assert "term-test-001" in pty_manager._sessions
    assert "user:session" in pty_manager._session_index
    assert mock_session.session_key == "user:session"
    # detach 取消了 read_task
    if mock_session.read_task:
        assert mock_session.read_task.cancel.called


@pytest.mark.asyncio
async def test_detach_clears_read_task(pty_manager, mock_session):
    """detach 取消读取循环但不关闭 session"""
    mock_task = MagicMock()
    mock_task.done.return_value = False
    mock_session.read_task = mock_task
    pty_manager._sessions["term-test-001"] = mock_session
    await pty_manager.detach("term-test-001", "user:session")

    # detach 不再取消 read_task，改为启动缓冲模式（_pending_output）
    assert not mock_task.cancel.called
    assert mock_session._pending_output == []
    assert not mock_session.close.called


@pytest.mark.asyncio
async def test_attach_restores_session(pty_manager, mock_session):
    """attach 重新绑定回调"""
    pty_manager._sessions["term-test-001"] = mock_session
    pty_manager._session_index["user:session"] = mock_session

    new_output = MagicMock()
    new_exit = MagicMock()
    result = await pty_manager.attach(
        "user:session",
        on_output=new_output,
        on_exit=new_exit,
    )

    assert result is mock_session
    assert mock_session._on_output is new_output
    assert mock_session._on_exit is new_exit


@pytest.mark.asyncio
async def test_attach_nonexistent_returns_none(pty_manager):
    """attach 不存在的 session 返回 None"""
    result = await pty_manager.attach("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_attach_closed_session_returns_none(pty_manager, mock_session):
    """attach 已关闭的 session 返回 None"""
    mock_session._closed = True
    pty_manager._session_index["user:session"] = mock_session
    result = await pty_manager.attach("user:session")
    assert result is None


@pytest.mark.asyncio
async def test_kill_removes_from_both_indexes(pty_manager, mock_session):
    """kill 从 _sessions 和 _session_index 中移除"""
    mock_session.session_key = "user:session"
    pty_manager._sessions["term-test-001"] = mock_session
    pty_manager._session_index["user:session"] = mock_session

    result = await pty_manager.kill("term-test-001")
    assert result is True
    assert "term-test-001" not in pty_manager._sessions
    assert "user:session" not in pty_manager._session_index
    assert mock_session.close.called


@pytest.mark.asyncio
async def test_kill_nonexistent_returns_false(pty_manager):
    """kill 不存在的 session 返回 False"""
    result = await pty_manager.kill("nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_kill_all_clears_everything(pty_manager, mock_session):
    """kill_all 清理所有会话"""
    session2 = MagicMock(spec=PtySession)
    session2._closed = False
    pty_manager._sessions["term-test-001"] = mock_session
    pty_manager._sessions["term-test-002"] = session2

    await pty_manager.kill_all()
    assert len(pty_manager._sessions) == 0
    assert len(pty_manager._session_index) == 0
    assert mock_session.close.called
    assert session2.close.called


def test_list_sessions(pty_manager, mock_session):
    """list_sessions 返回所有活跃终端 ID"""
    pty_manager._sessions["term-a"] = mock_session
    pty_manager._sessions["term-b"] = MagicMock(spec=PtySession)

    sessions = pty_manager.list_sessions()
    assert set(sessions) == {"term-a", "term-b"}


def test_get_session(pty_manager, mock_session):
    """get_session 返回指定会话"""
    pty_manager._sessions["term-test-001"] = mock_session
    assert pty_manager.get_session("term-test-001") is mock_session
    assert pty_manager.get_session("nonexistent") is None