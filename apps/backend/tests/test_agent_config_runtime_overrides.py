from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

import pytest

import app.api.routes.agent_config as agent_config_route
import app.core.config as core_config_module
import app.services.agent as agent_service_module
import app.services.agent.config as dynamic_agent_config_module
import app.services.agent.subagent_catalog as subagent_catalog_module
import app.services.agent_config as agent_config_package
import app.services.session.config_projection as config_projection_module
from app.services.agent.system_presets import get_local_system_preset_virtual_path
from app.models.user import UserInfo
from app.services.agent.mixins import session as session_module
from app.services.agent_config.models import AgentMode
from app.services.agent_config.service import AgentConfigService
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


CURRENT_USER = UserInfo(
    user_id="runtime-config-user",
    role="user",
    auth_provider="none",
)


def test_resolve_agent_system_default_paths_uses_preset_for_docker_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dynamic_agent_config_module, "SANDBOX_DEFAULT_MODE", "docker")
    monkeypatch.setattr(
        dynamic_agent_config_module,
        "is_sandbox_mode_enabled",
        lambda mode: mode == "docker",
    )

    config_path, prompt_path = dynamic_agent_config_module.resolve_agent_system_default_paths(
        sandbox_mode="docker",
    )

    assert config_path == get_local_system_preset_virtual_path("data_analysis")
    assert config_path.name == "data_analysis.preset"
    assert config_path.suffix != ".yaml"
    assert prompt_path.name == "general_host_prompt.md"


@pytest.mark.asyncio
async def test_runtime_config_merge_and_editor_state(tmp_path) -> None:
    service = AgentConfigService(workspace_root=tmp_path)

    base_config = await service.get_merged_config(
        mode=AgentMode.ANALYSIS,
        user_id=CURRENT_USER.user_id,
    )
    assert base_config.runtime_source == "system_default"
    assert base_config.runtime_config.reserved_context_size == 50000
    assert base_config.runtime_config.compaction_trigger_ratio == pytest.approx(0.85)

    assert await service.save_runtime_config(
        mode=AgentMode.ANALYSIS,
        user_id=CURRENT_USER.user_id,
        reserved_context_size=64000,
        compaction_trigger_ratio=0.72,
    )

    editor_before = await service.get_session_editor_config(
        mode=AgentMode.ANALYSIS,
        user_id=CURRENT_USER.user_id,
        session_id="runtime-session-1",
    )
    assert editor_before["runtime_source"] == "user_default"
    assert editor_before["has_local_runtime_override"] is False
    assert editor_before["reserved_context_size"] == 64000
    assert editor_before["compaction_trigger_ratio"] == pytest.approx(0.72)

    assert await service.save_runtime_config(
        mode=AgentMode.ANALYSIS,
        user_id=CURRENT_USER.user_id,
        session_id="runtime-session-1",
        reserved_context_size=32000,
    )

    merged_session = await service.get_merged_config(
        mode=AgentMode.ANALYSIS,
        user_id=CURRENT_USER.user_id,
        session_id="runtime-session-1",
    )
    assert merged_session.runtime_source == "session_override"
    assert merged_session.runtime_config.reserved_context_size == 32000
    assert merged_session.runtime_config.compaction_trigger_ratio == pytest.approx(0.72)

    editor_after = await service.get_session_editor_config(
        mode=AgentMode.ANALYSIS,
        user_id=CURRENT_USER.user_id,
        session_id="runtime-session-1",
    )
    assert editor_after["runtime_source"] == "session_override"
    assert editor_after["has_local_runtime_override"] is True


