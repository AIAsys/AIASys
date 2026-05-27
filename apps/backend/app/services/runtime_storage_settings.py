"""运行态存储路径设置服务。"""

from __future__ import annotations

import os
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import DATA_DIR, LOGS_DIR, RUNTIME_ROOT, WORKSPACE_DIR
from app.core.runtime_storage_config import (
    STORAGE_ENV_BY_KEY,
    STORAGE_PATH_KEYS,
    get_runtime_storage_config_path,
    read_runtime_storage_paths,
    write_runtime_storage_paths,
)

_MIGRATION_STATUS_FILE = "runtime-storage-migration.json"
_MIGRATION_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now().isoformat()


class RuntimeStorageSettingsService:
    """管理保存后重启生效的存储路径配置。"""

    def __init__(
        self,
        *,
        config_root: Path | None = None,
        effective_paths: dict[str, Path] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.config_root = Path(config_root or RUNTIME_ROOT)
        self.effective_paths = effective_paths or {
            "data_dir": Path(DATA_DIR),
            "workspaces_dir": Path(WORKSPACE_DIR),
            "logs_dir": Path(LOGS_DIR),
        }
        self.env = env if env is not None else os.environ

    def _read_pending_paths(self) -> dict[str, str]:
        return read_runtime_storage_paths(self.config_root)

    def _config_path(self) -> Path:
        return get_runtime_storage_config_path(self.config_root)

    def _normalize_path_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return str(Path(text).expanduser()) if text else None

    def _migration_status_path(self) -> Path:
        return self._config_path().parent / _MIGRATION_STATUS_FILE

    def _read_migration_status(self) -> dict[str, Any]:
        path = self._migration_status_path()
        if not path.exists():
            return self._empty_migration_status()
        try:
            import json

            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return self._empty_migration_status(status="unknown")
        if not isinstance(payload, dict):
            return self._empty_migration_status(status="unknown")
        return {
            **self._empty_migration_status(status=str(payload.get("status") or "unknown")),
            **payload,
        }

    def _write_migration_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        import json
        import tempfile

        path = self._migration_status_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(payload)
        payload["updated_at"] = _now_iso()
        fd, temp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, indent=2, ensure_ascii=False))
            os.replace(temp_path, path)
        except Exception:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise
        return payload

    def _empty_migration_status(self, *, status: str = "idle") -> dict[str, Any]:
        return {
            "migration_id": None,
            "status": status,
            "created_at": None,
            "updated_at": None,
            "started_at": None,
            "completed_at": None,
            "paths": {},
            "items": [],
            "warnings": [],
            "errors": [],
            "progress": {
                "total_items": 0,
                "completed_items": 0,
                "current_key": None,
            },
            "message": None,
        }

    def _effective_path_texts(self) -> dict[str, str]:
        return {key: str(value.expanduser()) for key, value in self.effective_paths.items()}

    def _build_config_paths(self, paths: dict[str, str | None]) -> dict[str, str | None]:
        pending_paths = self._read_pending_paths()
        next_paths: dict[str, str | None] = dict(pending_paths)
        for key in STORAGE_PATH_KEYS:
            env_name = STORAGE_ENV_BY_KEY[key]
            if env_name in self.env:
                continue
            if key not in paths:
                continue
            normalized_path = self._normalize_path_text(paths[key])
            effective_path = str(self.effective_paths[key].expanduser())
            next_paths[key] = (
                normalized_path if normalized_path and normalized_path != effective_path else None
            )
        return next_paths

    def _build_target_paths(self, config_paths: dict[str, str | None]) -> dict[str, str]:
        data_dir = (
            str(self.effective_paths["data_dir"].expanduser())
            if STORAGE_ENV_BY_KEY["data_dir"] in self.env
            else self._normalize_path_text(config_paths.get("data_dir"))
            or str(self.effective_paths["data_dir"].expanduser())
        )
        logs_dir = (
            str(self.effective_paths["logs_dir"].expanduser())
            if STORAGE_ENV_BY_KEY["logs_dir"] in self.env
            else self._normalize_path_text(config_paths.get("logs_dir"))
            or str(self.effective_paths["logs_dir"].expanduser())
        )
        workspaces_dir = (
            str(self.effective_paths["workspaces_dir"].expanduser())
            if STORAGE_ENV_BY_KEY["workspaces_dir"] in self.env
            else self._normalize_path_text(config_paths.get("workspaces_dir"))
            or str(Path(data_dir) / "workspaces")
        )
        return {
            "data_dir": data_dir,
            "workspaces_dir": workspaces_dir,
            "logs_dir": logs_dir,
        }

    def _path_is_relative_to(self, child: Path, parent: Path) -> bool:
        try:
            child.resolve().relative_to(parent.resolve())
            return True
        except ValueError:
            return False

    def _is_empty_dir(self, path: Path) -> bool:
        return path.is_dir() and not any(path.iterdir())

    def preview_migration(self, paths: dict[str, str | None]) -> dict[str, Any]:
        config_paths = self._build_config_paths(paths)
        target_paths = self._build_target_paths(config_paths)
        source_paths = self._effective_path_texts()
        items: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []
        data_source = Path(source_paths["data_dir"]).expanduser()
        data_target = Path(target_paths["data_dir"]).expanduser()
        data_dir_changes = data_source != data_target

        for key in STORAGE_PATH_KEYS:
            source = Path(source_paths[key]).expanduser()
            target = Path(target_paths[key]).expanduser()
            if source == target:
                continue
            if (
                key != "data_dir"
                and data_dir_changes
                and self._path_is_relative_to(source, data_source)
                and self._path_is_relative_to(target, data_target)
            ):
                continue

            source_exists = source.exists()
            target_exists = target.exists()
            target_empty = (not target_exists) or self._is_empty_dir(target)
            ok = True
            message = "可以迁移"

            if not source_exists:
                message = "源目录不存在，将只创建目标目录"
                warnings.append(f"{key} 源目录不存在: {source}")
            if target_exists and not target.is_dir():
                ok = False
                message = "目标路径已存在但不是目录"
            elif target_exists and not target_empty:
                ok = False
                message = "目标目录不是空目录"
            elif self._path_is_relative_to(target, source):
                ok = False
                message = "目标目录不能位于源目录内部"
            elif self._path_is_relative_to(source, target):
                ok = False
                message = "源目录不能位于目标目录内部"

            if not ok:
                errors.append(f"{key}: {message}")

            items.append(
                {
                    "key": key,
                    "source_path": str(source),
                    "target_path": str(target),
                    "source_exists": source_exists,
                    "target_exists": target_exists,
                    "target_empty": target_empty,
                    "will_copy": source_exists,
                    "ok": ok,
                    "message": message,
                }
            )

        can_start = bool(items) and not errors
        if not items:
            warnings.append("没有需要迁移的路径变更")

        return {
            "migration_id": None,
            "status": "preview",
            "created_at": None,
            "updated_at": _now_iso(),
            "started_at": None,
            "completed_at": None,
            "paths": target_paths,
            "config_paths": {
                key: value for key, value in config_paths.items() if value is not None
            },
            "items": items,
            "warnings": warnings,
            "errors": errors,
            "progress": {
                "total_items": len(items),
                "completed_items": 0,
                "current_key": None,
            },
            "can_start": can_start,
            "message": "可以开始迁移" if can_start else "迁移前需要处理提示项",
        }

    def get_migration_status(self) -> dict[str, Any]:
        return self._read_migration_status()

    def migration_in_progress(self) -> bool:
        return self.get_migration_status().get("status") == "in_progress"

    def start_migration(
        self,
        paths: dict[str, str | None],
        *,
        run_async: bool = True,
    ) -> dict[str, Any]:
        with _MIGRATION_LOCK:
            current = self._read_migration_status()
            if current.get("status") == "in_progress":
                raise ValueError("已有存储迁移正在进行")

            preview = self.preview_migration(paths)
            if not preview.get("can_start"):
                raise ValueError("迁移预检未通过")

            migration_id = uuid4().hex[:12]
            status = {
                **preview,
                "migration_id": migration_id,
                "status": "in_progress",
                "created_at": _now_iso(),
                "started_at": _now_iso(),
                "completed_at": None,
                "progress": {
                    "total_items": len(preview["items"]),
                    "completed_items": 0,
                    "current_key": None,
                },
                "message": "正在迁移存储目录",
            }
            self._write_migration_status(status)

        if run_async:
            thread = threading.Thread(
                target=self._run_migration,
                args=(migration_id,),
                daemon=True,
            )
            thread.start()
            return self.get_migration_status()

        self._run_migration(migration_id)
        return self.get_migration_status()

    def _run_migration(self, migration_id: str) -> None:
        status = self._read_migration_status()
        if status.get("migration_id") != migration_id:
            return

        try:
            items = [item for item in status.get("items", []) if isinstance(item, dict)]
            for index, item in enumerate(items, start=1):
                key = str(item.get("key") or "")
                self._write_migration_status(
                    {
                        **status,
                        "status": "in_progress",
                        "progress": {
                            "total_items": len(items),
                            "completed_items": index - 1,
                            "current_key": key,
                        },
                        "message": f"正在迁移 {key}",
                    }
                )
                self._copy_migration_item(item)
                status = self._read_migration_status()

            write_runtime_storage_paths(
                self.config_root,
                {
                    key: str(value)
                    for key, value in dict(status.get("config_paths") or {}).items()
                    if key in STORAGE_PATH_KEYS
                },
            )
            self._write_migration_status(
                {
                    **status,
                    "status": "completed",
                    "completed_at": _now_iso(),
                    "progress": {
                        "total_items": len(items),
                        "completed_items": len(items),
                        "current_key": None,
                    },
                    "message": "迁移完成，重启后端后生效",
                }
            )
        except Exception as exc:
            latest = self._read_migration_status()
            self._write_migration_status(
                {
                    **latest,
                    "status": "failed",
                    "completed_at": _now_iso(),
                    "errors": [*list(latest.get("errors") or []), str(exc)],
                    "message": "迁移失败",
                }
            )

    def _copy_migration_item(self, item: dict[str, Any]) -> None:
        source = Path(str(item["source_path"])).expanduser()
        target = Path(str(item["target_path"])).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_target = target.parent / f".{target.name}.aiasys-migrating-{uuid4().hex[:8]}"
        if temp_target.exists():
            shutil.rmtree(temp_target)

        if source.exists():
            shutil.copytree(source, temp_target, symlinks=True)
        else:
            temp_target.mkdir(parents=True, exist_ok=True)

        if target.exists():
            if not self._is_empty_dir(target):
                shutil.rmtree(temp_target)
                raise ValueError(f"目标目录不是空目录: {target}")
            target.rmdir()
        os.replace(temp_target, target)

    def get_settings(self) -> dict[str, object]:
        pending_paths = self._read_pending_paths()
        items = []
        restart_required = False

        for key in STORAGE_PATH_KEYS:
            env_name = STORAGE_ENV_BY_KEY[key]
            pending_path = pending_paths.get(key)
            effective_path = str(self.effective_paths[key].expanduser())
            configured_path = pending_path or effective_path
            overridden_by_env = env_name if env_name in self.env else None
            if pending_path and pending_path != effective_path:
                restart_required = True

            items.append(
                {
                    "key": key,
                    "effective_path": effective_path,
                    "configured_path": configured_path,
                    "pending_path": pending_path,
                    "overridden_by_env": overridden_by_env,
                    "editable": overridden_by_env is None,
                }
            )

        return {
            "paths": items,
            "restart_required": restart_required,
            "config_path": str(self._config_path()),
        }

    def save_settings(self, paths: dict[str, str | None]) -> dict[str, object]:
        if self.migration_in_progress():
            raise ValueError("存储迁移进行中，暂时不能保存路径配置")

        next_paths = self._build_config_paths(paths)

        for key in STORAGE_PATH_KEYS:
            if key not in paths:
                continue
            env_name = STORAGE_ENV_BY_KEY[key]
            if env_name in self.env:
                continue
            normalized_path = next_paths.get(key)
            if normalized_path:
                validation = self.validate_path(normalized_path, create=True)
                if not validation["ok"]:
                    raise ValueError(str(validation["message"]))
            next_paths[key] = normalized_path

        write_runtime_storage_paths(self.config_root, next_paths)
        return self.get_settings()

    def validate_path(self, path: str, *, create: bool = True) -> dict[str, object]:
        text = str(path or "").strip()
        if not text:
            return {
                "path": text,
                "ok": False,
                "exists": False,
                "is_directory": False,
                "readable": False,
                "writable": False,
                "created": False,
                "message": "路径不能为空",
            }

        target = Path(text).expanduser()
        created = False
        try:
            if target.exists() and not target.is_dir():
                return {
                    "path": str(target),
                    "ok": False,
                    "exists": True,
                    "is_directory": False,
                    "readable": os.access(target, os.R_OK),
                    "writable": False,
                    "created": False,
                    "message": "路径已存在但不是目录",
                }

            if not target.exists() and create:
                target.mkdir(parents=True, exist_ok=True)
                created = True

            exists = target.exists()
            is_directory = target.is_dir()
            readable = exists and os.access(target, os.R_OK)
            writable = exists and is_directory and os.access(target, os.W_OK)
            ok = exists and is_directory and readable and writable
            message = "路径可用" if ok else "路径不可读写"
            return {
                "path": str(target),
                "ok": ok,
                "exists": exists,
                "is_directory": is_directory,
                "readable": readable,
                "writable": writable,
                "created": created,
                "message": message,
            }
        except Exception as exc:
            return {
                "path": str(target),
                "ok": False,
                "exists": target.exists(),
                "is_directory": target.is_dir() if target.exists() else False,
                "readable": False,
                "writable": False,
                "created": created,
                "message": str(exc),
            }


def is_runtime_storage_migration_in_progress() -> bool:
    return RuntimeStorageSettingsService().migration_in_progress()
