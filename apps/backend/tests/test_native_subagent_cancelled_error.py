"""测试 TaskTool 在 asyncio.CancelledError 时的状态更新。

当 Host SSE 连接断开时，invoke_stream 的协程会被取消，抛出 asyncio.CancelledError。
此测试验证：CancelledError 被正确捕获并设置 subagent 状态为 "cancelled"，
而不是被通用的 Exception 捕获导致状态变为 "failed"。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.runtime_backends.aiasys.tools.task_tool import TaskTool


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.mark.asyncio
async def test_invoke_stream_sets_cancelled_status_on_cancelled_error(
    temp_workspace,
    monkeypatch,
):
    """验证 CancelledError 触发后 meta.json 状态为 cancelled 而非 failed。"""
    from app.services.agent import subagent_storage

    monkeypatch.setattr(subagent_storage, "WORKSPACE_DIR", temp_workspace)

    tool = TaskTool()

    # Mock _find_subagent_manifest 返回一个最小 manifest
    manifest = {
        "name": "coder",
        "system_prompt": "You are a coder.",
    }

    # Mock backend.create_session 返回一个 session，其 prompt() 返回的 async iterable 抛出 CancelledError
    class CancelledAsyncIterator:
        def __aiter__(self):
            return self
        async def __anext__(self):
            raise asyncio.CancelledError("Simulated SSE disconnect")

    mock_session = MagicMock()
    mock_session.prompt = MagicMock(return_value=CancelledAsyncIterator())
    mock_session.close = AsyncMock()

    mock_backend = MagicMock()
    mock_backend.create_session = AsyncMock(return_value=mock_session)

    ctx = {
        "user_id": "test_user",
        "session_id": "test_session",
        "host_session_id": "test_session",
        "workspace": str(temp_workspace),
        "session_root": str(temp_workspace),
        "agent_config": {
            "subagents": {
                "coder": {
                    "agent_manifest": manifest,
                }
            }
        },
        "llm_config": MagicMock(),
        "agent_path": "/root",
    }

    with patch(
        "app.services.agent.runtime_backends.aiasys.tools.task_tool._find_subagent_manifest",
        return_value=manifest,
    ):
        with patch(
            "app.services.agent.runtime_backends.aiasys.tools.task_tool.AiasysRuntimeBackend",
            return_value=mock_backend,
        ):
            # 收集 yielded 的结果，但预期会被 CancelledError 中断
            results = []
            with pytest.raises(asyncio.CancelledError):
                async for result in tool.invoke_stream(
                    ctx,
                    subagent_name="coder",
                    description="test task",
                    prompt="write some code",
                ):
                    results.append(result)

    # 验证 session.prompt 被调用过（prompt 返回 async iterable，不是 coroutine）
    mock_session.prompt.assert_called_once()

    # 验证 storage 目录已创建且状态为 cancelled
    from app.services.agent.subagent_storage import SubAgentStorage

    # agent_id 格式: {subagent_name}_{uuid.hex[:12]}
    # 需要从实际创建的 storage 中读取，但 agent_id 在 invoke_stream 内部生成。
    # 我们通过扫描 subagents 目录来找到它。
    subagents_dir = (
        temp_workspace / "test_user" / "test_session"
        / ".aiasys" / "session" / "subagents"
    )
    assert subagents_dir.exists(), f"subagents dir not found at {subagents_dir}"

    agent_dirs = [d for d in subagents_dir.iterdir() if d.is_dir()]
    assert len(agent_dirs) == 1, f"expected 1 agent dir, found: {agent_dirs}"

    meta_file = agent_dirs[0] / "meta.json"
    assert meta_file.exists()

    import json

    meta = json.loads(meta_file.read_text())
    assert meta["status"] == "cancelled", (
        f"Expected status 'cancelled', got '{meta['status']}'"
    )
    assert meta["subagent_type"] == "coder"

    # 验证 session.close 被调用（在 finally 中）
    mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_invoke_stream_sets_failed_status_on_generic_exception(
    temp_workspace,
    monkeypatch,
):
    """验证普通 Exception 触发后 meta.json 状态为 failed。"""
    from app.services.agent import subagent_storage

    monkeypatch.setattr(subagent_storage, "WORKSPACE_DIR", temp_workspace)

    tool = TaskTool()

    manifest = {
        "name": "coder",
        "system_prompt": "You are a coder.",
    }

    class FailingAsyncIterator:
        def __aiter__(self):
            return self
        async def __anext__(self):
            raise RuntimeError("Something went wrong")

    mock_session = MagicMock()
    mock_session.prompt = MagicMock(return_value=FailingAsyncIterator())
    mock_session.close = AsyncMock()

    mock_backend = MagicMock()
    mock_backend.create_session = AsyncMock(return_value=mock_session)

    ctx = {
        "user_id": "test_user",
        "session_id": "test_session",
        "host_session_id": "test_session",
        "workspace": str(temp_workspace),
        "session_root": str(temp_workspace),
        "agent_config": {
            "subagents": {
                "coder": {
                    "agent_manifest": manifest,
                }
            }
        },
        "llm_config": MagicMock(),
        "agent_path": "/root",
    }

    with patch(
        "app.services.agent.runtime_backends.aiasys.tools.task_tool._find_subagent_manifest",
        return_value=manifest,
    ):
        with patch(
            "app.services.agent.runtime_backends.aiasys.tools.task_tool.AiasysRuntimeBackend",
            return_value=mock_backend,
        ):
            results = []
            async for result in tool.invoke_stream(
                ctx,
                subagent_name="coder",
                description="test task",
                prompt="write some code",
            ):
                results.append(result)

    # 对于普通异常，invoke_stream 会捕获并 yield 最终结果，不会抛出
    assert len(results) >= 1
    assert results[-1].is_error is True
    assert "执行异常" in results[-1].content

    subagents_dir = (
        temp_workspace / "test_user" / "test_session"
        / ".aiasys" / "session" / "subagents"
    )
    agent_dirs = [d for d in subagents_dir.iterdir() if d.is_dir()]
    assert len(agent_dirs) == 1

    import json

    meta = json.loads((agent_dirs[0] / "meta.json").read_text())
    assert meta["status"] == "failed", (
        f"Expected status 'failed', got '{meta['status']}'"
    )
