"""ShellExecutor 跨平台执行器单元测试。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.services.shell_executor import ShellExecutor, ShellOptions, ShellResult


def _executor() -> ShellExecutor:
    return ShellExecutor()


@pytest.mark.asyncio
async def test_execute_echo() -> None:
    result = await _executor().execute("echo hello")

    assert isinstance(result, ShellResult)
    assert result.exit_code == 0
    assert "hello" in result.stdout
    assert result.output == result.stdout


@pytest.mark.asyncio
async def test_execute_stderr_merged() -> None:
    result = await _executor().execute("echo err >&2")

    assert result.exit_code == 0
    assert "err" in result.stderr
    assert "[stderr]" in result.output


@pytest.mark.asyncio
async def test_execute_exit_code() -> None:
    result = await _executor().execute("exit 42")

    assert result.exit_code == 42


@pytest.mark.asyncio
async def test_execute_timeout() -> None:
    with pytest.raises(TimeoutError):
        await _executor().execute("sleep 10", options=ShellOptions(timeout=1))


@pytest.mark.asyncio
async def test_execute_with_cwd(tmp_path) -> None:
    (tmp_path / "marker.txt").write_text("", encoding="utf-8")

    result = await _executor().execute(
        "ls marker.txt",
        options=ShellOptions(cwd=str(tmp_path)),
    )

    assert result.exit_code == 0
    assert "marker.txt" in result.stdout


@pytest.mark.asyncio
async def test_execute_with_env() -> None:
    result = await _executor().execute(
        "echo $AIASYS_TEST_VAR",
        options=ShellOptions(env={"AIASYS_TEST_VAR": "42"}),
    )

    assert result.exit_code == 0
    assert "42" in result.stdout


def test_win_path_to_posix() -> None:
    conv = ShellExecutor.win_path_to_posix
    assert conv(r"C:\foo\bar") == "/c/foo/bar"
    assert conv(r"C:/foo/bar") == "/c/foo/bar"
    assert conv("D:\\") == "/d"
    assert conv(r"relative\path") == "relative/path"


def test_win_path_to_wsl() -> None:
    conv = ShellExecutor.win_path_to_wsl
    assert conv(r"C:\Users\ke") == "/mnt/c/Users/ke"
    assert conv("C:\\") == "/mnt/c"
    assert conv("relative/path") is None


def test_detect_interpreter_bash() -> None:
    path, args, family = _executor().detect_interpreter("bash")
    assert family == "posix"
    assert args == ["-c"]
    assert path


def test_detect_interpreter_auto_on_posix() -> None:
    path, args, family = _executor().detect_interpreter("auto")
    assert family == "posix"
    if os.name != "nt":
        assert os.path.exists(path)


@pytest.mark.skipif(os.name != "nt", reason="仅在 Windows 上测试")
def test_detect_interpreter_cmd_on_windows() -> None:
    path, args, family = _executor().detect_interpreter("cmd")
    assert family == "cmd"
    assert path.endswith("cmd.exe")


@pytest.mark.skipif(os.name != "nt", reason="仅在 Windows 上测试")
def test_find_git_bash_on_windows() -> None:
    path = _executor()._find_git_bash()
    if path:
        assert Path(path).exists()


def test_rewrite_windows_null_redirect() -> None:
    rewrite = ShellExecutor.rewrite_windows_null_redirect
    assert rewrite("echo x >NUL") == "echo x >/dev/null"
    assert rewrite("echo x >nul") == "echo x >/dev/null"
    assert rewrite("cmd 2>NUL") == "cmd 2>/dev/null"
    assert rewrite("cmd >NUL 2>&1") == "cmd >/dev/null 2>&1"
    assert rewrite("cmd &>NUL") == "cmd &>/dev/null"
    # 不影响已转换或无关内容
    assert rewrite("echo NUL") == "echo NUL"
    assert rewrite("echo /dev/null") == "echo /dev/null"
