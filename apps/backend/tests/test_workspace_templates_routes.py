"""工作区模板 API 路由契约测试。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import workspace_templates as route_module
from app.models.user import UserInfo


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_client(monkeypatch, tmp_path: Path) -> TestClient:
    import importlib

    import app.core.config as config_mod
    monkeypatch.setattr(config_mod, "WORKSPACE_DIR", tmp_path / "workspaces")

    import app.core.templates as tmpl_mod
    monkeypatch.setattr(tmpl_mod, "_TEMPLATES_DIR", tmp_path / "builtin")
    monkeypatch.setattr(
        tmpl_mod, "_get_user_templates_dir", lambda _uid: tmp_path / "user"
    )

    # 重新加载路由模块，使 WORKSPACE_DIR 使用新值
    importlib.reload(route_module)

    app = FastAPI()
    app.include_router(route_module.router)
    app.dependency_overrides[route_module.require_auth()] = _build_user
    return TestClient(app)


def _make_builtin_template(tmp_path: Path, template_id: str, name: str) -> None:
    tmpl_dir = tmp_path / "builtin" / template_id
    tmpl_dir.mkdir(parents=True)
    (tmpl_dir / "template.toml").write_text(
        f'template_id = "{template_id}"\nname = "{name}"\n',
        encoding="utf-8",
    )


def _make_user_template(tmp_path: Path, template_id: str, name: str) -> None:
    tmpl_dir = tmp_path / "user" / template_id
    tmpl_dir.mkdir(parents=True)
    (tmpl_dir / "template.toml").write_text(
        f'template_id = "{template_id}"\nname = "{name}"\n',
        encoding="utf-8",
    )


def _make_workspace(tmp_path: Path, workspace_id: str = "ws-export") -> Path:
    ws_dir = tmp_path / "workspaces" / "local_default" / workspace_id
    ws_dir.mkdir(parents=True)
    (ws_dir / ".aiasys" / "workspace").mkdir()
    (ws_dir / ".aiasys" / "workspace" / "workspace.json").write_text(
        json.dumps({"title": "Test WS", "description": "desc"}),
        encoding="utf-8",
    )
    (ws_dir / "README.md").write_text("# Test", encoding="utf-8")
    return ws_dir


class TestListTemplates:
    """GET /workspace-templates"""

    def test_list_builtin_and_user(self, monkeypatch, tmp_path: Path) -> None:
        client = _build_client(monkeypatch, tmp_path)
        _make_builtin_template(tmp_path, "builtin-a", "Builtin A")
        _make_user_template(tmp_path, "user-a", "User A")

        response = client.get("/workspace-templates")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        ids = {t["template_id"] for t in data["templates"]}
        assert ids == {"builtin-a", "user-a"}

    def test_user_overrides_builtin(self, monkeypatch, tmp_path: Path) -> None:
        client = _build_client(monkeypatch, tmp_path)
        _make_builtin_template(tmp_path, "shared", "Builtin Shared")
        _make_user_template(tmp_path, "shared", "User Shared")

        response = client.get("/workspace-templates")
        data = response.json()
        shared = [t for t in data["templates"] if t["template_id"] == "shared"]
        assert len(shared) == 1
        assert shared[0]["name"] == "User Shared"


class TestGetTemplate:
    """GET /workspace-templates/{template_id}"""

    def test_get_existing(self, monkeypatch, tmp_path: Path) -> None:
        client = _build_client(monkeypatch, tmp_path)
        _make_builtin_template(tmp_path, "detail-tmpl", "Detail")

        response = client.get("/workspace-templates/detail-tmpl")
        assert response.status_code == 200
        assert response.json()["template_id"] == "detail-tmpl"

    def test_get_not_found(self, monkeypatch, tmp_path: Path) -> None:
        client = _build_client(monkeypatch, tmp_path)
        response = client.get("/workspace-templates/nonexistent")
        assert response.status_code == 404


class TestDeleteTemplate:
    """DELETE /workspace-templates/{template_id}"""

    def test_delete_user_template(self, monkeypatch, tmp_path: Path) -> None:
        client = _build_client(monkeypatch, tmp_path)
        _make_user_template(tmp_path, "to-delete", "Delete Me")

        response = client.delete("/workspace-templates/to-delete")
        assert response.status_code == 200
        assert response.json()["deleted"] is True
        assert not (tmp_path / "user" / "to-delete").exists()

    def test_delete_builtin_refused(self, monkeypatch, tmp_path: Path) -> None:
        client = _build_client(monkeypatch, tmp_path)
        _make_builtin_template(tmp_path, "protected", "Protected")

        response = client.delete("/workspace-templates/protected")
        assert response.status_code == 404

    def test_delete_unsafe_id(self, monkeypatch, tmp_path: Path) -> None:
        client = _build_client(monkeypatch, tmp_path)
        response = client.delete("/workspace-templates/../etc")
        assert response.status_code == 404


class TestExportTemplate:
    """POST /workspace-templates/{workspace_id}/export"""

    def test_export_success(self, monkeypatch, tmp_path: Path) -> None:
        import app.services.workspace_registry as reg_mod

        client = _build_client(monkeypatch, tmp_path)
        monkeypatch.setattr(reg_mod, "WORKSPACE_DIR", tmp_path / "workspaces")

        service = reg_mod.WorkspaceRegistryService(tmp_path / "workspaces")
        service.create_workspace(user_id="local_default", title="Test", workspace_id="ws-export")
        # 添加一个 README.md 供导出读取
        ws_dir = tmp_path / "workspaces" / "local_default" / "ws-export"
        (ws_dir / "README.md").write_text("# Test", encoding="utf-8")

        response = client.post(
            "/workspace-templates/ws-export/export",
            json={"name": "Exported Template"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["name"] == "Exported Template"
        assert data["template_id"]

    def test_export_workspace_not_found(self, monkeypatch, tmp_path: Path) -> None:
        import app.services.workspace_registry as reg_mod

        client = _build_client(monkeypatch, tmp_path)
        monkeypatch.setattr(reg_mod, "WORKSPACE_DIR", tmp_path / "workspaces")

        response = client.post(
            "/workspace-templates/nonexistent/export",
            json={"name": "Fail"},
        )
        assert response.status_code == 404

    def test_export_invalid_name(self, monkeypatch, tmp_path: Path) -> None:
        import app.services.workspace_registry as reg_mod

        client = _build_client(monkeypatch, tmp_path)
        monkeypatch.setattr(reg_mod, "WORKSPACE_DIR", tmp_path / "workspaces")

        service = reg_mod.WorkspaceRegistryService(tmp_path / "workspaces")
        service.create_workspace(user_id="local_default", title="Test", workspace_id="ws-inv")

        response = client.post(
            "/workspace-templates/ws-inv/export",
            json={"name": ""},
        )
        assert response.status_code == 422

    def test_export_unsafe_template_id(self, monkeypatch, tmp_path: Path) -> None:
        import app.services.workspace_registry as reg_mod

        client = _build_client(monkeypatch, tmp_path)
        monkeypatch.setattr(reg_mod, "WORKSPACE_DIR", tmp_path / "workspaces")

        service = reg_mod.WorkspaceRegistryService(tmp_path / "workspaces")
        service.create_workspace(user_id="local_default", title="Test", workspace_id="ws-bad-id")

        response = client.post(
            "/workspace-templates/ws-bad-id/export",
            json={"name": "Bad", "template_id": "../etc"},
        )
        assert response.status_code == 422
