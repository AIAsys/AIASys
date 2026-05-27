"""全局环境变量存储。

每个用户一个 JSON 文件，存储全局默认环境变量。
工作区级别的 env_vars 会覆盖同名的全局变量。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.config import get_user_global_config_dir

logger = logging.getLogger(__name__)


def _get_user_file(user_id: str) -> Path:
    return get_user_global_config_dir(user_id) / "env_vars.json"


def get_global_env_vars(user_id: str) -> dict[str, str]:
    """读取用户全局环境变量。"""
    file_path = _get_user_file(user_id)
    if not file_path.exists():
        return {}
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        logger.warning("读取全局环境变量失败: %s", file_path, exc_info=True)
    return {}


def set_global_env_vars(user_id: str, env_vars: dict[str, str]) -> None:
    """保存用户全局环境变量。"""
    file_path = _get_user_file(user_id)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(env_vars, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def resolve_merged_env_vars(
    user_id: str,
    workspace_env_vars: dict[str, str] | None,
) -> dict[str, str] | None:
    """合并全局 + 工作区环境变量，工作区优先。"""
    global_vars = get_global_env_vars(user_id)
    if not global_vars and not workspace_env_vars:
        return None
    merged = dict(global_vars)
    if workspace_env_vars:
        merged.update(workspace_env_vars)
    return merged
