"""ShellExecutor 解释器选择单元测试。"""

from __future__ import annotations

import asyncio
import shutil

import pytest

from app.services.shell_executor import ShellExecutor, ShellOptions


def test_normalize_interpreter_aliases():
    ex = ShellExecutor()
    assert ex._normalize_interpreter_alias("sh") == "bash"
    assert ex._normalize_interpreter_alias("zsh") == "bash"
    assert ex._normalize_interpreter_alias("ash") == "busybox"
    assert ex._normalize_interpreter_alias("pwsh") == "powershell"
    assert ex._normalize_interpreter_alias("ps") == "powershell"
    assert ex._normalize_interpreter_alias("wsl2") == "wsl"
    # 未知名称原样返回，大小写由 detect_interpreter 自行处理
    assert ex._normalize_interpreter_alias("Bash") == "Bash"
    assert ex._normalize_interpreter_alias("custom") == "custom"


def test_keyword_case_insensitive():
    ex = ShellExecutor()
    path, args, family = ex.detect_interpreter("Bash")
    assert family == "posix"


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows-only")
def test_keyword_case_insensitive_powershell():
    ex = ShellExecutor()
    path, args, family = ex.detect_interpreter("POWERSHELL")
    assert family == "powershell"


def test_detect_family_from_name():
    ex = ShellExecutor()
    assert ex._detect_family_from_name("bash.exe") == "posix"
    assert ex._detect_family_from_name("sh") == "posix"
    assert ex._detect_family_from_name("wsl.exe") == "wsl"
    assert ex._detect_family_from_name("busybox.exe") == "busybox"
    assert ex._detect_family_from_name("pwsh.exe") == "powershell"
    assert ex._detect_family_from_name("powershell.exe") == "powershell"
    assert ex._detect_family_from_name("cmd.exe") == "cmd"
    assert ex._detect_family_from_name("unknown") is None


def test_bash_keyword_resolves():
    ex = ShellExecutor()
    path, args, family = ex.detect_interpreter("bash")
    assert family == "posix"
    assert args == ["-c"]
    assert path


def test_sh_alias_resolves_to_bash():
    ex = ShellExecutor()
    path, args, family = ex.detect_interpreter("sh")
    assert family == "posix"
    assert args == ["-c"]


def test_custom_path_resolves():
    sh_path = shutil.which("sh") or "/bin/sh"
    ex = ShellExecutor()
    path, args, family = ex.detect_interpreter(sh_path)
    assert path == sh_path
    assert family == "posix"
    assert args == ["-c"]


def test_unknown_interpreter_raises():
    ex = ShellExecutor()
    with pytest.raises(ValueError):
        ex.detect_interpreter("this_does_not_exist_anywhere")


@pytest.mark.skipif(
    shutil.which("powershell") is None and shutil.which("pwsh") is None,
    reason="PowerShell not available",
)
def test_powershell_alias_pwsh():
    ex = ShellExecutor()
    # 仅在 Windows 上 powershell family 有效；在其他平台 detect_interpreter 会抛 RuntimeError
    if __import__("os").name != "nt":
        pytest.skip("Windows-only")
    path, args, family = ex.detect_interpreter("pwsh")
    assert family == "powershell"
    assert args == ["-NoProfile", "-Command"]


def test_windows_auto_no_cmd_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows auto fallback 链找不到任何解释器时，应抛 RuntimeError，不再落到 cmd.exe。"""
    ex = ShellExecutor()
    monkeypatch.setattr(ex, "_is_windows", True)
    monkeypatch.setattr(ex, "_find_git_bash", lambda: None)
    monkeypatch.setattr(ex, "_find_wsl_bash", lambda: None)
    monkeypatch.setattr(ex, "_find_busybox", lambda: None)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError) as exc_info:
        ex.detect_interpreter("auto")

    assert "cmd.exe" in str(exc_info.value)
    assert "PowerShell" in str(exc_info.value)


def test_windows_auto_prefers_powershell(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows auto fallback 链应优先使用 PowerShell。"""
    ex = ShellExecutor()
    monkeypatch.setattr(ex, "_is_windows", True)
    monkeypatch.setattr(ex, "_find_git_bash", lambda: None)
    monkeypatch.setattr(ex, "_find_wsl_bash", lambda: None)
    monkeypatch.setattr(ex, "_find_busybox", lambda: None)

    def fake_which(name: str) -> str | None:
        if name in ("pwsh", "powershell"):
            return r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        return None

    monkeypatch.setattr(shutil, "which", fake_which)
    path, args, family = ex.detect_interpreter("auto")
    assert family == "powershell"
    assert args == ["-NoProfile", "-Command"]
    assert path.endswith("powershell.exe")


def test_windows_explicit_cmd_still_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """显式指定 interpreter=cmd 时，仍允许使用 cmd.exe（兼容旧入口，但不推荐）。"""
    ex = ShellExecutor()
    monkeypatch.setattr(ex, "_is_windows", True)
    monkeypatch.setattr(shutil, "which", lambda name: r"C:\Windows\System32\cmd.exe" if name == "cmd" else None)

    path, args, family = ex.detect_interpreter("cmd")
    assert family == "cmd"
    assert args == ["/c"]
    assert path.endswith("cmd.exe")


@pytest.mark.asyncio
@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows-only")
async def test_windows_git_bash_cwd_keeps_windows_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows + Git Bash 时 cwd 必须保持 Windows 路径，避免 WinError 267。"""
    ex = ShellExecutor()
    fake_bash = r"C:\Program Files\Git\bin\bash.exe"
    monkeypatch.setattr(ex, "_is_windows", True)
    monkeypatch.setattr(ex, "_find_git_bash", lambda: fake_bash)

    captured: dict[str, object] = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["cwd"] = kwargs.get("cwd")
        class FakeProc:
            stdin = None
            stdout = None
            stderr = None
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    await ex.spawn("echo hi", options=ShellOptions(cwd=r"C:\Users\ke\workspace"), interpreter="bash")

    assert captured["cwd"] == r"C:\Users\ke\workspace"
