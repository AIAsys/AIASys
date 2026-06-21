"""运行态存储路径配置读写工具。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from app.utils.path_utils import as_system_path

STORAGE_SETTINGS_ENV = "AIASYS_RUNTIME_STORAGE_CONFIG_PATH"
STORAGE_SETTINGS_RELATIVE_PATH = Path(".config") / "runtime-storage.json"

STORAGE_PATH_KEYS = (
    "data_dir",
    "workspaces_dir",
    "logs_dir",
)

STORAGE_ENV_BY_KEY = {
    "data_dir": "AIASYS_RUNTIME_DATA_DIR",
    "workspaces_dir": "AIASYS_RUNTIME_WORKSPACES_DIR",
    "logs_dir": "AIASYS_RUNTIME_LOGS_DIR",
}


def get_runtime_storage_config_path(config_root: Path) -> Path:
    """返回运行态存储路径配置文件位置。"""
    override = os.environ.get(STORAGE_SETTINGS_ENV)
    if override:
        return Path(override).expanduser()
    return config_root / STORAGE_SETTINGS_RELATIVE_PATH


def _normalize_stored_path(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def read_runtime_storage_paths(config_root: Path) -> dict[str, str]:
    """读取待生效存储路径；文件不存在或损坏时返回空配置。"""
    path = get_runtime_storage_config_path(config_root)
    if not Path(as_system_path(path)).exists():
        return {}
    try:
        payload = json.loads(Path(as_system_path(path)).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}

    raw_paths = payload.get("paths")
    if not isinstance(raw_paths, dict):
        raw_paths = payload

    result: dict[str, str] = {}
    for key in STORAGE_PATH_KEYS:
        normalized = _normalize_stored_path(raw_paths.get(key))
        if normalized:
            result[key] = normalized
    return result


def write_runtime_storage_paths(
    config_root: Path,
    paths: Mapping[str, str | None],
) -> Path:
    """写入待生效存储路径配置。"""
    config_path = get_runtime_storage_config_path(config_root)
    normalized_paths: dict[str, str] = {}
    for key in STORAGE_PATH_KEYS:
        normalized = _normalize_stored_path(paths.get(key))
        if normalized:
            normalized_paths[key] = normalized

    payload = {
        "_schema_version": 1,
        "paths": normalized_paths,
    }
    Path(as_system_path(str(config_path.parent))).mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=as_system_path(str(config_path.parent)), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, ensure_ascii=False))
        os.replace(temp_path, as_system_path(str(config_path)))
    except Exception:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise
    return config_path
