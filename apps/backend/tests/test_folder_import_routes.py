"""
文件夹导入 API 路由契约测试。
"""

from __future__ import annotations

import io
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import workspaces_core as route_module
from app.models.user import UserInfo
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_client(monkeypatch, tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.include_router(route_module.router)
    app.dependency_overrides[route_module.require_auth()] = _build_user
    return TestClient(app)


def _patch_registry(monkeypatch, service: WorkspaceRegistryService) -> None:
    monkeypatch.setattr(route_module, "get_workspace_registry_service", lambda: service)


def _prepare_service(tmp_path: Path, user_id: str = "local_default") -> WorkspaceRegistryService:
    service = WorkspaceRegistryService(tmp_path)
    return service


class TestFolderImportPreviewRoute:
    def test_preview_local_folder(self, monkeypatch, tmp_path: Path):
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_service(tmp_path)
        _patch_registry(monkeypatch, service)

        source = tmp_path / "source"
        source.mkdir()
        (source / "main.py").write_text("print('hello')")
        (source / ".env").write_text("SECRET=1")

        response = client.post(
            "/workspaces/import-folder-preview",
            json={"source_path": str(source)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["source_path"] == str(source)
        paths = {f["relative_path"] for f in data["files"] if not f["is_directory"]}
        assert "main.py" in paths
        assert ".env" in paths
        assert "main.py" in data["default_selected_files"]
        assert ".env" not in data["default_selected_files"]

    def test_preview_missing_source(self, monkeypatch, tmp_path: Path):
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_service(tmp_path)
        _patch_registry(monkeypatch, service)

        response = client.post("/workspaces/import-folder-preview", json={"source_path": ""})
        assert response.status_code == 400


class TestFolderImportUploadRoute:
    def test_upload_files(self, monkeypatch, tmp_path: Path):
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_service(tmp_path)
        _patch_registry(monkeypatch, service)

        response = client.post(
            "/workspaces/import-folder-upload",
            files=[
                ("files", ("main.py", io.BytesIO(b"print('hello')"), "text/x-python")),
                ("files", ("README.md", io.BytesIO(b"# test"), "text/markdown")),
            ],
        )
        assert response.status_code == 200
        data = response.json()
        assert "upload_id" in data
        assert data["file_count"] == 2

    def test_upload_empty(self, monkeypatch, tmp_path: Path):
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_service(tmp_path)
        _patch_registry(monkeypatch, service)

        response = client.post("/workspaces/import-folder-upload", files=[])
        # FastAPI 先校验必填参数，空数组会返回 422
        assert response.status_code == 422

    def test_upload_oversized_file(self, monkeypatch, tmp_path: Path):
        from app.services.folder_import import MAX_UPLOAD_FILE_SIZE_BYTES

        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_service(tmp_path)
        _patch_registry(monkeypatch, service)

        big_content = b"x" * (MAX_UPLOAD_FILE_SIZE_BYTES + 1)
        response = client.post(
            "/workspaces/import-folder-upload",
            files=[("files", ("big.bin", io.BytesIO(big_content), "application/octet-stream"))],
        )
        assert response.status_code == 413


class TestFolderImportStreamRoute:
    def test_stream_import_from_upload(self, monkeypatch, tmp_path: Path):
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_service(tmp_path)
        _patch_registry(monkeypatch, service)

        # 先上传文件
        upload_resp = client.post(
            "/workspaces/import-folder-upload",
            files=[("files", ("main.py", io.BytesIO(b"print('hello')"), "text/x-python"))],
        )
        assert upload_resp.status_code == 200
        upload_id = upload_resp.json()["upload_id"]

        # 再流式导入
        response = client.post(
            "/workspaces/import-folder-stream",
            json={
                "title": "test-upload-import",
                "temp_upload_id": upload_id,
                "import_files": ["main.py"],
            },
        )
        assert response.status_code == 200
        text = response.text
        assert 'data: {"stage": "completed"' in text
        assert "workspace_id" in text

    def test_stream_import_missing_source(self, monkeypatch, tmp_path: Path):
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_service(tmp_path)
        _patch_registry(monkeypatch, service)

        response = client.post(
            "/workspaces/import-folder-stream",
            json={"title": "test-missing"},
        )
        assert response.status_code == 400
