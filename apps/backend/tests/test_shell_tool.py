"""Shell 命令执行工具测试。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.agents.tools.shell_tool import Shell, ShellParams
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
    result = await tool.invoke(
        **ShellParams(command="python3 -c \"print('x' * 50000)\"").model_dump()
    )

    assert not result.is_error
    assert "truncated" in result.output


@pytest.mark.asyncio
async def test_shell_dangerous_windows_blocked(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows 危险命令检测：mock os.name='nt' 后应拦截 Windows 特有危险命令。"""
    monkeypatch.setattr(os, "name", "nt")
    tool = Shell()

    # del 删除 C 盘
    result = await tool.invoke(**ShellParams(command="del /f /s /q C:\\").model_dump())
    assert result.is_error
    assert "危险操作" in result.message

    # rd 删除 C 盘
    result = await tool.invoke(**ShellParams(command="rd /s /q C:\\").model_dump())
    assert result.is_error
    assert "危险操作" in result.message

    # format 格式化
    result = await tool.invoke(**ShellParams(command="format C:").model_dump())
    assert result.is_error
    assert "危险操作" in result.message

    # diskpart
    result = await tool.invoke(**ShellParams(command="diskpart").model_dump())
    assert result.is_error
    assert "危险操作" in result.message

    # shutdown
    result = await tool.invoke(**ShellParams(command="shutdown /s /f /t 0").model_dump())
    assert result.is_error
    assert "危险操作" in result.message

    # PowerShell Remove-Item -Recurse
    result = await tool.invoke(
        **ShellParams(command='powershell -Command "Remove-Item -Recurse -Force C:\\"').model_dump()
    )
    assert result.is_error
    assert "危险操作" in result.message


@pytest.mark.asyncio
async def test_shell_interpreter_auto(tmp_workspace: Path) -> None:
    """默认 interpreter='auto' 应正常执行命令。"""
    tool = Shell()
    result = await tool.invoke(**ShellParams(command="echo auto").model_dump())

    assert not result.is_error
    assert "auto" in result.output


@pytest.mark.asyncio
async def test_shell_interpreter_bash(tmp_workspace: Path) -> None:
    """显式指定 interpreter='bash' 时应使用 bash 执行命令。"""
    tool = Shell()
    result = await tool.invoke(
        **ShellParams(command="echo bash_test", interpreter="bash").model_dump()
    )

    assert not result.is_error
    assert "bash_test" in result.output


@pytest.mark.asyncio
async def test_shell_interpreter_cmd_unavailable_on_posix(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """非 Windows 系统上 interpreter='cmd' 应返回错误。"""
    monkeypatch.setattr(os, "name", "posix")
    tool = Shell()
    result = await tool.invoke(
        **ShellParams(command="echo cmd_test", interpreter="cmd").model_dump()
    )

    assert result.is_error
    assert "cmd" in result.message


@pytest.mark.asyncio
async def test_shell_interpreter_powershell_unavailable_on_posix(
    tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """非 Windows 系统上 interpreter='powershell' 应返回错误。"""
    monkeypatch.setattr(os, "name", "posix")
    tool = Shell()
    result = await tool.invoke(
        **ShellParams(command="echo ps_test", interpreter="powershell").model_dump()
    )

    assert result.is_error
    assert "powershell" in result.message


@pytest.mark.asyncio
async def test_shell_interpreter_invalid(tmp_workspace: Path) -> None:
    """不支持的 interpreter 值应返回错误。"""
    tool = Shell()
    result = await tool.invoke(
        **ShellParams(command="echo invalid", interpreter="unknown_shell").model_dump()
    )

    assert result.is_error
    assert "interpreter" in result.message
