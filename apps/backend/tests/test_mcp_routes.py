"""MCP API 路由测试（三层合并模型）"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
TEST_USER_ID = "local_default"


def _empty_system_defaults_path(tmp_path: Path) -> Path:
    """创建空的系统默认 MCP 配置文件，避免测试依赖真实 system_defaults.json。"""
    path = tmp_path / "system_defaults.json"
    path.write_text('{"version": 1, "servers": {}}', encoding="utf-8")
    return path


class TestMCPStoreRoutes:
    def test_list_store_servers_empty(self, tmp_path: Path, monkeypatch):
        """空 store 返回空列表"""
        monkeypatch.setattr("app.mcp.manager.WORKSPACE_DIR", tmp_path)
        monkeypatch.setattr("app.api.routes.mcp.WORKSPACE_DIR", tmp_path)

        response = client.get("/api/mcp/store")
        assert response.status_code == 200
        data = response.json()
        assert data["servers"] == []
        assert data["total"] == 0

    def test_add_and_list_store_server(self, tmp_path: Path, monkeypatch):
        """添加 server 后可以在列表中看到"""
        monkeypatch.setattr("app.mcp.manager.WORKSPACE_DIR", tmp_path)
        monkeypatch.setattr("app.api.routes.mcp.WORKSPACE_DIR", tmp_path)

        response = client.post(
            "/api/mcp/store",
            json={
                "name": "test-tavily",
                "type": "streamable-http",
                "url": "https://tavily.example.com/mcp",
                "enabled": True,
            },
        )
        assert response.status_code == 200

        response = client.get("/api/mcp/store")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["servers"][0]["name"] == "test-tavily"

    def test_delete_store_server(self, tmp_path: Path, monkeypatch):
        """删除 server 后从列表消失"""
        monkeypatch.setattr("app.mcp.manager.WORKSPACE_DIR", tmp_path)
        monkeypatch.setattr("app.api.routes.mcp.WORKSPACE_DIR", tmp_path)

        client.post(
            "/api/mcp/store",
            json={
                "name": "to-delete",
                "type": "stdio",
                "command": "npx",
                "enabled": True,
            },
        )

        response = client.delete("/api/mcp/store/to-delete")
        assert response.status_code == 200

        response = client.get("/api/mcp/store")
        names = [s["name"] for s in response.json()["servers"]]
        assert "to-delete" not in names

    def test_delete_nonexistent_server(self, tmp_path: Path, monkeypatch):
        """删除不存在的 server 返回 404"""
        monkeypatch.setattr("app.mcp.manager.WORKSPACE_DIR", tmp_path)
        monkeypatch.setattr("app.api.routes.mcp.WORKSPACE_DIR", tmp_path)

        response = client.delete("/api/mcp/store/nonexistent")
        assert response.status_code == 404


class TestMCPWorkspaceRoutes:
    def test_list_workspace_servers(self, tmp_path: Path, monkeypatch):
        """工作区 MCP 列表返回合并后的配置"""
        from app.mcp import MCPManager
        from app.mcp.models import MCPServerDefinition

        monkeypatch.setattr("app.mcp.manager.WORKSPACE_DIR", tmp_path)
        monkeypatch.setattr("app.api.routes.mcp.WORKSPACE_DIR", tmp_path)
        monkeypatch.setattr(
            "app.mcp.manager.MCPManager.SYSTEM_DEFAULTS_PATH",
            _empty_system_defaults_path(tmp_path),
        )

        mgr = MCPManager()
        mgr.save_store_server(
            TEST_USER_ID,
            MCPServerDefinition(
                name="ws-server",
                display_name="WS Server",
                type="streamable-http",
                url="https://example.com",
            ),
            force=True,
        )
        monkeypatch.setattr("app.api.routes.mcp.get_mcp_manager", lambda: mgr)

        workspace_path = tmp_path / TEST_USER_ID / "workspace-1"
        workspace_path.mkdir(parents=True, exist_ok=True)

        response = client.get("/api/mcp/workspaces/workspace-1")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["servers"][0]["name"] == "ws-server"

    def test_workspace_overrides_global(self, tmp_path: Path, monkeypatch):
        """工作区配置覆盖全局配置"""
        from app.mcp import MCPManager
        from app.mcp.models import MCPServerDefinition

        monkeypatch.setattr("app.mcp.manager.WORKSPACE_DIR", tmp_path)
        monkeypatch.setattr("app.api.routes.mcp.WORKSPACE_DIR", tmp_path)
        monkeypatch.setattr(
            "app.mcp.manager.MCPManager.SYSTEM_DEFAULTS_PATH",
            _empty_system_defaults_path(tmp_path),
        )

        mgr = MCPManager()
        mgr.save_store_server(
            TEST_USER_ID,
            MCPServerDefinition(
                name="override-server",
                display_name="Override Server",
                type="streamable-http",
                url="https://global.example.com",
            ),
            force=True,
        )
        workspace_path = tmp_path / TEST_USER_ID / "workspace-2"
        workspace_path.mkdir(parents=True, exist_ok=True)
        mgr.save_workspace_server(
            workspace_path,
            MCPServerDefinition(
                name="override-server",
                display_name="Override Server",
                type="streamable-http",
                url="https://workspace.example.com",
            ),
        )
        monkeypatch.setattr("app.api.routes.mcp.get_mcp_manager", lambda: mgr)

        response = client.get("/api/mcp/workspaces/workspace-2")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["servers"][0]["url"] == "https://workspace.example.com"

    def test_add_remove_workspace_server(self, tmp_path: Path, monkeypatch):
        """添加和移除工作区 MCP server"""
        from app.mcp import MCPManager
        from app.mcp.models import MCPServerDefinition

        monkeypatch.setattr("app.mcp.manager.WORKSPACE_DIR", tmp_path)
        monkeypatch.setattr("app.api.routes.mcp.WORKSPACE_DIR", tmp_path)
        monkeypatch.setattr(
            "app.mcp.manager.MCPManager.SYSTEM_DEFAULTS_PATH",
            _empty_system_defaults_path(tmp_path),
        )

        mgr = MCPManager()
        mgr.save_store_server(
            TEST_USER_ID,
            MCPServerDefinition(
                name="custom-server",
                display_name="Custom Server",
                type="stdio",
                command="npx",
                args=["-y", "custom-mcp"],
            ),
            force=True,
        )
        monkeypatch.setattr("app.api.routes.mcp.get_mcp_manager", lambda: mgr)

        # 添加到工作区
        response = client.post("/api/mcp/workspaces/workspace-3/servers/custom-server")
        assert response.status_code == 200

        response = client.get("/api/mcp/workspaces/workspace-3")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["servers"][0]["name"] == "custom-server"

        # 从工作区移除（但全局配置中仍有，所以会继承）
        response = client.delete("/api/mcp/workspaces/workspace-3/servers/custom-server")
        assert response.status_code == 200

        # 验证工作区配置中已删除
        workspace_config = tmp_path / TEST_USER_ID / "workspace-3" / ".aiasys" / "mcp_config.json"
        import json

        ws_data = json.loads(workspace_config.read_text(encoding="utf-8"))
        assert "custom-server" not in ws_data.get("servers", {})
