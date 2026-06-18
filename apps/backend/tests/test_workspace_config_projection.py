from __future__ import annotations

import json
from pathlib import Path

from app.models.mcp import MCPServerConfig
from app.models.task_profile import build_task_profile_summary
from app.services.llm.mcp_session_service import MCPSessionService
from app.services.session import config_projection


def _get_isolated_mcp_manager(tmp_path: Path):
    """返回使用临时 WORKSPACE_DIR 且系统默认为空的 MCPManager，避免测试间污染。"""
    import app.mcp.manager as mcp_manager_module

    mcp_manager_module.WORKSPACE_DIR = tmp_path

    empty_defaults = tmp_path / "system_defaults.json"
    empty_defaults.write_text('{"version": 1, "servers": {}}', encoding="utf-8")
    mcp_manager_module.MCPManager.SYSTEM_DEFAULTS_PATH = empty_defaults

    from app.mcp import MCPManager

    return MCPManager()


def test_mcp_session_service_writes_global_mcp_config(tmp_path: Path) -> None:
    service = MCPSessionService()
    service.workspace_dir = tmp_path

    server = MCPServerConfig(
        name="demo",
        type="stdio",
        command="npx",
        args=["-y", "demo-mcp"],
        env={"DEMO_TOKEN": "abc"},
        enabled=True,
    )

    mgr = _get_isolated_mcp_manager(tmp_path)
    service._mgr = mgr

    assert service.add_session_mcp_server("user-1", "session-1", server) is True

    # 三层合并模型：server 定义存用户全局配置
    global_config = tmp_path / "user-1" / "global_workspace" / ".aiasys" / "mcp_config.json"
    assert global_config.exists()
    data = json.loads(global_config.read_text(encoding="utf-8"))
    assert "demo" in data["servers"]
    assert data["servers"]["demo"]["env"]["DEMO_TOKEN"] == "abc"

    sdk_config = service.get_sdk_config("user-1", "session-1")
    assert sdk_config == [
        {
            "mcpServers": {
                "demo": {
                    "command": "npx",
                    "args": ["-y", "demo-mcp"],
                    "env": {"DEMO_TOKEN": "abc"},
                }
            }
        }
    ]