@pytest.mark.asyncio
async def test_update_runtime_rejects_session_scope_edit_while_session_running(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AgentConfigService(workspace_root=tmp_path)
    monkeypatch.setattr(agent_config_route, "get_agent_config_service", lambda: service)

    session_id = "runtime-locked-session"
    session_key = f"{CURRENT_USER.user_id}/{session_id}"
    agent_config_route.agent_service._active_sessions[session_key] = object()

    try:
        with pytest.raises(agent_config_route.HTTPException) as exc:
            await agent_config_route.update_runtime(
                mode=AgentMode.ANALYSIS,
                request=agent_config_route.RuntimeConfigUpdateRequest(
                    reserved_context_size=48000,
                    compaction_trigger_ratio=0.7,
                ),
                session_id=session_id,
                current_user=CURRENT_USER,
            )
    finally:
        agent_config_route.agent_service._active_sessions.pop(session_key, None)

    assert exc.value.status_code == 409
    assert "正在执行中" in str(exc.value.detail)


def test_session_get_config_projects_runtime_loop_control(monkeypatch, tmp_path) -> None:
    service = AgentConfigService(workspace_root=tmp_path)
    user_id = CURRENT_USER.user_id

    import asyncio

    asyncio.run(
        service.save_runtime_config(
            mode=AgentMode.ANALYSIS,
            user_id=user_id,
            session_id="runtime-session-2",
            reserved_context_size=28000,
            compaction_trigger_ratio=0.68,
        )
    )

    class StubLLMConfigService:
        def get_full_config(self, _user_id: str):
            return {
                "providers": {
                    "provider-1": {
                        "type": "anthropic_messages",
                        "base_url": "https://api.example.com/v1",
                        "api_key": "test-key",
                    }
                },
                "models": {
                    "model-1": {
                        "provider": "provider-1",
                        "model": "kimi-k2",
                        "max_context_size": 262144,
                    }
                },
                "default_model": "model-1",
            }

    class DummyService(session_module.SessionMixin):
        pass

    monkeypatch.setattr(session_module, "get_llm_config_service", lambda: StubLLMConfigService())
    monkeypatch.setattr(session_module, "get_agent_config_service", lambda: service)

    dummy_service = DummyService()
    config = dummy_service._get_config(
        model=None,
        user_id=user_id,
        session_id="runtime-session-2",
    )

    assert config.default_model == "model-1"
    assert config.loop_control.reserved_context_size == 28000
    assert config.loop_control.compaction_trigger_ratio == pytest.approx(0.68)
    assert config.models["model-1"].max_context_size == 262144


@pytest.mark.asyncio
async def test_compute_agent_config_version_tracks_soul_and_project_profile(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AgentConfigService(workspace_root=tmp_path)
    registry = WorkspaceRegistryService(tmp_path)
    workspace = registry.create_workspace(
        user_id=CURRENT_USER.user_id,
        workspace_id="soul-version-workspace",
        title="Soul Version",
        initial_conversation_id="soul-version-session",
    )
    assert workspace.current_conversation is not None
    session_dir = tmp_path / CURRENT_USER.user_id / "soul-version-session"

    monkeypatch.setattr(
        config_projection_module,
        "get_agent_config_service",
        lambda: service,
    )

    version_before = await config_projection_module.compute_agent_config_version(
        user_id=CURRENT_USER.user_id,
        session_id="soul-version-session",
        sandbox_mode="local",
        session_dir=session_dir,
    )

    soul_path = (
        tmp_path
        / CURRENT_USER.user_id
        / "global_workspace"
        / ".aiasys"
        / "agent_config"
        / "soul.md"
    )
    soul_path.write_text("# Soul\n\n- changed", encoding="utf-8")
    version_after_soul = await config_projection_module.compute_agent_config_version(
        user_id=CURRENT_USER.user_id,
        session_id="soul-version-session",
        sandbox_mode="local",
        session_dir=session_dir,
    )

    profile_path = (
        tmp_path
        / CURRENT_USER.user_id
        / "soul-version-workspace"
        / ".aiasys"
        / "project_profile.md"
    )
    profile_path.write_text("# Profile\n\n- changed", encoding="utf-8")
    version_after_profile = await config_projection_module.compute_agent_config_version(
        user_id=CURRENT_USER.user_id,
        session_id="soul-version-session",
        sandbox_mode="local",
        session_dir=session_dir,
    )

    assert version_before != version_after_soul
    assert version_after_soul != version_after_profile


@pytest.mark.asyncio
async def test_generate_dynamic_agent_config_filters_enabled_experts_and_renders_role_prompts(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = tmp_path / "agent-config"
    config_dir.mkdir(parents=True, exist_ok=True)

    host_prompt = config_dir / "host_prompt.md"
    host_prompt.write_text("HOST ${PYTHON_VERSION}", encoding="utf-8")
    reviewer_prompt = config_dir / "reviewer_prompt.md"
    reviewer_prompt.write_text("REVIEWER ${PYTHON_VERSION}", encoding="utf-8")
    worker_prompt = config_dir / "worker_prompt.md"
    worker_prompt.write_text("WORKER ${PYTHON_VERSION}", encoding="utf-8")

    host_config = config_dir / "host.toml"
    host_config.write_text(
        """version = 1
[agent]
name = "host"
model = "host-model"
tools = []
system_prompt_path = "./host_prompt.md"

[agent.subagents]
worker = { path = "./worker.toml", description = "worker" }
reviewer = { path = "./reviewer.toml", description = "reviewer" }
""",
        encoding="utf-8",
    )
    (config_dir / "worker.toml").write_text(
        """version = 1
[agent]
name = "worker"
model = "worker-model"
tools = []
system_prompt_path = "./worker_prompt.md"
""",
        encoding="utf-8",
    )
    (config_dir / "reviewer.toml").write_text(
        """version = 1
[agent]
name = "reviewer"
model = "reviewer-model"
tools = []
system_prompt_path = "./reviewer_prompt.md"
""",
        encoding="utf-8",
    )

    session_manager = SessionManager(tmp_path)
    session_manager.create_session(
        session_id="expert-filter-session",
        user_id=CURRENT_USER.user_id,
        title="专家过滤",
        sandbox_mode="local",
        enabled_expert_role_ids=["reviewer"],
    )

    service = AgentConfigService(workspace_root=tmp_path)
    monkeypatch.setattr(dynamic_agent_config_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(core_config_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(agent_service_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(subagent_catalog_module, "WORKSPACE_DIR", tmp_path)
    subagent_catalog_module.enable_builtin_subagent_to_scope(
        user_id=CURRENT_USER.user_id,
        name="reviewer",
        scope="global",
    )
    monkeypatch.setattr(
        dynamic_agent_config_module,
        "resolve_agent_system_default_paths",
        lambda **_: (host_config, host_prompt),
    )
    monkeypatch.setattr(
        dynamic_agent_config_module,
        "_get_execution_env_info",
        lambda **_: {
            "PYTHON_VERSION": "3.12.9",
            "PACKAGE_LIST": "demo",
            "PYTHON_PATH": "/usr/bin/python",
            "PIP_PATH": "/usr/bin/pip",
        },
    )
    monkeypatch.setattr(
        agent_config_package,
        "get_agent_config_service",
        lambda: service,
    )
    generated_path = await dynamic_agent_config_module.generate_dynamic_agent_config(
        session_id="expert-filter-session",
        user_id=CURRENT_USER.user_id,
    )
    assert generated_path.parent == (
        tmp_path
        / CURRENT_USER.user_id
        / "expert-filter-session"
        / ".aiasys"
        / "session"
        / "runtime-agent-config"
    )

    import tomllib

    generated_payload = tomllib.loads(generated_path.read_text(encoding="utf-8"))
    generated_subagents = generated_payload["agent"]["subagents"]

    assert list(generated_subagents.keys()) == ["reviewer"]
    reviewer_generated_path = generated_subagents["reviewer"]["path"]
    reviewer_payload = tomllib.loads(
        dynamic_agent_config_module.Path(reviewer_generated_path).read_text(encoding="utf-8")
    )
    host_generated_prompt = dynamic_agent_config_module.Path(
        generated_payload["agent"]["system_prompt_path"]
    )
    reviewer_generated_prompt = dynamic_agent_config_module.Path(
        reviewer_payload["agent"]["system_prompt_path"]
    )

    host_prompt_text = host_generated_prompt.read_text(encoding="utf-8")
    assert "HOST 3.12.9" in host_prompt_text
    assert "Agent Soul" in host_prompt_text
    assert reviewer_generated_prompt.read_text(encoding="utf-8") == "REVIEWER 3.12.9"
    assert reviewer_generated_prompt.read_text(encoding="utf-8") != host_generated_prompt.read_text(
        encoding="utf-8"
    )


@pytest.mark.asyncio
async def test_build_dynamic_agent_manifest_respects_subagent_visibility_policy(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_manager = SessionManager(tmp_path)
    service = AgentConfigService(workspace_root=tmp_path)
    workspace_id = "visibility-runtime-workspace"
    workspace_dir = tmp_path / CURRENT_USER.user_id / workspace_id
    workspace_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(dynamic_agent_config_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(core_config_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(agent_service_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(subagent_catalog_module, "WORKSPACE_DIR", tmp_path)
    subagent_catalog_module.enable_builtin_subagent_to_scope(
        user_id=CURRENT_USER.user_id,
        name="reviewer",
        scope="workspace",
        workspace_id=workspace_id,
    )
    session_manager.create_session(
        session_id="visibility-runtime-session",
        user_id=CURRENT_USER.user_id,
        title="运行态可见性",
        sandbox_mode="local",
        workspace_id=workspace_id,
        enabled_expert_role_ids=["coder", "reviewer"],
    )
    subagent_catalog_module.save_subagent_visibility_policy(
        user_id=CURRENT_USER.user_id,
        role_id="coder",
        scope="workspace",
        workspace_id=workspace_id,
        host_selectable=False,
        default_enabled=False,
    )

    class StubWorkspaceRegistry:
        def find_workspace_id_by_session_id(self, user_id: str, session_id: str) -> str:
            assert user_id == CURRENT_USER.user_id
            assert session_id == "visibility-runtime-session"
            return workspace_id

        def get_workspace_root(self, user_id: str, requested_workspace_id: str) -> Path:
            assert user_id == CURRENT_USER.user_id
            assert requested_workspace_id == workspace_id
            return workspace_dir

    monkeypatch.setattr(
        "app.services.workspace_registry.get_workspace_registry_service",
        lambda: StubWorkspaceRegistry(),
    )
    monkeypatch.setattr(
        dynamic_agent_config_module,
        "resolve_agent_system_default_paths",
        lambda **_: (
            get_local_system_preset_virtual_path("data_analysis"),
            Path(__file__).resolve().parents[1]
            / "app"
            / "agents"
            / "local_sandbox_agent_config"
            / "general_host_prompt.md",
        ),
    )
    monkeypatch.setattr(
        agent_config_package,
        "get_agent_config_service",
        lambda: service,
    )

    manifest = await dynamic_agent_config_module.build_dynamic_agent_manifest(
        session_id="visibility-runtime-session",
        user_id=CURRENT_USER.user_id,
        sandbox_mode="local",
    )

    subagents = manifest.get("subagents") or {}
    assert "reviewer" in subagents
    assert "coder" not in subagents


@pytest.mark.asyncio
async def test_compute_agent_config_version_tracks_expert_prompt_changes(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = tmp_path / "agent-config-version"
    config_dir.mkdir(parents=True, exist_ok=True)

    host_prompt = config_dir / "host_prompt.md"
    host_prompt.write_text("HOST ${PYTHON_VERSION}", encoding="utf-8")
    reviewer_prompt = config_dir / "reviewer_prompt.md"
    reviewer_prompt.write_text("REVIEWER V1", encoding="utf-8")
    worker_prompt = config_dir / "worker_prompt.md"
    worker_prompt.write_text("WORKER V1", encoding="utf-8")

    host_config = config_dir / "host.toml"
    host_config.write_text(
        """version = 1
[agent]
name = "host"
model = "host-model"
tools = []
system_prompt_path = "./host_prompt.md"

[agent.subagents]
worker = { path = "./worker.toml", description = "worker" }
reviewer = { path = "./reviewer.toml", description = "reviewer" }
""",
        encoding="utf-8",
    )
    (config_dir / "worker.toml").write_text(
        """version = 1
[agent]
name = "worker"
model = "worker-model"
tools = []
system_prompt_path = "./worker_prompt.md"
""",
        encoding="utf-8",
    )
    (config_dir / "reviewer.toml").write_text(
        """version = 1
[agent]
name = "reviewer"
model = "reviewer-model"
tools = []
system_prompt_path = "./reviewer_prompt.md"
""",
        encoding="utf-8",
    )

    session_dir = tmp_path / CURRENT_USER.user_id / "expert-version-session"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "metadata.json").write_text(
        json.dumps(
            {
                "enabled_expert_role_ids": ["reviewer"],
                "execution_policy": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    service = AgentConfigService(workspace_root=tmp_path)
    monkeypatch.setattr(
        dynamic_agent_config_module,
        "resolve_agent_system_default_paths",
        lambda **_: (host_config, host_prompt),
    )
    monkeypatch.setattr(
        config_projection_module,
        "get_agent_config_service",
        lambda: service,
    )

    version_before = await config_projection_module.compute_agent_config_version(
        user_id=CURRENT_USER.user_id,
        session_id="expert-version-session",
        sandbox_mode="local",
        session_dir=session_dir,
    )

    reviewer_prompt.write_text("REVIEWER V2", encoding="utf-8")

    version_after = await config_projection_module.compute_agent_config_version(
        user_id=CURRENT_USER.user_id,
        session_id="expert-version-session",
        sandbox_mode="local",
        session_dir=session_dir,
    )

    assert version_before != version_after


@pytest.mark.asyncio
async def test_build_dynamic_agent_manifest_applies_session_role_tool_subset_for_presets(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_analyst_tool_subset = [
        "app.agents.tools.notebook_session_tool:ListSessionNotebooks",
        "app.agents.tools.notebook_session_tool:ReadNotebookOutputs",
    ]

    session_manager = SessionManager(tmp_path)
    service = AgentConfigService(workspace_root=tmp_path)
    monkeypatch.setattr(dynamic_agent_config_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(core_config_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(agent_service_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(subagent_catalog_module, "WORKSPACE_DIR", tmp_path)
    workspace_id = "preset-expert-tool-workspace"
    workspace_dir = tmp_path / CURRENT_USER.user_id / workspace_id
    workspace_dir.mkdir(parents=True, exist_ok=True)
    session_manager.create_session(
        session_id="preset-expert-tool-session",
        user_id=CURRENT_USER.user_id,
        title="预设专家工具裁剪",
        sandbox_mode="local",
        workspace_id=workspace_id,
        enabled_expert_role_ids=["data_analyst"],
        expert_role_tool_ids={"data_analyst": list(data_analyst_tool_subset)},
    )
    subagent_catalog_module.enable_builtin_subagent_to_scope(
        user_id=CURRENT_USER.user_id,
        name="data_analyst",
        scope="workspace",
        workspace_id=workspace_id,
    )

    class StubWorkspaceRegistry:
        def find_workspace_id_by_session_id(self, user_id: str, session_id: str) -> str:
            assert user_id == CURRENT_USER.user_id
            assert session_id == "preset-expert-tool-session"
            return workspace_id

        def get_workspace_root(self, user_id: str, requested_workspace_id: str) -> Path:
            assert user_id == CURRENT_USER.user_id
            assert requested_workspace_id == workspace_id
            return workspace_dir

    monkeypatch.setattr(
        "app.services.workspace_registry.get_workspace_registry_service",
        lambda: StubWorkspaceRegistry(),
    )
    monkeypatch.setattr(
        dynamic_agent_config_module,
        "resolve_agent_system_default_paths",
        lambda **_: (
            get_local_system_preset_virtual_path("data_analysis"),
            Path(__file__).resolve().parents[1]
            / "app"
            / "agents"
            / "local_sandbox_agent_config"
            / "general_host_prompt.md",
        ),
    )
    monkeypatch.setattr(
        agent_config_package,
        "get_agent_config_service",
        lambda: service,
    )

    manifest = await dynamic_agent_config_module.build_dynamic_agent_manifest(
        session_id="preset-expert-tool-session",
        user_id=CURRENT_USER.user_id,
        sandbox_mode="local",
    )

    assert list((manifest.get("subagents") or {}).keys()) == ["data_analyst"]
    data_analyst_manifest = manifest["subagents"]["data_analyst"]["agent_manifest"]
    assert data_analyst_manifest.get("tool_policy") == "allowlist"
    assert data_analyst_manifest.get("tools") == data_analyst_tool_subset
    assert data_analyst_manifest.get("allowed_tools") == data_analyst_tool_subset


@pytest.mark.asyncio
async def test_build_dynamic_agent_manifest_uses_explicit_tool_selection(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_manager = SessionManager(tmp_path)
    session_manager.create_session(
        session_id="explicit-tool-selection-session",
        user_id=CURRENT_USER.user_id,
        title="显式工具选择",
        sandbox_mode="local",
    )

    service = AgentConfigService(workspace_root=tmp_path)
    assert await service.save_tools_config(
        mode=AgentMode.ANALYSIS,
        user_id=CURRENT_USER.user_id,
        session_id="explicit-tool-selection-session",
        enabled_tools=[
            "app.agents.tools.notebook_session_tool:ReadNotebookOutputs",
        ],
        tool_strategy="search",
    )
    monkeypatch.setattr(dynamic_agent_config_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(core_config_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(agent_service_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(subagent_catalog_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(
        dynamic_agent_config_module,
        "resolve_agent_system_default_paths",
        lambda **_: (
            get_local_system_preset_virtual_path("data_analysis"),
            Path(__file__).resolve().parents[1]
            / "app"
            / "agents"
            / "local_sandbox_agent_config"
            / "general_host_prompt.md",
        ),
    )
    monkeypatch.setattr(
        agent_config_package,
        "get_agent_config_service",
        lambda: service,
    )

    manifest = await dynamic_agent_config_module.build_dynamic_agent_manifest(
        session_id="explicit-tool-selection-session",
        user_id=CURRENT_USER.user_id,
        sandbox_mode="local",
    )

    tools = list(manifest.get("tools") or [])

    assert tools == [
        "app.agents.tools.notebook_session_tool:ReadNotebookOutputs",
    ]
    assert manifest.get("tool_strategy") == "search"
    assert len(tools) == len(set(tools))


@pytest.mark.asyncio
async def test_compute_agent_config_version_tracks_expert_tool_subset_changes(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_dir = tmp_path / CURRENT_USER.user_id / "expert-tool-version-session"
    session_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = session_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "enabled_expert_role_ids": ["worker"],
                "expert_role_tool_ids": {
                    "worker": [
                        "app.agents.tools.notebook_session_tool:ListSessionNotebooks",
                    ],
                },
                "execution_policy": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    service = AgentConfigService(workspace_root=tmp_path)
    host_prompt = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "agents"
        / "local_sandbox_agent_config"
        / "general_host_prompt.md"
    )
    monkeypatch.setattr(
        config_projection_module,
        "get_agent_config_service",
        lambda: service,
    )
    monkeypatch.setattr(
        dynamic_agent_config_module,
        "resolve_agent_system_default_paths",
        lambda **_: (
            get_local_system_preset_virtual_path("data_analysis"),
            host_prompt,
        ),
    )

    version_before = await config_projection_module.compute_agent_config_version(
        user_id=CURRENT_USER.user_id,
        session_id="expert-tool-version-session",
        sandbox_mode="local",
        session_dir=session_dir,
    )

    metadata_path.write_text(
        json.dumps(
            {
                "enabled_expert_role_ids": ["worker"],
                "expert_role_tool_ids": {
                    "worker": [
                        "app.agents.tools.notebook_session_tool:ListSessionNotebooks",
                        "app.agents.tools.notebook_session_tool:ReadNotebookOutputs",
                    ],
                },
                "execution_policy": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    version_after = await config_projection_module.compute_agent_config_version(
        user_id=CURRENT_USER.user_id,
        session_id="expert-tool-version-session",
        sandbox_mode="local",
        session_dir=session_dir,
    )

    assert version_before != version_after


@pytest.mark.asyncio
async def test_compute_agent_config_version_tracks_subagent_visibility_policy(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = "expert-visibility-version-session"
    workspace_id = "expert-visibility-version-workspace"
    session_dir = tmp_path / CURRENT_USER.user_id / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / CURRENT_USER.user_id / workspace_id).mkdir(parents=True, exist_ok=True)
    metadata_path = session_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "workspace_id": workspace_id,
                "enabled_expert_role_ids": None,
                "execution_policy": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    service = AgentConfigService(workspace_root=tmp_path)
    host_prompt = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "agents"
        / "local_sandbox_agent_config"
        / "general_host_prompt.md"
    )
    monkeypatch.setattr(subagent_catalog_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(
        config_projection_module,
        "get_agent_config_service",
        lambda: service,
    )
    monkeypatch.setattr(
        dynamic_agent_config_module,
        "resolve_agent_system_default_paths",
        lambda **_: (
            get_local_system_preset_virtual_path("data_analysis"),
            host_prompt,
        ),
    )

    version_before = await config_projection_module.compute_agent_config_version(
        user_id=CURRENT_USER.user_id,
        session_id=session_id,
        sandbox_mode="local",
        session_dir=session_dir,
    )

    subagent_catalog_module.save_subagent_visibility_policy(
        user_id=CURRENT_USER.user_id,
        role_id="reviewer",
        scope="workspace",
        workspace_id=workspace_id,
        host_selectable=False,
        default_enabled=False,
    )

    version_after = await config_projection_module.compute_agent_config_version(
        user_id=CURRENT_USER.user_id,
        session_id=session_id,
        sandbox_mode="local",
        session_dir=session_dir,
    )

    assert version_before != version_after
