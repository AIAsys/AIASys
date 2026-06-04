"""
Agent 配置服务测试

测试用户配置隔离和合并逻辑。
"""

import json
import pytest
import tempfile
from pathlib import Path

import yaml
import app.services.agent_config.service as agent_config_service_module

from app.services.agent_config import (
    AgentConfigService,
    AgentMode,
    get_agent_config_service,
)
from app.services.agent_config.models import get_system_default_config_path
from app.services.agent.system_presets import (
    build_system_config_from_preset,
    resolve_system_agent_preset_from_path,
)
from app.services.workspace_registry import WorkspaceRegistryService


@pytest.fixture
def temp_workspace():
    """创建临时工作区"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def config_service(temp_workspace):
    """创建测试用的配置服务"""
    return AgentConfigService(workspace_root=temp_workspace)


@pytest.mark.asyncio
async def test_ensure_config_dir_exists(config_service, temp_workspace):
    """测试配置目录自动创建"""
    user_id = "test_user"
    
    # 确保目录不存在
    config_dir = temp_workspace / user_id / "global_workspace" / ".aiasys" / "agent_config"
    assert not config_dir.exists()
    
    # 调用 ensure 方法
    result = config_service._ensure_config_dir_exists(user_id)
    
    # 验证目录已创建
    assert result.exists()
    assert result.is_dir()
    assert result.name == "agent_config"


@pytest.mark.asyncio
async def test_save_and_load_prompt_override(config_service):
    """测试保存和读取提示词覆盖"""
    user_id = "test_user"
    mode = AgentMode.ANALYSIS
    content = "# 自定义提示词\n\n这是测试内容"
    
    # 保存提示词
    success = await config_service.save_prompt_override(
        mode=mode,
        user_id=user_id,
        content=content,
    )
    assert success is True
    
    # 读取用户配置
    user_config = await config_service.get_user_config(user_id)
    assert user_config is not None
    assert user_config.analysis is not None
    assert user_config.analysis.prompt is not None
    assert user_config.analysis.prompt.content == content
    assert user_config.analysis.enabled is True


@pytest.mark.asyncio
async def test_save_and_load_tools_config(config_service):
    """测试保存和读取工具配置"""
    user_id = "test_user"
    mode = AgentMode.ANALYSIS
    disabled_tools = [
        "app.agents.tools.local_ipython_box:LocalIPythonBox",
        "app.agents.tools.knowledge_tool:KnowledgeBaseQuery",
    ]
    
    # 保存工具配置
    success = await config_service.save_tools_config(
        mode=mode,
        user_id=user_id,
        disabled_tools=disabled_tools,
    )
    assert success is True
    
    # 读取用户配置
    user_config = await config_service.get_user_config(user_id)
    assert user_config is not None
    assert user_config.analysis is not None
    assert user_config.analysis.tools is not None
    assert user_config.analysis.tools.disabled_tools == disabled_tools


@pytest.mark.asyncio
async def test_new_writes_use_json_storage(config_service, temp_workspace):
    """新写入应落到 JSON，不再继续生成 YAML。"""
    user_id = "json_storage_user"
    mode = AgentMode.ANALYSIS

    assert await config_service.save_prompt_override(
        mode=mode,
        user_id=user_id,
        content="# JSON Prompt",
    )
    assert await config_service.save_tools_config(
        mode=mode,
        user_id=user_id,
        disabled_tools=["app.agents.tools.local_ipython_box:LocalIPythonBox"],
    )
    assert await config_service.save_runtime_config(
        mode=mode,
        user_id=user_id,
        reserved_context_size=20000,
        compaction_trigger_ratio=0.85,
    )

    config_root = temp_workspace / user_id / "global_workspace" / ".aiasys" / "agent_config"
    index_path = config_root / "user_config.json"
    tools_path = config_root / "analysis" / "tools.json"
    runtime_path = config_root / "analysis" / "runtime.json"

    assert index_path.exists()
    assert tools_path.exists()
    assert runtime_path.exists()
    assert not (config_root / "user_config.yaml").exists()
    assert not (config_root / "analysis" / "tools.yaml").exists()
    assert not (config_root / "analysis" / "runtime.yaml").exists()

    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert index_payload["modes"]["analysis"]["tools_path"] == "./analysis/tools.json"
    assert index_payload["modes"]["analysis"]["runtime_path"] == "./analysis/runtime.json"


@pytest.mark.asyncio
async def test_merge_config_with_user_override(config_service):
    """测试用户覆盖配置的合并"""
    user_id = "test_user"
    mode = AgentMode.ANALYSIS
    
    # 先保存用户配置
    await config_service.save_prompt_override(
        mode=mode,
        user_id=user_id,
        content="# 用户自定义提示词",
    )
    
    # 获取合并后的配置
    merged_config = await config_service.get_merged_config(
        mode=mode,
        user_id=user_id,
    )
    
    # 验证合并结果
    assert merged_config.is_customized is True
    assert merged_config.prompt_source == "user_default"
    assert "Agent Soul" in merged_config.system_prompt
    assert "用户自定义提示词" in merged_config.system_prompt
    assert merged_config.runtime_source == "system_default"
    assert merged_config.disabled_tools == []


@pytest.mark.asyncio
async def test_effective_version_snapshot_changes_after_session_override(config_service):
    """会话级覆盖应改变当前会话的生效配置。"""
    user_id = "version-snapshot-user"
    session_id = "version-snapshot-session"
    mode = AgentMode.ANALYSIS

    await config_service.save_prompt_override(
        mode=mode,
        user_id=user_id,
        content="# 用户默认版本",
    )
    base_config = await config_service.get_merged_config(
        mode=mode,
        user_id=user_id,
    )

    await config_service.save_prompt_override(
        mode=mode,
        user_id=user_id,
        content="# 当前任务版本",
        session_id=session_id,
    )
    session_config = await config_service.get_merged_config(
        mode=mode,
        user_id=user_id,
        session_id=session_id,
    )
    session_override = await config_service.get_session_override(
        mode=mode,
        user_id=user_id,
        session_id=session_id,
    )

    assert base_config.prompt_source == "user_default"
    assert "用户默认版本" in base_config.system_prompt
    assert session_config.prompt_source == "session_override"
    assert "用户默认版本" in session_config.system_prompt
    assert "当前任务版本" in session_config.system_prompt
    assert session_override is not None
    assert session_override.prompt is not None
    assert session_override.prompt.content == "# 当前任务版本"


@pytest.mark.asyncio
async def test_merge_config_without_user_override(config_service):
    """测试无用户覆盖时的系统默认配置"""
    user_id = "test_user_no_config"
    mode = AgentMode.ANALYSIS
    
    # 直接获取合并配置（用户未设置）
    merged_config = await config_service.get_merged_config(
        mode=mode,
        user_id=user_id,
    )
    
    # 验证使用系统默认
    assert merged_config.is_customized is False
    assert merged_config.prompt_source == "system_default"


@pytest.mark.asyncio
async def test_system_prompt_matches_baseline(config_service):
    """确认系统默认提示词来自配置文件且当无覆盖时生效"""
    user_id = "baseline_user"
    mode = AgentMode.ANALYSIS
    
    merged_config = await config_service.get_merged_config(
        mode=mode,
        user_id=user_id,
    )
    
    assert merged_config.prompt_source == "system_default"

    config_path = get_system_default_config_path(mode)
    preset = resolve_system_agent_preset_from_path(config_path)
    if preset is None and not config_path.exists():
        pytest.skip("system default config file missing in this environment")
    if preset is not None:
        config_data = build_system_config_from_preset(preset)
    else:
        config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    prompt_path_str = config_data.get("agent", {}).get("system_prompt_path", "")
    prompt_path = Path(prompt_path_str)
    if not prompt_path.is_absolute():
        prompt_path = config_path.parent / prompt_path
    if prompt_path.exists():
        expected_prompt = prompt_path.read_text(encoding="utf-8")
        assert expected_prompt in merged_config.system_prompt
        assert "Agent Soul" in merged_config.system_prompt
    else:
        assert "Agent Soul" in merged_config.system_prompt


@pytest.mark.asyncio
async def test_reset_to_default(config_service):
    """测试重置为系统默认"""
    user_id = "test_user"
    mode = AgentMode.ANALYSIS
    
    # 先保存配置
    await config_service.save_prompt_override(
        mode=mode,
        user_id=user_id,
        content="# 自定义提示词",
    )
    
    # 验证配置存在
    user_config = await config_service.get_user_config(user_id)
    assert user_config.analysis.enabled is True
    
    # 重置配置
    success = await config_service.reset_to_default(mode, user_id)
    assert success is True
    
    # 验证配置已删除
    user_config = await config_service.get_user_config(user_id)
    assert user_config is None or user_config.analysis is None


@pytest.mark.asyncio
async def test_validate_config_valid(config_service):
    """测试配置验证 - 有效配置"""
    user_id = "test_user"
    mode = AgentMode.ANALYSIS
    
    # 保存有效配置
    await config_service.save_prompt_override(
        mode=mode,
        user_id=user_id,
        content="# 有效提示词",
    )
    
    is_valid, errors = await config_service.validate_config(mode, user_id)
    
    assert is_valid is True
    assert len(errors) == 0


@pytest.mark.asyncio
async def test_analysis_mode_override(config_service):
    """测试 analysis 模式配置覆盖"""
    user_id = "test_user"

    await config_service.save_prompt_override(
        mode=AgentMode.ANALYSIS,
        user_id=user_id,
        content="# Analysis 配置",
    )

    user_config = await config_service.get_user_config(user_id)
    assert user_config.analysis.prompt.content == "# Analysis 配置"


@pytest.mark.asyncio
async def test_tools_merge_logic(config_service, monkeypatch):
    """测试工具合并逻辑"""
    system_tools = [
        "tool:a",
        "tool:b",
        "tool:c",
    ]
    
    from app.services.agent_config.models import ModeOverrides, ToolsConfig
    
    mode_overrides = ModeOverrides(
        enabled=True,
        tools=ToolsConfig(
            disabled_tools=["tool:b"],
            extra_tools=["tool:d"],
        ),
    )

    monkeypatch.setattr(
        agent_config_service_module,
        "_filter_supported_tools",
        lambda tool_names: list(tool_names),
    )
    monkeypatch.setattr(
        agent_config_service_module,
        "_is_supported_tool",
        lambda tool_name: True,
    )
    
    enabled, disabled, overrides, strategy = config_service._merge_tools(
        {"agent": {"tools": system_tools}},
        [mode_overrides],
    )
    
    assert "tool:a" in enabled
    assert "tool:b" not in enabled
    assert "tool:b" in disabled
    assert "tool:c" in enabled
    assert "tool:d" in enabled
    assert strategy == "auto"


@pytest.mark.asyncio
async def test_explicit_tool_selection_replaces_base_tools(config_service, monkeypatch):
    """显式工具选择应直接决定最终启用集合。"""
    system_tools = [
        "tool:a",
        "tool:b",
        "tool:c",
    ]

    from app.services.agent_config.models import ModeOverrides, ToolsConfig

    mode_overrides = ModeOverrides(
        enabled=True,
        tools=ToolsConfig(
            selection_mode="explicit",
            enabled_tools=["tool:c", "tool:d"],
            tool_strategy="search",
        ),
    )

    monkeypatch.setattr(
        agent_config_service_module,
        "_filter_supported_tools",
        lambda tool_names: list(tool_names),
    )
    monkeypatch.setattr(
        agent_config_service_module,
        "_is_supported_tool",
        lambda tool_name: True,
    )

    enabled, disabled, overrides, strategy = config_service._merge_tools(
        {"agent": {"tools": system_tools}},
        [mode_overrides],
    )

    assert enabled == ["tool:c", "tool:d"]
    assert "tool:a" in disabled
    assert "tool:b" in disabled
    assert strategy == "search"


@pytest.mark.asyncio
async def test_session_prompt_override_takes_precedence_over_user_default(config_service):
    """会话级提示词应覆盖用户默认层。"""
    user_id = "session_user"
    session_id = "session-001"
    mode = AgentMode.ANALYSIS

    await config_service.save_prompt_override(
        mode=mode,
        user_id=user_id,
        content="# 用户默认提示词",
    )
    await config_service.save_prompt_override(
        mode=mode,
        user_id=user_id,
        content="# 会话级提示词",
        session_id=session_id,
    )

    merged_config = await config_service.get_merged_config(
        mode=mode,
        user_id=user_id,
        session_id=session_id,
    )

    assert merged_config.prompt_source == "session_override"
    assert "用户默认提示词" in merged_config.system_prompt
    assert "会话级提示词" in merged_config.system_prompt
    assert merged_config.is_customized is True

    session_override = await config_service.get_session_override(
        mode=mode,
        user_id=user_id,
        session_id=session_id,
    )
    assert session_override is not None
    assert session_override.prompt is not None


@pytest.mark.asyncio
async def test_session_reset_falls_back_to_user_default(config_service):
    """会话级重置后应回退到用户默认，而不是系统基线。"""
    user_id = "session_reset_user"
    session_id = "session-002"
    mode = AgentMode.ANALYSIS

    await config_service.save_prompt_override(
        mode=mode,
        user_id=user_id,
        content="# 用户默认提示词",
    )
    await config_service.save_prompt_override(
        mode=mode,
        user_id=user_id,
        content="# 会话级提示词",
        session_id=session_id,
    )

    success = await config_service.reset_to_default(
        mode=mode,
        user_id=user_id,
        session_id=session_id,
    )
    assert success is True

    merged_config = await config_service.get_merged_config(
        mode=mode,
        user_id=user_id,
        session_id=session_id,
    )
    session_override = await config_service.get_session_override(
        mode=mode,
        user_id=user_id,
        session_id=session_id,
    )

    assert merged_config.prompt_source == "user_default"
    assert "用户默认提示词" in merged_config.system_prompt
    assert merged_config.is_customized is True
    assert session_override is None


@pytest.mark.asyncio
async def test_merged_prompt_includes_soul_and_project_profile(
    config_service,
    temp_workspace,
) -> None:
    user_id = "context-doc-user"
    workspace_id = "context-workspace"
    session_id = "context-session"
    mode = AgentMode.ANALYSIS

    registry = WorkspaceRegistryService(temp_workspace)
    registry.create_workspace(
        user_id=user_id,
        workspace_id=workspace_id,
        title="上下文项目",
        description="项目画像说明",
        initial_conversation_id=session_id,
    )

    soul_path = (
        temp_workspace
        / user_id
        / "global_workspace"
        / ".aiasys"
        / "agent_config"
        / "soul.md"
    )
    soul_path.write_text("# Soul\n\n- 稳定协作方式。", encoding="utf-8")

    profile_path = (
        temp_workspace
        / user_id
        / workspace_id
        / ".aiasys"
        / "project_profile.md"
    )
    profile_path.write_text("# Profile\n\n- 项目画像内容。", encoding="utf-8")

    await config_service.save_prompt_override(
        mode=mode,
        user_id=user_id,
        content="# 默认工作说明",
    )
    await config_service.save_prompt_override(
        mode=mode,
        user_id=user_id,
        content="# 当前会话覆盖",
        session_id=session_id,
    )

    merged_config = await config_service.get_merged_config(
        mode=mode,
        user_id=user_id,
        session_id=session_id,
        workspace_id=workspace_id,
    )

    prompt = merged_config.system_prompt
    assert "## Agent Soul" in prompt
    assert "稳定协作方式" in prompt
    assert "## 用户默认工作说明" in prompt
    assert "默认工作说明" in prompt
    assert "## Project Profile" in prompt
    assert "项目画像内容" in prompt
    assert "## 当前会话工作说明" in prompt
    assert "当前会话覆盖" in prompt
    assert prompt.index("稳定协作方式") < prompt.index("默认工作说明")
    assert prompt.index("默认工作说明") < prompt.index("项目画像内容")
    assert prompt.index("项目画像内容") < prompt.index("当前会话覆盖")


@pytest.mark.asyncio
async def test_session_tools_override_applies_after_user_default(config_service):
    """会话级工具覆盖应在用户默认层之后应用。"""
    user_id = "session_tools_user"
    session_id = "session-003"
    mode = AgentMode.ANALYSIS

    await config_service.save_tools_config(
        mode=mode,
        user_id=user_id,
        disabled_tools=["app.agents.tools.read_media_tool:ReadMediaFile"],
    )
    await config_service.save_tools_config(
        mode=mode,
        user_id=user_id,
        disabled_tools=["app.agents.tools.notebook_session_tool:ListSessionNotebooks"],
        extra_tools=["app.agents.tools.read_media_tool:ReadMediaFile"],
        session_id=session_id,
    )

    merged_config = await config_service.get_merged_config(
        mode=mode,
        user_id=user_id,
        session_id=session_id,
    )

    assert "app.agents.tools.read_media_tool:ReadMediaFile" in merged_config.enabled_tools
    assert "app.agents.tools.notebook_session_tool:ListSessionNotebooks" not in merged_config.enabled_tools
