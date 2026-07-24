"""Shell 环境增强检测单元测试。"""

from __future__ import annotations

import sys

import pytest

import app.services.shell_environment as she
from app.services.shell_environment import (
    ShellComponentInfo,
    ShellEnvironmentReport,
    _build_guidance,
    _recommend_family,
    build_shell_prompt_section,
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


def test_guidance_powershell_suggests_install():
    # cmd 已移除，powershell 是 Windows 最终回退，guidance 应包含安装建议
    components = [
        ShellComponentInfo(id="git_bash", name="Git Bash", installed=False),
        ShellComponentInfo(id="busybox_w32", name="busybox-w32", installed=False),
    ]
    g = _build_guidance(True, "powershell", components)
    assert "Git Bash" in g
    assert "busybox-w32" in g


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only detection")
def test_windows_components_include_git_bash_and_busybox():
    report = detect_shell_environment()
    ids = {c.id for c in report.components}
    assert "git_bash" in ids
    assert "busybox_w32" in ids
    assert "wsl" in ids


def _fake_report(
    family: str,
    is_windows: bool = True,
    guidance: str = "",
) -> ShellEnvironmentReport:
    return ShellEnvironmentReport(
        platform="windows" if is_windows else "linux",
        is_windows=is_windows,
        recommended_family=family,
        components=[],
        guidance=guidance,
    )


class TestBuildShellPromptSection:
    """按 recommended_family 生成语法口径段落，且口径与执行层 auto 一致。"""

    def test_posix_windows_uses_git_bash_and_posix_syntax(self, monkeypatch):
        monkeypatch.setattr(
            she, "detect_shell_environment", lambda force=False: _fake_report("posix", True)
        )
        section = build_shell_prompt_section()
        assert "Git Bash" in section
        assert "2>/dev/null" in section
        # 绝不能再教 cmd 的 2>nul
        assert "2>nul" not in section
        # POSIX 下应提示用显式 interpreter 切到 powershell
        assert "powershell" in section

    def test_posix_non_windows(self, monkeypatch):
        monkeypatch.setattr(
            she, "detect_shell_environment", lambda force=False: _fake_report("posix", False)
        )
        section = build_shell_prompt_section()
        assert "POSIX" in section
        assert "2>/dev/null" in section
        # 非 Windows 不应出现 Git Bash 字样
        assert "Git Bash" not in section

    def test_powershell_family_uses_ps_syntax(self, monkeypatch):
        monkeypatch.setattr(
            she, "detect_shell_environment", lambda force=False: _fake_report("powershell", True)
        )
        section = build_shell_prompt_section()
        assert "PowerShell" in section
        assert "2>$null" in section
        assert "Get-ChildItem" in section
        assert "2>nul" not in section

    def test_wsl_family_mentions_mount_path(self, monkeypatch):
        monkeypatch.setattr(
            she, "detect_shell_environment", lambda force=False: _fake_report("wsl", True)
        )
        section = build_shell_prompt_section()
        assert "WSL" in section
        assert "/mnt/c/" in section
        assert "2>/dev/null" in section

    def test_busybox_family(self, monkeypatch):
        monkeypatch.setattr(
            she, "detect_shell_environment", lambda force=False: _fake_report("busybox", True)
        )
        section = build_shell_prompt_section()
        assert "busybox" in section.lower()
        assert "2>/dev/null" in section

    def test_guidance_is_appended(self, monkeypatch):
        monkeypatch.setattr(
            she,
            "detect_shell_environment",
            lambda force=False: _fake_report("posix", True, guidance="当前使用 Git Bash"),
        )
        section = build_shell_prompt_section()
        assert "当前使用 Git Bash" in section

    def test_unknown_family_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            she, "detect_shell_environment", lambda force=False: _fake_report("weird", True)
        )
        assert build_shell_prompt_section() == ""


def test_prompt_template_declares_shell_guidance_placeholder():
    """模板必须声明 ${SHELL_GUIDANCE_SECTION}，否则动态口径不会注入（StrictUndefined）。"""
    from pathlib import Path

    template = Path(
        "app/agents/local_sandbox_agent_config/general_host_prompt.md"
    ).read_text(encoding="utf-8")
    assert "${SHELL_GUIDANCE_SECTION}" in template
    # 旧的、与执行层 auto 相矛盾的硬编码指引应已移除
    assert "2>nul" not in template
    assert "Windows 上优先使用 PowerShell 语法" not in template
