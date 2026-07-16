"""PowerShell 版本检测、提示词目标版本与提示词段落生成的单元测试。

覆盖 issue「AI 默认按 PowerShell 7 生成命令导致 5.1/WSL 报错」的修复：
- detect_powershell_info 解释器选择与 effective_version 解析
- 提示词目标版本偏好读写与校验
- build_powershell_prompt_section 5.1 / 7+ 两种兼容写法
- _get_execution_env_info 注入 POWERSHELL_SECTION（模板 StrictUndefined 要求）
"""

from __future__ import annotations

import json

import pytest

import app.services.shell_environment as she
from app.services.shell_environment import (
    PowerShellInfo,
    _ps_major,
    build_powershell_prompt_section,
    detect_powershell_info,
    get_powershell_prompt_target,
    set_powershell_prompt_target,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    she._ps_info_cache.clear()
    she._report_cache.clear()
    yield
    she._ps_info_cache.clear()
    she._report_cache.clear()


@pytest.fixture
def windows_env(monkeypatch, tmp_path):
    """模拟一台同时装有 pwsh 7 和 powershell 5.1 的 Windows 机器。"""

    def fake_which(name):
        return {
            "pwsh": "C:/PS7/pwsh.exe",
            "powershell": "C:/PS51/powershell.exe",
        }.get(name)

    monkeypatch.setattr(she.os, "name", "nt")
    monkeypatch.setattr(she.shutil, "which", fake_which)
    monkeypatch.setattr(
        she,
        "_query_ps_version",
        lambda path: "7.4.17" if "pwsh" in path else "5.1.26100.8875",
    )
    monkeypatch.setattr(she, "_PREFERENCES_PATH", tmp_path / "shell_preferences.json")
    return tmp_path


class TestPsMajor:
    def test_parse_versions(self):
        assert _ps_major("5.1.26100.8875") == 5
        assert _ps_major("7.4.17") == 7
        assert _ps_major(None) is None
        assert _ps_major("") is None
        assert _ps_major("unknown") is None


class TestDetectPowerShellInfo:
    def test_auto_uses_common_denominator_51(self, windows_env):
        """auto 模式下同时存在 7+ 和 5.1 时，effective_version 应取 5.1 兼容。"""
        info = detect_powershell_info(force=True)
        assert info.active_path == "C:/PS7/pwsh.exe"
        assert info.active_version == "7.4.17"
        assert info.prompt_target == "auto"
        assert info.effective_version == "5.1.26100.8875"

    def test_auto_prefers_pwsh_when_only_pwsh_installed(self, windows_env, monkeypatch):
        """auto 模式下只有 pwsh 7+ 时，effective_version 取 7+。"""
        monkeypatch.setattr(
            she.shutil,
            "which",
            lambda name: "C:/PS7/pwsh.exe" if name == "pwsh" else None,
        )
        info = detect_powershell_info(force=True)
        assert info.effective_version == "7.4.17"

    def test_target_51_uses_windows_powershell(self, windows_env):
        set_powershell_prompt_target("5.1")
        info = detect_powershell_info(force=True)
        assert info.effective_version == "5.1.26100.8875"

    def test_target_7_uses_pwsh(self, windows_env):
        set_powershell_prompt_target("7")
        info = detect_powershell_info(force=True)
        assert info.effective_version == "7.4.17"

    def test_non_windows_returns_empty(self, monkeypatch):
        monkeypatch.setattr(she.os, "name", "posix")
        info = detect_powershell_info(force=True)
        assert info.active_path is None
        assert info.effective_version is None


class TestPromptTargetPreference:
    def test_default_is_auto(self, windows_env):
        assert get_powershell_prompt_target() == "auto"

    def test_round_trip(self, windows_env):
        set_powershell_prompt_target("5.1")
        assert get_powershell_prompt_target() == "5.1"
        data = json.loads(she._PREFERENCES_PATH.read_text(encoding="utf-8"))
        assert data["powershell_prompt_target"] == "5.1"
        set_powershell_prompt_target("auto")
        assert get_powershell_prompt_target() == "auto"

    def test_invalid_target_rejected(self, windows_env):
        with pytest.raises(ValueError, match="无效"):
            set_powershell_prompt_target("9")

    def test_target_7_requires_pwsh(self, windows_env, monkeypatch):
        monkeypatch.setattr(
            she.shutil,
            "which",
            lambda name: "C:/PS51/powershell.exe" if name == "powershell" else None,
        )
        with pytest.raises(ValueError, match="pwsh"):
            set_powershell_prompt_target("7")

    def test_corrupt_preference_file_falls_back_to_auto(self, windows_env):
        she._PREFERENCES_PATH.write_text("not-json", encoding="utf-8")
        assert get_powershell_prompt_target() == "auto"


class TestBuildPromptSection:
    def _fake_info(self, **overrides) -> PowerShellInfo:
        base = dict(
            pwsh_path="C:/PS7/pwsh.exe",
            pwsh_version="7.4.17",
            powershell_path="C:/PS51/powershell.exe",
            powershell_version="5.1.26100.8875",
            active_path="C:/PS7/pwsh.exe",
            active_version="7.4.17",
            prompt_target="auto",
            effective_version="7.4.17",
        )
        base.update(overrides)
        return PowerShellInfo(**base)

    def test_non_windows_returns_empty(self, monkeypatch):
        monkeypatch.setattr(she.os, "name", "posix")
        assert build_powershell_prompt_section() == ""

    def test_ps7_section(self, windows_env, monkeypatch):
        monkeypatch.setattr(she, "detect_powershell_info", lambda force=False: self._fake_info())
        section = build_powershell_prompt_section()
        assert "7.4.17" in section
        assert "pwsh" in section
        assert "WSL" in section
        assert "5.1 兼容写法" in section

    def test_auto_ps51_section_when_both_installed(self, windows_env, monkeypatch):
        """auto 同时有 7+ 和 5.1 时，提示词按 5.1 生成并指向 powershell.exe。"""
        monkeypatch.setattr(
            she,
            "detect_powershell_info",
            lambda force=False: self._fake_info(
                effective_version="5.1.26100.8875",
            ),
        )
        section = build_powershell_prompt_section()
        assert "5.1.26100.8875" in section
        assert "C:/PS51/powershell.exe" in section
        assert "C:/PS7/pwsh.exe" not in section
        assert "&&" in section
        assert "三元运算符" in section
        assert "用户已固定" not in section

    def test_ps51_section_with_user_target(self, windows_env, monkeypatch):
        monkeypatch.setattr(
            she,
            "detect_powershell_info",
            lambda force=False: self._fake_info(
                prompt_target="5.1",
                effective_version="5.1.26100.8875",
            ),
        )
        section = build_powershell_prompt_section()
        assert "5.1.26100.8875" in section
        # 固定 5.1 目标时路径应指向 powershell.exe 而不是 pwsh
        assert "C:/PS51/powershell.exe" in section
        assert "C:/PS7/pwsh.exe" not in section
        assert "&&" in section  # 提示词里必须包含 5.1 禁用 && 的规则
        assert "三元运算符" in section
        assert "用户已固定提示词目标版本为 5.1" in section

    def test_no_powershell_detected_returns_empty(self, windows_env, monkeypatch):
        monkeypatch.setattr(she, "detect_powershell_info", lambda force=False: PowerShellInfo())
        assert build_powershell_prompt_section() == ""


class TestExecutionEnvInfo:
    def test_env_info_contains_powershell_section(self, monkeypatch):
        from app.services.agent import config as agent_config

        monkeypatch.setattr(
            she,
            "build_powershell_prompt_section",
            lambda: "- PowerShell：5.1（测试注入）",
        )
        env = agent_config._get_execution_env_info()
        assert env["POWERSHELL_SECTION"] == "- PowerShell：5.1（测试注入）"

    def test_env_info_degrades_when_detection_fails(self, monkeypatch):
        from app.services.agent import config as agent_config

        def _boom():
            raise RuntimeError("detection failed")

        monkeypatch.setattr(she, "build_powershell_prompt_section", _boom)
        env = agent_config._get_execution_env_info()
        assert env["POWERSHELL_SECTION"] == ""

    def test_prompt_template_declares_placeholder(self):
        """模板必须声明 ${POWERSHELL_SECTION}，否则注入不会生效（StrictUndefined）。"""
        from pathlib import Path

        template = Path("app/agents/local_sandbox_agent_config/general_host_prompt.md").read_text(
            encoding="utf-8"
        )
        assert "${POWERSHELL_SECTION}" in template
