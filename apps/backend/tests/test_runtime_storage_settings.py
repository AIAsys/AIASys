from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import Request

from app import main as app_main
from app.api.routes import system as system_route
from app.models.user import UserInfo
from app.services.runtime_storage_settings import RuntimeStorageSettingsService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_service(
    tmp_path: Path,
    *,
    env: dict[str, str] | None = None,
) -> RuntimeStorageSettingsService:
    return RuntimeStorageSettingsService(
        config_root=tmp_path,
        effective_paths={
            "data_dir": tmp_path / "data",
            "workspaces_dir": tmp_path / "data" / "workspaces",
            "logs_dir": tmp_path / "logs",
        },
        env=env or {},
    )


def test_storage_settings_save_marks_restart_required(tmp_path: Path) -> None:
    service = _build_service(tmp_path)

    response = service.save_settings(
        {
            "data_dir": str(tmp_path / "next-data"),
            "workspaces_dir": str(tmp_path / "next-workspaces"),
        }
    )

    paths = {item["key"]: item for item in response["paths"]}
    assert response["restart_required"] is True
    assert paths["data_dir"]["pending_path"] == str(tmp_path / "next-data")
    assert paths["workspaces_dir"]["pending_path"] == str(tmp_path / "next-workspaces")
    assert paths["data_dir"]["effective_path"] == str(tmp_path / "data")


def test_storage_settings_data_dir_change_derives_workspace_target(tmp_path: Path) -> None:
    service = _build_service(tmp_path)

    preview = service.preview_migration({"data_dir": str(tmp_path / "next-data")})

    assert preview["can_start"] is True
    assert preview["paths"]["workspaces_dir"] == str(tmp_path / "next-data" / "workspaces")
    assert preview["config_paths"] == {"data_dir": str(tmp_path / "next-data")}
    assert [item["key"] for item in preview["items"]] == ["data_dir"]


def test_storage_settings_env_override_is_readonly(tmp_path: Path) -> None:
    service = _build_service(
        tmp_path,
        env={"AIASYS_RUNTIME_WORKSPACES_DIR": "/env/workspaces"},
    )

    response = service.save_settings(
        {
            "workspaces_dir": str(tmp_path / "next-workspaces"),
            "logs_dir": str(tmp_path / "next-logs"),
        }
    )

    paths = {item["key"]: item for item in response["paths"]}
    assert paths["workspaces_dir"]["editable"] is False
    assert paths["workspaces_dir"]["overridden_by_env"] == "AIASYS_RUNTIME_WORKSPACES_DIR"
    assert paths["workspaces_dir"]["pending_path"] is None
    assert paths["logs_dir"]["pending_path"] == str(tmp_path / "next-logs")


def test_storage_settings_validate_path_creates_directory(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    target = tmp_path / "new-dir"

    result = service.validate_path(str(target), create=True)

    assert result["ok"] is True
    assert result["created"] is True
    assert target.is_dir()


def test_storage_settings_validate_rejects_file(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")

    result = service.validate_path(str(target), create=True)

    assert result["ok"] is False
    assert result["exists"] is True
    assert result["is_directory"] is False


def test_storage_migration_preview_rejects_non_empty_target(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    (tmp_path / "data").mkdir(parents=True)
    target = tmp_path / "next-workspaces"
    target.mkdir()
    (target / "existing.txt").write_text("occupied", encoding="utf-8")

    preview = service.preview_migration({"workspaces_dir": str(target)})

    assert preview["can_start"] is False
    assert any("目标目录不是空目录" in item["message"] for item in preview["items"])


def test_storage_migration_copies_data_and_writes_pending_config(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    source = tmp_path / "data" / "workspaces" / "local_default" / "task-alpha"
    source.mkdir(parents=True)
    (source / "note.md").write_text("hello", encoding="utf-8")
    target_data = tmp_path / "next-data"

    status = service.start_migration(
        {"data_dir": str(target_data)},
        run_async=False,
    )
    settings = service.get_settings()

    assert status["status"] == "completed"
    assert (target_data / "workspaces" / "local_default" / "task-alpha" / "note.md").read_text(
        encoding="utf-8"
    ) == "hello"
    paths = {item["key"]: item for item in settings["paths"]}
    assert paths["data_dir"]["pending_path"] == str(target_data)
    assert paths["workspaces_dir"]["pending_path"] is None


def test_storage_migration_in_progress_blocks_save(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    service._write_migration_status(
        {
            **service._empty_migration_status(status="in_progress"),
            "migration_id": "mig-test",
        }
    )

    with pytest.raises(ValueError, match="存储迁移进行中"):
        service.save_settings({"data_dir": str(tmp_path / "next-data")})


@pytest.mark.asyncio
async def test_storage_settings_routes_use_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        system_route,
        "get_runtime_storage_settings_service",
        lambda: service,
    )

    saved = await system_route.update_storage_settings(
        system_route.UpdateStorageSettingsRequest(paths={"data_dir": str(tmp_path / "next-data")}),
        current_user=_build_user(),
    )
    validation = await system_route.validate_storage_path(
        system_route.ValidateStoragePathRequest(path=str(tmp_path / "checked")),
        current_user=_build_user(),
    )

    assert saved["restart_required"] is True
    assert validation["ok"] is True


@pytest.mark.asyncio
async def test_storage_migration_routes_use_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    (tmp_path / "data" / "marker").mkdir(parents=True)
    monkeypatch.setattr(
        system_route,
        "get_runtime_storage_settings_service",
        lambda: service,
    )

    preview = await system_route.preview_storage_migration(
        system_route.StorageMigrationRequest(paths={"data_dir": str(tmp_path / "next-data")}),
        current_user=_build_user(),
    )
    started = await system_route.start_storage_migration(
        system_route.StorageMigrationRequest(paths={"data_dir": str(tmp_path / "next-data")}),
        current_user=_build_user(),
    )
    status = await system_route.get_storage_migration_status(current_user=_build_user())

    assert preview["can_start"] is True
    assert started["status"] in {"in_progress", "completed"}
    assert status["status"] in {"in_progress", "completed"}


@pytest.mark.asyncio
async def test_storage_migration_guard_blocks_api_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app_main,
        "is_runtime_storage_migration_in_progress",
        lambda: True,
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/workspaces",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )

    async def _call_next(_request):
        raise AssertionError("迁移锁应直接拒绝写请求")

    response = await app_main.storage_migration_guard_middleware(request, _call_next)

    assert response.status_code == 423