def test_mcp_session_service_reads_workspace_mcp_config(
    tmp_path: Path,
) -> None:
    service = MCPSessionService()
    service.workspace_dir = tmp_path

    session_dir = tmp_path / "user-2" / "session-2"
    session_dir.mkdir(parents=True, exist_ok=True)

    # 三层合并模型：在工作区 mcp_config.json 中直接定义 server
    workspace_config = session_dir / ".aiasys" / "mcp_config.json"
    workspace_config.parent.mkdir(parents=True, exist_ok=True)
    workspace_config.write_text(
        json.dumps(
            {
                "version": 1,
                "servers": {
                    "demo": {
                        "name": "demo",
                        "display_name": "Demo",
                        "type": "stdio",
                        "command": "python",
                        "args": ["server.py"],
                        "headers": {},
                        "env": {},
                        "env_schema": {},
                        "timeout_ms": 30000,
                        "is_system_default": False,
                        "auto_attach_modes": [],
                    }
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    mgr = _get_isolated_mcp_manager(tmp_path)
    service._mgr = mgr

    servers = service.get_session_mcp_servers("user-2", "session-2")
    assert [server.name for server in servers] == ["demo"]


def test_workspace_database_mounts_round_trip(tmp_path: Path) -> None:
    session_dir = tmp_path / "user-db" / "workspace-db"

    written_path = config_projection.write_workspace_database_mount_data(
        session_dir,
        {
            "version": 1,
            "connector_ids": ["dbc_a", "dbc_b", "dbc_a", " "],
        },
    )
    assert written_path == session_dir / ".aiasys" / "database-mounts.json"
    assert written_path.exists()

    data = config_projection.read_workspace_database_mount_data(session_dir)
    assert data == {
        "version": 1,
        "connector_ids": ["dbc_a", "dbc_b"],
    }


def test_workspace_database_mounts_sqlite_has_priority_over_json(tmp_path: Path) -> None:
    session_dir = tmp_path / "user-db" / "workspace-db-sqlite"

    written_path = config_projection.write_workspace_database_mount_data(
        session_dir,
        {"connector_ids": ["dbc_sqlite"]},
    )
    written_path.write_text(
        '{"version": 1, "connector_ids": ["dbc_json"]}',
        encoding="utf-8",
    )

    data = config_projection.read_workspace_database_mount_data(session_dir)
    assert data == {
        "version": 1,
        "connector_ids": ["dbc_sqlite"],
    }

    config_projection.write_workspace_database_mount_data(
        session_dir,
        {"connector_ids": []},
    )
    assert config_projection.read_workspace_database_mount_data(session_dir) == {
        "version": 1,
        "connector_ids": [],
    }


import pytest


@pytest.mark.asyncio
async def test_build_runtime_config_projection_reports_pending_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_dir = tmp_path / "user-4" / "session-4"
    config_projection.ensure_workspace_layout(session_dir)

    skill_dir = session_dir / ".aiasys" / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("# demo", encoding="utf-8")
    # 三层合并模型：在工作区 mcp_config.json 中直接定义 server
    import app.mcp.manager as mcp_manager_module

    mcp_manager_module.WORKSPACE_DIR = tmp_path
    from app.mcp import MCPManager
    from app.mcp.models import MCPServerDefinition, MCPConfig

    mgr = MCPManager()
    workspace_config = MCPConfig(
        version=1,
        servers={
            "test_server": MCPServerDefinition(
                name="test_server",
                display_name="Test Server",
                type="streamable-http",
                url="https://mcp.example.com/mcp",
            )
        },
    )
    mgr._save_workspace_config(session_dir, workspace_config)

    monkeypatch.setattr(
        "app.mcp.get_mcp_manager",
        lambda: mgr,
    )

    config_projection.write_runtime_config_state(
        session_dir,
        applied_agent_config_version="agent-old",
        applied_capability_snapshot_version="cap-old",
    )

    async def _fake_agent_version(**_: object) -> str:
        return "agent-new"

    monkeypatch.setattr(
        config_projection,
        "compute_agent_config_version",
        _fake_agent_version,
    )
    monkeypatch.setattr(
        config_projection,
        "_list_available_knowledge_base_ids",
        lambda _user_id: [],
    )
    monkeypatch.setattr(
        config_projection,
        "_list_available_knowledge_graph_ids",
        lambda _user_id: [],
    )

    projection = await config_projection.build_runtime_config_projection(
        session_dir=session_dir,
        user_id="user-4",
        session_id="session-4",
        sandbox_mode="local",
        runtime_busy=True,
    )

    assert projection["can_edit_agent_config_now"] is False
    assert projection["agent_config_effect"] == "next_run_only"
    assert projection["config_sync_state"] == "pending"
    assert projection["rebuild_required"] is True
    assert projection["rebuild_required_reasons"] == [
        "agent_config_updated",
        "capabilities_updated",
    ]
    assert projection["current_agent_config_version"] == "agent-new"
    assert projection["applied_agent_config_version"] == "agent-old"
    assert projection["pending_agent_config_version"] == "agent-new"
    assert projection["current_capability_snapshot_version"] != "cap-old"
    assert projection["applied_capability_snapshot_version"] == "cap-old"
    assert projection["pending_capability_snapshot_version"] != "cap-old"
    expected_task_profile = build_task_profile_summary(
        execution_policy=None,
    )
    assert projection["workspace_capability_summary"] == {
        "skill_count": 1,
        "skill_names": ["demo-skill"],
        "mcp_server_count": 1,
        "enabled_mcp_server_count": 1,
        "enabled_mcp_server_names": ["test_server"],
        "mcp_config_version": 1,
        "mounted_knowledge_base_count": 0,
        "mounted_knowledge_base_ids": [],
        "mounted_knowledge_graph_count": 0,
        "mounted_knowledge_graph_ids": [],
        "primary_knowledge_graph_id": None,
        "execution_policy": expected_task_profile["execution_policy"],
    }


@pytest.mark.asyncio
async def test_build_runtime_config_projection_reports_aligned_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_dir = tmp_path / "user-5" / "session-5"
    config_projection.ensure_workspace_layout(session_dir)

    async def _fake_agent_version(**_: object) -> str:
        return "agent-same"

    monkeypatch.setattr(
        config_projection,
        "compute_agent_config_version",
        _fake_agent_version,
    )
    monkeypatch.setattr(
        config_projection,
        "_list_available_knowledge_base_ids",
        lambda _user_id: [],
    )
    monkeypatch.setattr(
        config_projection,
        "_list_available_knowledge_graph_ids",
        lambda _user_id: [],
    )
    monkeypatch.setattr(
        "app.mcp.get_mcp_manager",
        lambda: _get_isolated_mcp_manager(tmp_path),
    )

    current_capability_version = config_projection.compute_capability_snapshot_version(session_dir)
    config_projection.write_runtime_config_state(
        session_dir,
        applied_agent_config_version="agent-same",
        applied_capability_snapshot_version=current_capability_version,
    )

    projection = await config_projection.build_runtime_config_projection(
        session_dir=session_dir,
        user_id="user-5",
        session_id="session-5",
        sandbox_mode="local",
        runtime_busy=False,
    )

    assert projection["config_sync_state"] == "aligned"
    assert projection["rebuild_required"] is False
    assert projection["rebuild_required_reasons"] == []
    assert projection["pending_agent_config_version"] is None
    assert projection["pending_capability_snapshot_version"] is None
    expected_task_profile = build_task_profile_summary(
        execution_policy=None,
    )
    assert projection["workspace_capability_summary"] == {
        "skill_count": 0,
        "skill_names": [],
        "mcp_server_count": 0,
        "enabled_mcp_server_count": 0,
        "enabled_mcp_server_names": [],
        "mcp_config_version": 1,
        "mounted_knowledge_base_count": 0,
        "mounted_knowledge_base_ids": [],
        "mounted_knowledge_graph_count": 0,
        "mounted_knowledge_graph_ids": [],
        "primary_knowledge_graph_id": None,
        "execution_policy": expected_task_profile["execution_policy"],
    }
