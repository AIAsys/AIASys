from __future__ import annotations

import json
from pathlib import Path

from app.services.llm.mcp_session_service import MCPSessionService
from app.services.workspace_registry import WorkspaceRegistryService
from app.services.session import SessionManager


def _write_metadata(path: Path, mode: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"session_id": path.parent.name, "mode": mode}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_mcp_session_service_uses_workspace_root_for_bound_conversation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry = WorkspaceRegistryService(tmp_path, session_manager=SessionManager(tmp_path))
    workspace = registry.create_workspace(
        user_id="local_default",
        workspace_id="task-mcp-root",
        title="任务 MCP Root",
        initial_conversation_id="conversation-mcp-001",
        initial_conversation_title="MCP 对话",
    )
    conversation = workspace.current_conversation
    assert conversation is not None

    service = MCPSessionService()
    service.workspace_dir = tmp_path
    monkeypatch.setattr(
        "app.services.llm.mcp_session_service.get_workspace_registry_service",
        lambda: registry,
    )
    monkeypatch.setattr("app.mcp.manager.WORKSPACE_DIR", tmp_path)

    _write_metadata(
        tmp_path / "local_default" / conversation.session_id / "metadata.json", "analysis"
    )

    from app.models.mcp import MCPServerConfig

    assert service.add_session_mcp_server(
        "local_default",
        conversation.session_id,
        MCPServerConfig(
            name="workspace-bound-mcp",
            type="streamable-http",
            url="https://example.com/mcp",
            enabled=True,
        ),
    )

    # 三层合并模型：server 定义存用户全局配置
    global_config = tmp_path / "local_default" / "global_workspace" / ".aiasys" / "mcp_config.json"
    assert global_config.exists()
    data = json.loads(global_config.read_text(encoding="utf-8"))
    assert "workspace-bound-mcp" in data["servers"]


def test_mcp_session_service_reads_current_session_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry = WorkspaceRegistryService(tmp_path, session_manager=SessionManager(tmp_path))
    workspace = registry.create_workspace(
        user_id="local_default",
        workspace_id="task-mcp-legacy",
        title="任务 MCP Legacy",
        initial_conversation_id="conversation-mcp-legacy",
        initial_conversation_title="Legacy 对话",
    )
    conversation = workspace.current_conversation
    assert conversation is not None

    service = MCPSessionService()
    service.workspace_dir = tmp_path
    monkeypatch.setattr(
        "app.services.llm.mcp_session_service.get_workspace_registry_service",
        lambda: registry,
    )
    monkeypatch.setattr("app.mcp.manager.WORKSPACE_DIR", tmp_path)

    session_dir = tmp_path / "local_default" / conversation.session_id
    _write_metadata(session_dir / "metadata.json", "analysis")

    # 先创建全局 store 定义
    from app.mcp import get_mcp_manager
    from app.mcp.models import MCPServerDefinition

    mgr = get_mcp_manager()
    mgr.save_store_server(
        "local_default",
        MCPServerDefinition(
            name="session-mcp",
            display_name="Session MCP",
            type="streamable-http",
            url="https://example.com/mcp",
        ),
        force=True,
    )

    servers = service.get_session_mcp_servers("local_default", conversation.session_id)
    names = [server.name for server in servers]
    assert "session-mcp" in names
