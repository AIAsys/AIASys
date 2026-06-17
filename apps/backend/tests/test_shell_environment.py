"""Shell 环境增强检测单元测试。"""

from __future__ import annotations

import sys

import pytest

from app.services.shell_environment import (
    ShellComponentInfo,
    _build_guidance,
    _recommend_family,
    detect_shell_environment,
)


def test_detect_shell_environment_returns_report():
    report = detect_shell_environment()
    assert report.platform
    assert isinstance(report.is_windows, bool)
    assert report.recommended_family in (
        "posix",
        "wsl",
        "busybox",
        "powershell",
        "cmd",
    )
    assert len(report.components) > 0
    ids = {c.id for c in report.components}
    assert "uv" in ids
    for c in report.components:
        assert c.id
        assert c.name
        assert isinstance(c.installed, bool)


def test_recommend_family_posix_first_on_windows():
    components = [
        ShellComponentInfo(id="git_bash", name="Git Bash", installed=True),
        ShellComponentInfo(id="wsl", name="WSL", installed=True),
        ShellComponentInfo(id="busybox_w32", name="busybox-w32", installed=True),
    ]
    assert _recommend_family(True, components) == "posix"


def test_recommend_family_wsl_when_no_git_bash():
    components = [
        ShellComponentInfo(id="git_bash", name="Git Bash", installed=False),
        ShellComponentInfo(id="wsl", name="WSL", installed=True),
        ShellComponentInfo(id="busybox_w32", name="busybox-w32", installed=True),
    ]
    assert _recommend_family(True, components) == "wsl"


def test_recommend_family_busybox_fallback():
    components = [
        ShellComponentInfo(id="git_bash", name="Git Bash", installed=False),
        ShellComponentInfo(id="wsl", name="WSL", installed=False),
        ShellComponentInfo(id="busybox_w32", name="busybox-w32", installed=True),
    ]
    assert _recommend_family(True, components) == "busybox"


def test_guidance_non_windows_posix():
    components = [ShellComponentInfo(id="bash", name="Bash", installed=True)]
    g = _build_guidance(False, "posix", components)
    assert "POSIX" in g
    assert "Git Bash" not in g


def test_guidance_windows_posix():
    components = [ShellComponentInfo(id="git_bash", name="Git Bash", installed=True)]
    g = _build_guidance(True, "posix", components)
    assert "Git Bash" in g


def test_guidance_cmd_suggests_install():
    components = [
        ShellComponentInfo(id="git_bash", name="Git Bash", installed=False),
        ShellComponentInfo(id="busybox_w32", name="busybox-w32", installed=False),
    ]
    g = _build_guidance(True, "cmd", components)
    assert "Git Bash" in g
    assert "busybox-w32" in g


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only detection")
def test_windows_components_include_git_bash_and_busybox():
    report = detect_shell_environment()
    ids = {c.id for c in report.components}
    assert "git_bash" in ids
    assert "busybox_w32" in ids
    assert "wsl" in ids
