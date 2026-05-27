"""Shell 命令执行工具测试。"""

from __future__ import annotations

import pytest
from pathlib import Path

from app.agents.tools.shell_tool import ShellParams, Shell
from app.services.history import current_workspace
from app.services.runtime.runtime_execution import RuntimeExecutionPlan


@pytest.fixture
def tmp_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """设置临时工作区上下文，并绕过 UV 环境解析。"""
    token = current_workspace.set(str(tmp_path))
    monkeypatch.setattr(
        "app.agents.tools.shell_tool.resolve_runtime_execution_plan",
        lambda **kwargs: RuntimeExecutionPlan(
            sandbox_mode="local",
            env_id="workspace-default",
            display_name="Workspace UV",
            workspace=None,
            env=None,
        ),
    )
    yield tmp_path
    current_workspace.reset(token)


@pytest.mark.asyncio
async def test_shell_echo(tmp_workspace: Path) -> None:
    tool = Shell()
    result = await tool.invoke(**ShellParams(command="echo hello").model_dump())

    assert not result.is_error
    assert "hello" in result.output


@pytest.mark.asyncio
async def test_shell_exit_code(tmp_workspace: Path) -> None:
    tool = Shell()
    result = await tool.invoke(**ShellParams(command="exit 1").model_dump())

    assert result.is_error
    assert "退出码: 1" in result.message


@pytest.mark.asyncio
async def test_shell_stderr(tmp_workspace: Path) -> None:
    tool = Shell()
    result = await tool.invoke(**ShellParams(command="echo err >&2").model_dump())

    assert not result.is_error
    assert "err" in result.output


@pytest.mark.asyncio
async def test_shell_empty_command(tmp_workspace: Path) -> None:
    tool = Shell()
    result = await tool.invoke(**ShellParams(command="").model_dump())

    assert result.is_error
    assert "命令不能为空" in result.message


@pytest.mark.asyncio
async def test_shell_timeout(tmp_workspace: Path) -> None:
    tool = Shell()
    result = await tool.invoke(**ShellParams(command="sleep 10", timeout=1).model_dump())

    assert result.is_error
    assert "超时" in result.message


@pytest.mark.asyncio
async def test_shell_dangerous_blocked(tmp_workspace: Path) -> None:
    tool = Shell()
    result = await tool.invoke(**ShellParams(command="rm -rf /").model_dump())

    assert result.is_error
    assert "危险操作" in result.message


@pytest.mark.asyncio
async def test_shell_cwd(tmp_workspace: Path) -> None:
    (tmp_workspace / "marker.txt").write_text("", encoding="utf-8")

    tool = Shell()
    result = await tool.invoke(**ShellParams(command="ls marker.txt").model_dump())

    assert not result.is_error
    assert "marker.txt" in result.output


@pytest.mark.asyncio
async def test_shell_output_truncation(tmp_workspace: Path) -> None:
    tool = Shell()
    result = await tool.invoke(**ShellParams(command="python3 -c \"print('x' * 50000)\"").model_dump())

    assert not result.is_error
    assert "truncated" in result.output
