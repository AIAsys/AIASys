"""ShellExecutor 解释器选择单元测试。"""

from __future__ import annotations

import shutil

import pytest

from app.services.shell_executor import ShellExecutor


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
