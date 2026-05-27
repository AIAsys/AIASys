"""MCP 管理器测试（三层合并模型）"""

from pathlib import Path

import pytest

from app.mcp import get_mcp_manager
from app.mcp.models import MCPServerDefinition

TEST_USER_ID = "test-user"


@pytest.fixture
def mgr():
    return get_mcp_manager()


@pytest.fixture
def tmp_workspace(tmp_path: Path):
    ws = tmp_path / TEST_USER_ID / "test_workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


class TestMCPStoreOperations:
    def test_list_store_skills_empty(self, mgr, tmp_path, monkeypatch):
        """空 store 返回空列表"""
        monkeypatch.setattr("app.mcp.manager.WORKSPACE_DIR", tmp_path)
        servers = mgr.list_store_servers(TEST_USER_ID)
        assert servers == []

    def test_save_and_get_server_definition(self, mgr, tmp_path, monkeypatch):
        """保存 server 定义后可以读取"""
        monkeypatch.setattr("app.mcp.manager.WORKSPACE_DIR", tmp_path)
        definition = MCPServerDefinition(
            name="test-server",
            display_name="Test Server",
            type="streamable-http",
            url="http://localhost:9999",
            description="A test MCP server",
        )
        result = mgr.save_store_server(TEST_USER_ID, definition)
        assert result.success

        loaded = mgr.get_server_definition("test-server", TEST_USER_ID)
        assert loaded is not None
        assert loaded.name == "test-server"
        assert loaded.display_name == "Test Server"
        assert loaded.type == "streamable-http"
        assert loaded.url == "http://localhost:9999"

    def test_remove_store_server(self, mgr, tmp_path, monkeypatch):
        """删除 server 定义"""
        monkeypatch.setattr("app.mcp.manager.WORKSPACE_DIR", tmp_path)
        definition = MCPServerDefinition(
            name="to-remove",
            display_name="To Remove",
            type="stdio",
            command="npx",
        )
        mgr.save_store_server(TEST_USER_ID, definition)

        result = mgr.remove_store_server("to-remove", TEST_USER_ID)
        assert result.success
        assert mgr.get_server_definition("to-remove", TEST_USER_ID) is None

    def test_save_rejects_duplicate_without_force(self, mgr, tmp_path, monkeypatch):
        """不覆盖已存在的 server"""
        monkeypatch.setattr("app.mcp.manager.WORKSPACE_DIR", tmp_path)
        definition = MCPServerDefinition(
            name="existing",
            display_name="Existing",
            type="streamable-http",
            url="http://localhost:1",
        )
        mgr.save_store_server(TEST_USER_ID, definition)

        result = mgr.save_store_server(TEST_USER_ID, definition, force=False)
        assert not result.success


class TestMCPWorkspaceConfig:
    def test_workspace_config_overrides_global(self, mgr, tmp_workspace, tmp_path, monkeypatch):
        """工作区配置覆盖全局配置"""
        monkeypatch.setattr("app.mcp.manager.WORKSPACE_DIR", tmp_path)

        # 全局配置
        mgr.save_store_server(
            TEST_USER_ID,
            MCPServerDefinition(
                name="server-a",
                display_name="Server A",
                type="streamable-http",
                url="http://global.example.com",
            ),
        )

        # 工作区配置覆盖
        mgr.save_workspace_server(
            tmp_workspace,
            MCPServerDefinition(
                name="server-a",
                display_name="Server A Workspace",
                type="streamable-http",
                url="http://workspace.example.com",
            ),
        )

        effective = mgr.get_effective_config(tmp_workspace)
        assert "server-a" in effective.servers
        assert effective.servers["server-a"].url == "http://workspace.example.com"

    def test_workspace_inherits_global(self, mgr, tmp_workspace, tmp_path, monkeypatch):
        """工作区无配置时继承全局"""
        monkeypatch.setattr("app.mcp.manager.WORKSPACE_DIR", tmp_path)

        mgr.save_store_server(
            TEST_USER_ID,
            MCPServerDefinition(
                name="server-b",
                display_name="Server B",
                type="streamable-http",
                url="http://global.example.com",
            ),
        )

        effective = mgr.get_effective_config(tmp_workspace)
        assert "server-b" in effective.servers
        assert effective.servers["server-b"].url == "http://global.example.com"

    def test_list_effective_servers(self, mgr, tmp_workspace, tmp_path, monkeypatch):
        """list_effective_servers 返回合并后的列表"""
        monkeypatch.setattr("app.mcp.manager.WORKSPACE_DIR", tmp_path)

        mgr.save_store_server(
            TEST_USER_ID,
            MCPServerDefinition(
                name="global-only",
                display_name="Global Only",
                type="streamable-http",
                url="http://global.example.com",
            ),
        )
        mgr.save_workspace_server(
            tmp_workspace,
            MCPServerDefinition(
                name="workspace-only",
                display_name="Workspace Only",
                type="streamable-http",
                url="http://workspace.example.com",
            ),
        )

        servers = mgr.list_effective_servers(tmp_workspace)
        names = {s.name for s in servers}
        assert "global-only" in names
        assert "workspace-only" in names

    def test_remove_workspace_server(self, mgr, tmp_workspace, tmp_path, monkeypatch):
        """从工作区配置删除 server"""
        monkeypatch.setattr("app.mcp.manager.WORKSPACE_DIR", tmp_path)

        mgr.save_workspace_server(
            tmp_workspace,
            MCPServerDefinition(
                name="to-delete",
                display_name="To Delete",
                type="streamable-http",
                url="http://example.com",
            ),
        )

        result = mgr.remove_workspace_server("to-delete", tmp_workspace)
        assert result.success

        effective = mgr.get_effective_config(tmp_workspace)
        assert "to-delete" not in effective.servers


class TestMCPSafety:
    def test_path_traversal_rejected(self, mgr, tmp_workspace):
        """路径遍历名称被拒绝"""
        result = mgr.save_workspace_server(
            tmp_workspace,
            MCPServerDefinition(
                name="../etc/passwd",
                display_name="Bad",
                type="streamable-http",
                url="http://localhost:1",
            ),
        )
        assert not result.success

        result = mgr.remove_store_server("../../etc/passwd", TEST_USER_ID)
        assert not result.success

        result = mgr.save_store_server(
            TEST_USER_ID,
            MCPServerDefinition(
                name="a/b",
                display_name="Bad",
                type="streamable-http",
                url="http://localhost:1",
            ),
        )
        assert not result.success
