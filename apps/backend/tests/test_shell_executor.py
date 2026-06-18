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
    # 若系统只有 WSL bash（无 Git Bash），则回退到 wsl family
    assert family in ("posix", "wsl")


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
    # Windows 内置 WSL bash 路径应识别为 wsl
    assert ex._detect_family_from_name(r"C:\Windows\system32\bash.exe") == "wsl"


def test_bash_keyword_resolves():
    ex = ShellExecutor()
    path, args, family = ex.detect_interpreter("bash")
    # 优先 Git Bash（posix），没有则回退 WSL bash
    assert family in ("posix", "wsl")
    assert path


def test_sh_alias_resolves_to_bash():
    ex = ShellExecutor()
    path, args, family = ex.detect_interpreter("sh")
    assert family in ("posix", "wsl")
    assert path


def test_custom_path_resolves():
    sh_path = shutil.which("sh")
    if sh_path is None:
        pytest.skip("系统中未找到 sh")
    ex = ShellExecutor()
    path, args, family = ex.detect_interpreter(sh_path)
    assert path == sh_path
    # sh 可能是 Git Bash / MSYS sh（posix），也可能是 WSL bash 启动器
    assert family in ("posix", "wsl")


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
