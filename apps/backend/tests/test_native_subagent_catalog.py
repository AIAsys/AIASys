"""测试 AIASys 原生 SubAgent 目录管理器（global/workspace 配置源）。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.services.agent.subagent_catalog import (
    compute_subagent_visibility_fingerprint,
    delete_subagent,
    is_system_subagent_name,
    is_valid_subagent_name,
    is_subagent_dispatch_enabled,
    ensure_default_builtin_experts_installed,
    is_subagent_installed_to_scope,
    list_subagents,
    load_custom_subagents_for_manifest,
    load_enabled_experts,
    load_subagent_for_runtime,
    load_subagent_visibility_policy,
    resolve_subagent_visibility_policy,
    load_subagent,
    save_enabled_experts,
    save_subagent,
    save_subagent_visibility_policy,
)
from app.services.runtime_tooling import READ_MEDIA_TOOL_PATH


@pytest.fixture
def temp_workspace(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        from app.services.agent import subagent_catalog

        original = subagent_catalog.WORKSPACE_DIR
        tmp_path = Path(tmpdir)
        monkeypatch.setattr(subagent_catalog, "WORKSPACE_DIR", tmp_path)
        yield tmp_path
        monkeypatch.setattr(subagent_catalog, "WORKSPACE_DIR", original)


class TestSubagentCatalog:
    def test_is_valid_subagent_name(self):
        assert is_valid_subagent_name("custom_coder") is True
        assert is_valid_subagent_name("data-cleaner") is True
        assert is_valid_subagent_name("my_agent_2") is True
        assert is_valid_subagent_name("2invalid") is False
        assert is_valid_subagent_name("") is False
        assert is_valid_subagent_name("a" * 65) is False
        assert is_valid_subagent_name("has space") is False

    def test_is_system_subagent_name(self):
        assert is_system_subagent_name("data_analyst") is True
        assert is_system_subagent_name("coder") is True
        assert is_system_subagent_name("researcher") is True
        assert is_system_subagent_name("reviewer") is True
        assert is_system_subagent_name("custom_coder") is False

    def test_save_and_load_user_scope(self, temp_workspace):
        """用户级子 Agent：持久化到文件系统，跨 session 复用。"""
        manifest = {
            "name": "custom_coder",
            "description": "自定义代码专家",
            "system_prompt": "你是一个代码专家...",
            "tools": ["app.agents.tools.read_media_tool:ReadMediaFile"],
            "model": "kimi-test",
        }
        path = save_subagent("user1", "custom_coder", manifest, scope="workspace")
        assert path is not None
        assert path.exists()
        assert path == (
            temp_workspace
            / "user1"
            / "user1"
            / ".aiasys"
            / "agent_config"
            / "subagents"
            / "custom_coder.toml"
        )

        loaded = load_subagent("user1", "custom_coder")
        assert loaded is not None
        assert loaded["name"] == "custom_coder"
        assert loaded["description"] == "自定义代码专家"
        assert loaded["system_prompt"] == "你是一个代码专家..."
        assert loaded["tools"] == [READ_MEDIA_TOOL_PATH]
        assert loaded["model"] == "kimi-test"

    def test_workspace_scope_uses_user_workspace_root(self, temp_workspace):
        """显式工作区级子 Agent 应写入用户目录下的真实工作区。"""
        manifest = {
            "name": "workspace_coder",
            "description": "工作区代码专家",
            "system_prompt": "你是这个工作区的代码专家。",
        }

        path = save_subagent(
            "user1",
            "workspace_coder",
            manifest,
            scope="workspace",
            workspace_id="workspace_a",
        )

        assert path == (
            temp_workspace
            / "user1"
            / "workspace_a"
            / ".aiasys"
            / "agent_config"
            / "subagents"
            / "workspace_coder.toml"
        )
        assert path.exists()
        assert not (
            temp_workspace
            / "workspace_a"
            / ".aiasys"
            / "agent_config"
            / "subagents"
            / "workspace_coder.toml"
        ).exists()

        loaded = load_subagent(
            "user1",
            "workspace_coder",
            workspace_id="workspace_a",
        )
        assert loaded is not None
        assert loaded["description"] == "工作区代码专家"

    def test_sqlite_record_has_priority_over_yaml_and_manifest_not_mutated(self, temp_workspace):
        """SQLite 记录优先于 YAML 镜像，保存时不修改调用方 manifest。"""
        manifest = {
            "name": "sqlite_first_agent",
            "description": "SQLite 版本",
            "system_prompt": "sqlite prompt",
            "tools": ["app.agents.tools.read_media_tool:ReadMediaFile"],
            "role": "reviewer",
            "model_reasoning_effort": "high",
            "agent_max_depth": 2,
            "agent_nickname_pool": ["Ada"],
            "fork_turns": 3,
        }
        original = dict(manifest)
        path = save_subagent(
            "user1",
            "sqlite_first_agent",
            manifest,
            scope="workspace",
        )
        assert manifest == original
        path.write_text(
            "\n".join(
                [
                    'version = 1',
                    '',
                    '[agent]',
                    'name = "sqlite_first_agent"',
                    'description = "TOML 版本"',
                    'system_prompt = "toml prompt"',
                ]
            ),
            encoding="utf-8",
        )

        loaded = load_subagent("user1", "sqlite_first_agent")
        assert loaded is not None
        assert loaded["description"] == "SQLite 版本"
        assert loaded["system_prompt"] == "sqlite prompt"
        assert loaded["role"] == "reviewer"
        assert loaded["model_reasoning_effort"] == "high"
        assert "agent_max_depth" not in loaded
        assert loaded["agent_nickname_pool"] == ["Ada"]
        assert loaded["fork_turns"] == 3

        assert delete_subagent("user1", "sqlite_first_agent", scope="workspace") is True
        assert load_subagent("user1", "sqlite_first_agent") is None

    def test_save_unknown_scope_rejected(self, temp_workspace):
        manifest = {
            "name": "temp_analyst",
            "description": "临时分析师",
            "system_prompt": "你是一个分析师...",
        }

        with pytest.raises(ValueError, match="仅支持 'global'/'workspace'"):
            save_subagent(
                "user1",
                "temp_analyst",
                manifest,
                scope="project",
            )

    def test_workspace_overrides_global(self, temp_workspace):
        """同名时，工作区级角色覆盖全局级角色。"""
        global_manifest = {
            "name": "my_agent",
            "description": "全局版本",
            "system_prompt": "全局提示词",
        }
        workspace_manifest = {
            "name": "my_agent",
            "description": "工作区版本",
            "system_prompt": "工作区提示词",
        }
        save_subagent("user1", "my_agent", global_manifest, scope="global")
        save_subagent("user1", "my_agent", workspace_manifest, scope="workspace")

        loaded = load_subagent("user1", "my_agent")
        assert loaded is not None
        assert loaded["description"] == "工作区版本"

    def test_list_subagents(self, temp_workspace):
        save_subagent(
            "user1",
            "user_agent",
            {"name": "user_agent", "description": "工作区级", "system_prompt": "u"},
            scope="workspace",
        )
        catalog = list_subagents("user1")
        assert "global" in catalog
        assert "workspace" in catalog

        workspace_names = {s["name"] for s in catalog["workspace"]}
        global_names = {s["name"] for s in catalog["global"]}

        assert "user_agent" in workspace_names
        # global 专家至少包含代码预设角色
        assert len(global_names) > 0
        assert "data_analyst" in global_names or "coder" in global_names

    def test_load_custom_subagents_for_manifest(self, temp_workspace):
        save_subagent(
            "user1",
            "custom1",
            {"name": "custom1", "description": "c1", "system_prompt": "s1"},
            scope="workspace",
        )
        customs = load_custom_subagents_for_manifest("user1")
        assert "custom1" in customs

    def test_delete_subagent(self, temp_workspace):
        save_subagent(
            "user1",
            "to_delete",
            {"name": "to_delete", "description": "d", "system_prompt": "s"},
            scope="workspace",
        )
        assert load_subagent("user1", "to_delete") is not None

        result = delete_subagent("user1", "to_delete", scope="workspace")
        assert result is True
        assert load_subagent("user1", "to_delete") is None

    def test_delete_nonexistent(self, temp_workspace):
        result = delete_subagent("user1", "nonexistent")
        assert result is False

    def test_delete_unknown_scope_returns_false(self, temp_workspace):
        result = delete_subagent("user1", "unknown_scope", scope="project")
        assert result is False

    def test_enabled_experts(self, temp_workspace):
        """启用/禁用专家列表读写。"""
        # 默认返回 None（全部启用）
        assert load_enabled_experts("user1") is None

        # 保存启用列表
        save_enabled_experts("user1", {"worker", "coder"})
        loaded = load_enabled_experts("user1")
        assert loaded == {"worker", "coder"}

        # 覆盖保存
        save_enabled_experts("user1", {"researcher"})
        loaded = load_enabled_experts("user1")
        assert loaded == {"researcher"}

    def test_visibility_policy_global_and_workspace_override(self, temp_workspace):
        """可见性策略按全局默认、工作区默认顺序合并。"""
        before = compute_subagent_visibility_fingerprint(
            user_id="user1",
            workspace_id="workspace_a",
        )

        save_subagent_visibility_policy(
            user_id="user1",
            role_id="coder",
            scope="global",
            host_selectable=False,
            default_enabled=False,
            lock_reason="全局默认隐藏",
        )
        global_policy = load_subagent_visibility_policy(
            user_id="user1",
            scope="global",
        )
        assert global_policy["coder"].host_selectable is False
        assert global_policy["coder"].default_enabled is False
        assert global_policy["coder"].visibility_source == "global"

        effective_global = resolve_subagent_visibility_policy(
            user_id="user1",
            role_id="coder",
            workspace_id="workspace_a",
        )
        assert effective_global.host_selectable is False
        assert effective_global.lock_reason == "全局默认隐藏"

        save_subagent_visibility_policy(
            user_id="user1",
            role_id="coder",
            scope="workspace",
            workspace_id="workspace_a",
            host_selectable=True,
            default_enabled=True,
            lock_reason="工作区覆盖",
        )
        effective_workspace = resolve_subagent_visibility_policy(
            user_id="user1",
            role_id="coder",
            workspace_id="workspace_a",
        )
        assert effective_workspace.host_selectable is True
        assert effective_workspace.default_enabled is True
        assert effective_workspace.visibility_source == "workspace"
        assert effective_workspace.lock_reason == "工作区覆盖"

        after = compute_subagent_visibility_fingerprint(
            user_id="user1",
            workspace_id="workspace_a",
        )
        assert before != after

    def test_system_builtin_role_is_dispatch_enabled_by_default(
        self,
        temp_workspace,
    ):
        """系统内置角色默认即可进入运行态派发，无需安装。"""
        catalog = list_subagents(
            "user1",
            workspace_id="workspace_a",
        )
        assert any(item["name"] == "coder" for item in catalog["global"])
        assert is_subagent_dispatch_enabled(
            user_id="user1",
            role_id="coder",
            workspace_id="workspace_a",
        ) is True

    def test_delete_default_builtin_experts_does_not_reinstall(self, temp_workspace):
        """用户移出默认内置专家后，不会被下一次目录加载重新安装。"""
        assert ensure_default_builtin_experts_installed("user1") == [
            "data_analyst",
            "researcher",
            "reviewer",
        ]

        for name in ("data_analyst", "researcher", "reviewer"):
            assert delete_subagent("user1", name, scope="global") is True

        assert ensure_default_builtin_experts_installed("user1") == []
        for name in ("data_analyst", "researcher", "reviewer"):
            assert is_subagent_installed_to_scope(
                user_id="user1",
                name=name,
                scope="global",
            ) is False

    def test_default_builtin_experts_install_core_set_only(self, temp_workspace):
        """用户默认层首次初始化只安装核心内置专家。"""
        installed = ensure_default_builtin_experts_installed("user1")

        assert installed == ["data_analyst", "researcher", "reviewer"]
        assert is_subagent_installed_to_scope(
            user_id="user1",
            name="data_analyst",
            scope="global",
        ) is True
        assert is_subagent_installed_to_scope(
            user_id="user1",
            name="researcher",
            scope="global",
        ) is True
        assert is_subagent_installed_to_scope(
            user_id="user1",
            name="reviewer",
            scope="global",
        ) is True
        assert is_subagent_installed_to_scope(
            user_id="user1",
            name="coder",
            scope="global",
        ) is False

        assert ensure_default_builtin_experts_installed("user1") == []

        save_subagent_visibility_policy(
            user_id="user1",
            role_id="coder",
            scope="global",
            host_selectable=True,
            default_enabled=True,
        )
        # 内置角色在 global 策略显式启用后即可派发，不需要实际安装文件
        assert is_subagent_dispatch_enabled(
            user_id="user1",
            role_id="coder",
            workspace_id="workspace_a",
        ) is True

        save_subagent_visibility_policy(
            user_id="user1",
            role_id="coder",
            scope="workspace",
            workspace_id="workspace_a",
            host_selectable=True,
            default_enabled=False,
        )
        # workspace 策略显式禁用后，内置角色也不可派发
        assert is_subagent_dispatch_enabled(
            user_id="user1",
            role_id="coder",
            workspace_id="workspace_a",
        ) is False

    def test_builtin_role_dispatch_no_installation_required(self, temp_workspace):
        """系统内置角色即使未安装到任何作用域，也应默认可派发。"""
        for name in ("coder", "data_analyst", "researcher", "reviewer"):
            assert is_subagent_installed_to_scope(
                user_id="user_no_install",
                name=name,
                scope="global",
            ) is False
            assert is_subagent_dispatch_enabled(
                user_id="user_no_install",
                role_id=name,
                workspace_id="workspace_a",
            ) is True, f"{name} 应默认可派发"

    def test_builtin_role_can_be_explicitly_disabled(self, temp_workspace):
        """系统内置角色可以通过显式策略禁用。"""
        save_subagent_visibility_policy(
            user_id="user_disabled",
            role_id="coder",
            scope="workspace",
            workspace_id="workspace_a",
            host_selectable=True,
            default_enabled=False,
        )
        assert is_subagent_dispatch_enabled(
            user_id="user_disabled",
            role_id="coder",
            workspace_id="workspace_a",
        ) is False

        save_subagent_visibility_policy(
            user_id="user_disabled2",
            role_id="coder",
            scope="workspace",
            workspace_id="workspace_a",
            host_selectable=False,
            default_enabled=True,
        )
        assert is_subagent_dispatch_enabled(
            user_id="user_disabled2",
            role_id="coder",
            workspace_id="workspace_a",
        ) is False

    def test_load_subagent_for_runtime_fallback_to_builtin_seed(self, temp_workspace):
        """未安装的内置角色运行时查找应 fallback 到代码预设 seed。"""
        manifest = load_subagent_for_runtime(
            user_id="user_seed",
            name="coder",
            session_id="s1",
            workspace_id="workspace_a",
        )
        assert manifest is not None
        assert manifest["name"] == "coder"
        assert "system_prompt" in manifest

        # 自定义未安装角色不应 fallback
        custom_manifest = load_subagent_for_runtime(
            user_id="user_seed",
            name="custom_not_installed",
            session_id="s1",
            workspace_id="workspace_a",
        )
        assert custom_manifest is None
