"""
子 Agent 目录管理器（专家管理）。

支持工作区级配置源：
- 全局（global）：跨所有工作区共享的子 Agent，持久化到全局目录 YAML
- 工作区（workspace）：工作区内共享的自定义子 Agent，持久化到工作区目录 YAML，跨会话复用

与现有 .aiasys/agent_config 配置体系保持一致的文件系统存储。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import tomli_w

from app.core.config import WORKSPACE_DIR
from app.models.expert import SubAgentVisibilitySettings
from app.services.agent.system_presets import (
    _LOCAL_BASELINES,
    build_subagent_manifest_from_seed,
)
from app.services.runtime_tooling import (
    canonicalize_runtime_tool_name,
    is_subagent_orchestration_tool_name,
    probe_runtime_tool,
)

logger = logging.getLogger(__name__)

# 子 Agent 标识名规则：英文、数字、下划线、连字符，不能以数字开头
_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")
_EXTENDED_MANIFEST_FIELDS = (
    "role",
    "model_reasoning_effort",
    "agent_nickname_pool",
    "fork_turns",
    "tool_policy",
)
_COLLABORATION_ROLES_FILENAME = "collaboration_roles.json"
_COLLABORATION_ROLES_INIT_FILENAME = "collaboration_roles_initialized.json"
DEFAULT_BUILTIN_EXPERT_INSTALLS: tuple[str, ...] = (
    "data_analyst",
    "researcher",
    "reviewer",
)


def _normalize_bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _normalize_lock_reason(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_tool_id_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


def _normalize_runtime_policy(raw: Any) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    max_depth = payload.get("max_depth")
    if not isinstance(max_depth, int) or max_depth < 1:
        max_depth = 1
    if max_depth > 5:
        max_depth = 5

    max_threads = payload.get("max_threads")
    if not isinstance(max_threads, int) or max_threads < 1:
        max_threads = None
    elif max_threads > 32:
        max_threads = 32

    return {
        "max_depth": max_depth,
        "max_threads": max_threads,
        "allow_nested_spawn": False,
        "budget_policy": (
            payload.get("budget_policy") if isinstance(payload.get("budget_policy"), dict) else {}
        ),
        "timeout_policy": (
            payload.get("timeout_policy") if isinstance(payload.get("timeout_policy"), dict) else {}
        ),
        "stop_policy": (
            payload.get("stop_policy") if isinstance(payload.get("stop_policy"), dict) else {}
        ),
    }


def normalize_subagent_tool_paths(tool_paths: Any) -> tuple[list[str], list[str]]:
    """规范化子 Agent 工具路径，并剔除当前运行时不可用的条目。"""
    if not isinstance(tool_paths, list):
        return [], []

    normalized: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()

    for item in tool_paths:
        raw = str(item or "").strip()
        if not raw:
            continue
        canonical = canonicalize_runtime_tool_name(raw)
        if is_subagent_orchestration_tool_name(canonical):
            if raw not in invalid:
                invalid.append(raw)
            continue
        availability = probe_runtime_tool(canonical)
        if not availability.available:
            if raw not in invalid:
                invalid.append(raw)
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        normalized.append(canonical)

    return normalized, invalid


def _get_user_global_workspace_dir(user_id: str) -> Path:
    return WORKSPACE_DIR / user_id / "global_workspace"


def _get_global_agent_config_dir(user_id: str) -> Path:
    path = _get_user_global_workspace_dir(user_id) / ".aiasys" / "agent_config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_workspace_agent_config_dir(user_id: str, workspace_id: str) -> Path:
    return WORKSPACE_DIR / user_id / workspace_id / ".aiasys" / "agent_config"


def _get_global_dir(user_id: str) -> Path:
    """全局级持久化子 Agent 目录。"""
    path = _get_global_agent_config_dir(user_id) / "subagents"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_enabled_experts_path(user_id: str) -> Path:
    path = _get_global_agent_config_dir(user_id) / "enabled_experts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_enabled_experts(user_id: str) -> set[str] | None:
    """读取用户显式启用的专家列表；None 表示继承全部目录角色。"""
    path = _get_enabled_experts_path(user_id)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("读取 enabled_experts 失败: %s", path, exc_info=True)
        return None

    if not isinstance(payload, list):
        return None

    normalized: set[str] = set()
    for item in payload:
        text = str(item or "").strip()
        if text:
            normalized.add(text)
    return normalized


def save_enabled_experts(user_id: str, enabled_names: set[str]) -> None:
    """保存用户显式启用的专家列表。"""
    path = _get_enabled_experts_path(user_id)
    normalized = sorted(
        {str(item or "").strip() for item in enabled_names if str(item or "").strip()}
    )
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _get_workspace_dir(user_id: str, workspace_id: str) -> Path:
    """工作区级持久化子 Agent 目录。"""
    return _get_workspace_agent_config_dir(user_id, workspace_id) / "subagents"


def _subagent_file_exists(
    *,
    user_id: str,
    name: str,
    scope: str,
    workspace_id: str | None = None,
) -> bool:
    effective_workspace = workspace_id or user_id
    if scope == "global":
        return (_get_global_dir(user_id) / f"{name}.toml").exists()
    if scope == "workspace":
        return (_get_workspace_dir(user_id, effective_workspace) / f"{name}.toml").exists()
    return False


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def _get_visibility_policy_path(
    *,
    user_id: str,
    scope: str,
    workspace_id: str | None = None,
) -> Path:
    if scope == "global":
        return _get_global_agent_config_dir(user_id) / _COLLABORATION_ROLES_FILENAME
    if scope == "workspace":
        effective_workspace = workspace_id or user_id
        return (
            _get_workspace_agent_config_dir(user_id, effective_workspace)
            / _COLLABORATION_ROLES_FILENAME
        )
    raise ValueError("协作专家策略只支持 global 或 workspace 作用域")


def _get_global_builtin_expert_init_path(user_id: str) -> Path:
    return _get_global_agent_config_dir(user_id) / _COLLABORATION_ROLES_INIT_FILENAME


def _read_visibility_policy_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("读取子 Agent 可见性策略失败: %s", path, exc_info=True)
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_policy_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    roles = payload.get("roles")
    if isinstance(roles, dict):
        payload["roles"] = {key: roles[key] for key in sorted(roles)}
    payload["version"] = 1
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _get_role_policy_payload(
    *,
    user_id: str,
    scope: str,
    role_id: str,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    path = _get_visibility_policy_path(
        user_id=user_id,
        scope=scope,
        workspace_id=workspace_id,
    )
    payload = _read_visibility_policy_file(path)
    roles = payload.get("roles")
    if not isinstance(roles, dict):
        return {}
    raw = roles.get(role_id)
    return raw if isinstance(raw, dict) else {}


def _normalize_visibility_settings(
    raw: Any,
    *,
    source: str,
) -> SubAgentVisibilitySettings:
    payload = raw if isinstance(raw, dict) else {}
    source_value = source if source in {"system", "global", "workspace"} else "system"
    enabled_value = payload.get("enabled", payload.get("default_enabled"))
    return SubAgentVisibilitySettings(
        catalog_visible=_normalize_bool(payload.get("catalog_visible"), True),
        host_selectable=_normalize_bool(payload.get("host_selectable"), True),
        default_enabled=_normalize_bool(enabled_value, False),
        visibility_source=source_value,
        lock_reason=_normalize_lock_reason(payload.get("lock_reason")),
    )


def load_subagent_visibility_policy(
    *,
    user_id: str,
    scope: str,
    workspace_id: str | None = None,
) -> dict[str, SubAgentVisibilitySettings]:
    """读取单层协作专家策略。"""
    path = _get_visibility_policy_path(
        user_id=user_id,
        scope=scope,
        workspace_id=workspace_id,
    )
    payload = _read_visibility_policy_file(path)
    roles = payload.get("roles")
    if not isinstance(roles, dict):
        return {}

    normalized: dict[str, SubAgentVisibilitySettings] = {}
    for raw_role_id, raw_policy in roles.items():
        role_id = str(raw_role_id or "").strip()
        if not role_id:
            continue
        normalized[role_id] = _normalize_visibility_settings(
            raw_policy,
            source=scope,
        )
    return normalized


def resolve_subagent_visibility_policy(
    *,
    user_id: str,
    role_id: str,
    workspace_id: str | None = None,
) -> SubAgentVisibilitySettings:
    """按系统提供、用户默认、工作区启用的顺序合成单个协作专家策略。"""
    normalized_role_id = str(role_id or "").strip()
    effective = SubAgentVisibilitySettings(
        catalog_visible=True,
        host_selectable=True,
        default_enabled=False,
        visibility_source="system",
    )
    if not normalized_role_id:
        return effective

    global_policy = load_subagent_visibility_policy(
        user_id=user_id,
        scope="global",
    ).get(normalized_role_id)
    if global_policy is not None:
        effective = global_policy

    if workspace_id:
        workspace_policy = load_subagent_visibility_policy(
            user_id=user_id,
            scope="workspace",
            workspace_id=workspace_id,
        ).get(normalized_role_id)
        if workspace_policy is not None:
            effective = workspace_policy

    return effective


def is_subagent_dispatch_enabled(
    *,
    user_id: str,
    role_id: str,
    workspace_id: str | None = None,
    explicit_enabled_role_ids: list[str] | set[str] | None = None,
) -> bool:
    """判断协作专家是否允许进入当前运行态派发。

    目录项可以来自系统市场，但运行态必须来自用户默认层或工作区层的显式启用。
    """
    normalized_role_id = str(role_id or "").strip()
    if not normalized_role_id:
        return False

    policy = resolve_subagent_visibility_policy(
        user_id=user_id,
        role_id=normalized_role_id,
        workspace_id=workspace_id,
    )
    if not policy.host_selectable or not policy.default_enabled:
        return False
    if policy.visibility_source == "system":
        return False
    if policy.visibility_source == "global" and not is_subagent_installed_to_scope(
        user_id=user_id,
        name=normalized_role_id,
        scope="global",
    ):
        return False
    if policy.visibility_source == "workspace" and not is_subagent_installed_to_scope(
        user_id=user_id,
        name=normalized_role_id,
        scope="workspace",
        workspace_id=workspace_id,
    ):
        return False

    if explicit_enabled_role_ids is not None:
        explicit_set = {
            str(item or "").strip() for item in explicit_enabled_role_ids if str(item or "").strip()
        }
        if normalized_role_id not in explicit_set:
            return False

    return True


def save_subagent_visibility_policy(
    *,
    user_id: str,
    role_id: str,
    scope: str,
    workspace_id: str | None = None,
    catalog_visible: bool | None = None,
    host_selectable: bool | None = None,
    default_enabled: bool | None = None,
    lock_reason: str | None = None,
) -> SubAgentVisibilitySettings:
    """写入单层协作专家策略，并返回该层保存后的策略。"""
    normalized_role_id = str(role_id or "").strip()
    if not normalized_role_id:
        raise ValueError("子 Agent 角色 ID 不能为空")
    if scope not in {"global", "workspace"}:
        raise ValueError("协作专家策略只支持 global 或 workspace 作用域")

    path = _get_visibility_policy_path(
        user_id=user_id,
        scope=scope,
        workspace_id=workspace_id,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _read_visibility_policy_file(path)
    roles = payload.get("roles")
    if not isinstance(roles, dict):
        roles = {}

    existing = roles.get(normalized_role_id)
    existing_payload = existing if isinstance(existing, dict) else {}
    existing_settings = _normalize_visibility_settings(existing, source=scope)
    next_settings = SubAgentVisibilitySettings(
        catalog_visible=(
            existing_settings.catalog_visible if catalog_visible is None else catalog_visible
        ),
        host_selectable=(
            existing_settings.host_selectable if host_selectable is None else host_selectable
        ),
        default_enabled=(
            existing_settings.default_enabled if default_enabled is None else default_enabled
        ),
        visibility_source=scope,
        lock_reason=(
            existing_settings.lock_reason
            if lock_reason is None
            else _normalize_lock_reason(lock_reason)
        ),
    )
    roles[normalized_role_id] = {
        **existing_payload,
        "catalog_visible": next_settings.catalog_visible,
        "host_selectable": next_settings.host_selectable,
        "enabled": next_settings.default_enabled,
        "lock_reason": next_settings.lock_reason,
    }
    payload["roles"] = roles
    _write_policy_file(path, payload)
    return next_settings


def load_workspace_collaboration_policy(
    *,
    user_id: str,
    scope: str = "workspace",
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """读取工作区协作专家策略文件。"""
    path = _get_visibility_policy_path(
        user_id=user_id,
        scope=scope,
        workspace_id=workspace_id,
    )
    payload = _read_visibility_policy_file(path)
    roles = payload.get("roles")
    if not isinstance(roles, dict):
        roles = {}
    return {
        "roles": roles,
        "runtime": _normalize_runtime_policy(payload.get("runtime")),
    }


def resolve_workspace_role_tool_ids(
    *,
    user_id: str,
    role_id: str,
    workspace_id: str | None = None,
) -> list[str] | None:
    normalized_role_id = str(role_id or "").strip()
    if not normalized_role_id:
        return None

    effective: list[str] | None = None
    global_payload = _get_role_policy_payload(
        user_id=user_id,
        scope="global",
        role_id=normalized_role_id,
    )
    global_tools = _normalize_tool_id_list(global_payload.get("tool_ids"))
    if global_tools is not None:
        effective = global_tools

    if workspace_id:
        workspace_payload = _get_role_policy_payload(
            user_id=user_id,
            scope="workspace",
            workspace_id=workspace_id,
            role_id=normalized_role_id,
        )
        workspace_tools = _normalize_tool_id_list(workspace_payload.get("tool_ids"))
        if workspace_tools is not None:
            effective = workspace_tools
    return effective


def resolve_workspace_collaboration_runtime_policy(
    *,
    user_id: str,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    effective = _normalize_runtime_policy(None)
    global_policy = load_workspace_collaboration_policy(
        user_id=user_id,
        scope="global",
    )
    effective = _normalize_runtime_policy(global_policy.get("runtime"))
    if workspace_id:
        workspace_policy = load_workspace_collaboration_policy(
            user_id=user_id,
            scope="workspace",
            workspace_id=workspace_id,
        )
        effective = _normalize_runtime_policy(
            {
                **effective,
                **workspace_policy.get("runtime", {}),
            }
        )
    return effective


def save_workspace_collaboration_policy(
    *,
    user_id: str,
    workspace_id: str,
    enabled_role_ids: list[str] | None = None,
    available_role_ids: list[str] | None = None,
    reset_enabled: bool = False,
    role_tool_ids: dict[str, list[str]] | None = None,
    runtime_policy: dict[str, Any] | None = None,
) -> None:
    """保存工作区级协作专家策略。"""
    path = _get_visibility_policy_path(
        user_id=user_id,
        scope="workspace",
        workspace_id=workspace_id,
    )
    payload = _read_visibility_policy_file(path)
    roles = payload.get("roles")
    if not isinstance(roles, dict):
        roles = {}

    available_set = {
        str(role_id or "").strip()
        for role_id in (available_role_ids or [])
        if str(role_id or "").strip()
    }

    if reset_enabled:
        all_role_ids = available_set | {
            str(role_id or "").strip() for role_id in roles if str(role_id or "").strip()
        }
        for role_id in all_role_ids:
            raw = roles.get(role_id)
            role_payload = raw if isinstance(raw, dict) else {}
            role_payload.pop("enabled", None)
            role_payload.pop("default_enabled", None)
            roles[role_id] = role_payload
    elif enabled_role_ids is not None:
        enabled_set = {
            str(role_id or "").strip() for role_id in enabled_role_ids if str(role_id or "").strip()
        }
        all_role_ids = (
            enabled_set
            | available_set
            | {str(role_id or "").strip() for role_id in roles if str(role_id or "").strip()}
        )
        for role_id in all_role_ids:
            raw = roles.get(role_id)
            role_payload = raw if isinstance(raw, dict) else {}
            role_payload["enabled"] = role_id in enabled_set
            role_payload.pop("default_enabled", None)
            roles[role_id] = role_payload

    if role_tool_ids is not None:
        for raw_role_id, raw_tool_ids in role_tool_ids.items():
            role_id = str(raw_role_id or "").strip()
            if not role_id:
                continue
            raw = roles.get(role_id)
            role_payload = raw if isinstance(raw, dict) else {}
            role_payload["tool_ids"] = _normalize_tool_id_list(raw_tool_ids) or []
            roles[role_id] = role_payload

        for role_id, raw in list(roles.items()):
            if role_id not in role_tool_ids and isinstance(raw, dict):
                raw.pop("tool_ids", None)

    if runtime_policy is not None:
        payload["runtime"] = _normalize_runtime_policy(runtime_policy)

    payload["roles"] = roles
    _write_policy_file(path, payload)


def save_global_collaboration_policy(
    *,
    user_id: str,
    enabled_role_ids: list[str] | None = None,
    available_role_ids: list[str] | None = None,
    reset_enabled: bool = False,
    role_tool_ids: dict[str, list[str]] | None = None,
    runtime_policy: dict[str, Any] | None = None,
) -> None:
    """保存用户默认层协作专家策略。"""
    path = _get_visibility_policy_path(
        user_id=user_id,
        scope="global",
    )
    payload = _read_visibility_policy_file(path)
    roles = payload.get("roles")
    if not isinstance(roles, dict):
        roles = {}

    available_set = {
        str(role_id or "").strip()
        for role_id in (available_role_ids or [])
        if str(role_id or "").strip()
    }

    if reset_enabled:
        all_role_ids = available_set | {
            str(role_id or "").strip() for role_id in roles if str(role_id or "").strip()
        }
        for role_id in all_role_ids:
            raw = roles.get(role_id)
            role_payload = raw if isinstance(raw, dict) else {}
            role_payload.pop("enabled", None)
            role_payload.pop("default_enabled", None)
            roles[role_id] = role_payload
    elif enabled_role_ids is not None:
        enabled_set = {
            str(role_id or "").strip() for role_id in enabled_role_ids if str(role_id or "").strip()
        }
        all_role_ids = (
            enabled_set
            | available_set
            | {str(role_id or "").strip() for role_id in roles if str(role_id or "").strip()}
        )
        for role_id in all_role_ids:
            raw = roles.get(role_id)
            role_payload = raw if isinstance(raw, dict) else {}
            role_payload["enabled"] = role_id in enabled_set
            role_payload.pop("default_enabled", None)
            roles[role_id] = role_payload

    if role_tool_ids is not None:
        for raw_role_id, raw_tool_ids in role_tool_ids.items():
            role_id = str(raw_role_id or "").strip()
            if not role_id:
                continue
            raw = roles.get(role_id)
            role_payload = raw if isinstance(raw, dict) else {}
            role_payload["tool_ids"] = _normalize_tool_id_list(raw_tool_ids) or []
            roles[role_id] = role_payload

        for role_id, raw in list(roles.items()):
            if role_id not in role_tool_ids and isinstance(raw, dict):
                raw.pop("tool_ids", None)

    if runtime_policy is not None:
        payload["runtime"] = _normalize_runtime_policy(runtime_policy)

    payload["roles"] = roles
    _write_policy_file(path, payload)


def compute_subagent_visibility_fingerprint(
    *,
    user_id: str,
    workspace_id: str | None = None,
) -> str:
    def _normalized_layer(scope: str, workspace: str | None = None) -> dict[str, Any]:
        policy = load_workspace_collaboration_policy(
            user_id=user_id,
            scope=scope,
            workspace_id=workspace,
        )
        roles = policy.get("roles")
        normalized_roles: dict[str, Any] = {}
        if isinstance(roles, dict):
            for raw_role_id, raw_payload in sorted(roles.items()):
                role_id = str(raw_role_id or "").strip()
                if not role_id:
                    continue
                payload = raw_payload if isinstance(raw_payload, dict) else {}
                visibility = _normalize_visibility_settings(payload, source=scope)
                normalized_roles[role_id] = {
                    "catalog_visible": visibility.catalog_visible,
                    "host_selectable": visibility.host_selectable,
                    "enabled": visibility.default_enabled,
                    "lock_reason": visibility.lock_reason,
                    "tool_ids": _normalize_tool_id_list(payload.get("tool_ids")),
                }
        return {
            "roles": normalized_roles,
            "runtime": _normalize_runtime_policy(policy.get("runtime")),
        }

    payload: dict[str, Any] = {
        "global": _normalized_layer("global"),
        "workspace": {},
    }
    if workspace_id:
        payload["workspace"] = _normalized_layer("workspace", workspace_id)
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def _visibility_fields_for_item(
    *,
    user_id: str,
    role_id: str,
    workspace_id: str | None,
) -> dict[str, Any]:
    policy = resolve_subagent_visibility_policy(
        user_id=user_id,
        role_id=role_id,
        workspace_id=workspace_id,
    )
    return {
        "catalog_visible": policy.catalog_visible,
        "host_selectable": policy.host_selectable,
        "default_enabled": policy.default_enabled,
        "visibility_source": policy.visibility_source,
        "lock_reason": policy.lock_reason,
    }


def _ensure_subagent_config_table() -> None:
    from app.core.database import SubAgentConfigORM, engine

    SubAgentConfigORM.__table__.create(bind=engine, checkfirst=True)


def _scope_identity(
    *,
    user_id: str,
    scope: str,
    session_id: str | None,
    workspace_id: str | None,
) -> tuple[str | None, str | None]:
    effective_workspace = workspace_id or user_id
    if scope == "global":
        return None, None
    if scope == "workspace":
        return effective_workspace, None
    raise ValueError("协作专家配置仅支持 global/workspace 作用域")


def _normalize_manifest_for_storage(
    name: str,
    manifest: dict[str, Any],
    status: str = "active",
    source: str = "custom",
    builtin_baseline_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    source_manifest = dict(manifest)
    prompt_text = str(source_manifest.get("system_prompt", "") or "")
    clean_manifest: dict[str, Any] = {
        "name": source_manifest.get("name", name),
        "description": source_manifest.get("description", ""),
    }
    if source_manifest.get("model"):
        clean_manifest["model"] = source_manifest["model"]
    normalized_tools, invalid_tools = normalize_subagent_tool_paths(source_manifest.get("tools"))
    if normalized_tools:
        clean_manifest["tools"] = normalized_tools
    if invalid_tools:
        logger.warning(
            "保存子 Agent 时忽略不可用工具: name=%s invalid_tools=%s",
            name,
            invalid_tools,
        )
    for field in _EXTENDED_MANIFEST_FIELDS:
        if source_manifest.get(field) is not None:
            clean_manifest[field] = source_manifest[field]
    clean_manifest["status"] = status
    clean_manifest["source"] = source
    if builtin_baseline_id:
        clean_manifest["builtin_baseline_id"] = builtin_baseline_id
    return clean_manifest, prompt_text


def _manifest_from_db_record(record: Any) -> dict[str, Any] | None:
    manifest = dict(record.manifest or {})
    if not manifest:
        manifest = {"name": record.name, "description": record.description or ""}
    if record.system_prompt is not None:
        manifest["system_prompt"] = record.system_prompt
    elif record.prompt_path:
        try:
            prompt_path = Path(str(record.prompt_path))
            if prompt_path.exists():
                manifest["system_prompt"] = prompt_path.read_text(encoding="utf-8")
        except Exception:
            logger.debug("读取子 Agent DB prompt_path 失败: %s", record.prompt_path, exc_info=True)
    normalized_tools, invalid_tools = normalize_subagent_tool_paths(manifest.get("tools"))
    if normalized_tools:
        manifest["tools"] = normalized_tools
    else:
        manifest.pop("tools", None)
    if invalid_tools:
        logger.warning(
            "加载子 Agent DB 记录时忽略不可用工具: name=%s invalid_tools=%s",
            record.name,
            invalid_tools,
        )
    manifest["_status"] = getattr(record, "status", "active")
    manifest["_source"] = getattr(record, "source", "custom")
    manifest["_builtin_baseline_id"] = getattr(record, "builtin_baseline_id", None)
    return manifest


def _load_subagent_from_db(
    *,
    user_id: str,
    name: str,
    scope: str,
    session_id: str | None = None,
    workspace_id: str | None = None,
) -> dict[str, Any] | None:
    try:
        from app.core.database import SubAgentConfigORM, db_session

        _ensure_subagent_config_table()
        record_workspace_id, record_session_id = _scope_identity(
            user_id=user_id,
            scope=scope,
            session_id=session_id,
            workspace_id=workspace_id,
        )
        with db_session() as db:
            query = db.query(SubAgentConfigORM).filter(
                SubAgentConfigORM.user_id == user_id,
                SubAgentConfigORM.scope == scope,
                SubAgentConfigORM.name == name,
            )
            if record_workspace_id is None:
                query = query.filter(SubAgentConfigORM.workspace_id.is_(None))
            else:
                query = query.filter(SubAgentConfigORM.workspace_id == record_workspace_id)
            if record_session_id is None:
                query = query.filter(SubAgentConfigORM.session_id.is_(None))
            else:
                query = query.filter(SubAgentConfigORM.session_id == record_session_id)
            record = query.order_by(SubAgentConfigORM.updated_at.desc()).first()
            if record is None:
                return None
            return _manifest_from_db_record(record)
    except Exception:
        logger.debug("读取子 Agent SQLite 记录失败: scope=%s name=%s", scope, name, exc_info=True)
        return None


def _save_subagent_to_db(
    *,
    user_id: str,
    name: str,
    clean_manifest: dict[str, Any],
    prompt_text: str,
    scope: str,
    config_path: Path,
    prompt_path: Path,
    session_id: str | None = None,
    workspace_id: str | None = None,
    source: str = "custom",
    status: str = "active",
    builtin_baseline_id: str | None = None,
) -> None:
    from app.core.database import SubAgentConfigORM, db_session

    _ensure_subagent_config_table()
    record_workspace_id, record_session_id = _scope_identity(
        user_id=user_id,
        scope=scope,
        session_id=session_id,
        workspace_id=workspace_id,
    )
    with db_session() as db:
        try:
            query = db.query(SubAgentConfigORM).filter(
                SubAgentConfigORM.user_id == user_id,
                SubAgentConfigORM.scope == scope,
                SubAgentConfigORM.name == name,
            )
            if record_workspace_id is None:
                query = query.filter(SubAgentConfigORM.workspace_id.is_(None))
            else:
                query = query.filter(SubAgentConfigORM.workspace_id == record_workspace_id)
            if record_session_id is None:
                query = query.filter(SubAgentConfigORM.session_id.is_(None))
            else:
                query = query.filter(SubAgentConfigORM.session_id == record_session_id)
            query.delete(synchronize_session=False)
            db.add(
                SubAgentConfigORM(
                    id=f"sac_{uuid4().hex[:16]}",
                    user_id=user_id,
                    workspace_id=record_workspace_id,
                    session_id=record_session_id,
                    scope=scope,
                    name=name,
                    description=str(clean_manifest.get("description") or ""),
                    manifest=clean_manifest,
                    system_prompt=prompt_text,
                    yaml_path=str(config_path),
                    prompt_path=str(prompt_path),
                    source=source,
                    status=status,
                    builtin_baseline_id=builtin_baseline_id,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise


def _delete_subagent_from_db(
    *,
    user_id: str,
    name: str,
    scope: str,
    session_id: str | None = None,
    workspace_id: str | None = None,
) -> bool:
    try:
        from app.core.database import SubAgentConfigORM, db_session

        _ensure_subagent_config_table()
        record_workspace_id, record_session_id = _scope_identity(
            user_id=user_id,
            scope=scope,
            session_id=session_id,
            workspace_id=workspace_id,
        )
        with db_session() as db:
            query = db.query(SubAgentConfigORM).filter(
                SubAgentConfigORM.user_id == user_id,
                SubAgentConfigORM.scope == scope,
                SubAgentConfigORM.name == name,
            )
            if record_workspace_id is None:
                query = query.filter(SubAgentConfigORM.workspace_id.is_(None))
            else:
                query = query.filter(SubAgentConfigORM.workspace_id == record_workspace_id)
            if record_session_id is None:
                query = query.filter(SubAgentConfigORM.session_id.is_(None))
            else:
                query = query.filter(SubAgentConfigORM.session_id == record_session_id)
            deleted = query.delete(synchronize_session=False)
            db.commit()
            return deleted > 0
    except Exception:
        logger.debug("删除子 Agent SQLite 记录失败: scope=%s name=%s", scope, name, exc_info=True)
        return False


def _list_subagents_from_db(
    *,
    user_id: str,
    scope: str,
    session_id: str | None = None,
    workspace_id: str | None = None,
    include_disabled: bool = False,
) -> dict[str, dict[str, Any]]:
    try:
        from app.core.database import SubAgentConfigORM, db_session

        _ensure_subagent_config_table()
        record_workspace_id, record_session_id = _scope_identity(
            user_id=user_id,
            scope=scope,
            session_id=session_id,
            workspace_id=workspace_id,
        )
        with db_session() as db:
            query = db.query(SubAgentConfigORM).filter(
                SubAgentConfigORM.user_id == user_id,
                SubAgentConfigORM.scope == scope,
            )
            if record_workspace_id is None:
                query = query.filter(SubAgentConfigORM.workspace_id.is_(None))
            else:
                query = query.filter(SubAgentConfigORM.workspace_id == record_workspace_id)
            if record_session_id is None:
                query = query.filter(SubAgentConfigORM.session_id.is_(None))
            else:
                query = query.filter(SubAgentConfigORM.session_id == record_session_id)
            if not include_disabled:
                query = query.filter(SubAgentConfigORM.status == "active")
            records = query.order_by(SubAgentConfigORM.name.asc()).all()
            result: dict[str, dict[str, Any]] = {}
            for record in records:
                manifest = _manifest_from_db_record(record)
                if manifest is not None:
                    result[record.name] = manifest
            return result
    except Exception:
        logger.debug("列出子 Agent SQLite 记录失败: scope=%s", scope, exc_info=True)
        return {}


def is_subagent_installed_to_scope(
    *,
    user_id: str,
    name: str,
    scope: str,
    workspace_id: str | None = None,
) -> bool:
    """判断协作专家是否已经安装到指定配置层。"""
    normalized_name = str(name or "").strip()
    if not normalized_name:
        return False
    if scope not in {"global", "workspace"}:
        return False
    if scope == "workspace" and not workspace_id:
        return False

    if (
        _load_subagent_from_db(
            user_id=user_id,
            name=normalized_name,
            scope=scope,
            workspace_id=workspace_id,
        )
        is not None
    ):
        return True
    return _subagent_file_exists(
        user_id=user_id,
        name=normalized_name,
        scope=scope,
        workspace_id=workspace_id,
    )


def list_installed_subagent_names_for_scope(
    *,
    user_id: str,
    scope: str,
    workspace_id: str | None = None,
) -> set[str]:
    """列出指定配置层中已经安装的协作专家名称。"""
    if scope not in {"global", "workspace"}:
        return set()
    if scope == "workspace" and not workspace_id:
        return set()

    names = set(
        _list_subagents_from_db(
            user_id=user_id,
            scope=scope,
            workspace_id=workspace_id,
        ).keys()
    )
    base_dir = (
        _get_global_dir(user_id)
        if scope == "global"
        else _get_workspace_dir(user_id, workspace_id or user_id)
    )
    if base_dir.exists():
        names.update(path.stem for path in base_dir.glob("*.toml"))
    return {name for name in names if name}


def has_any_installed_subagents_for_scope(
    *,
    user_id: str,
    scope: str,
    workspace_id: str | None = None,
) -> bool:
    return bool(
        list_installed_subagent_names_for_scope(
            user_id=user_id,
            scope=scope,
            workspace_id=workspace_id,
        )
    )


def ensure_default_builtin_experts_installed(user_id: str) -> list[str]:
    """首次初始化用户默认层协作专家。

    只在用户默认层没有任何协作专家副本、策略文件和初始化标记时安装精简默认集，避免覆盖用户后续选择。
    """
    init_path = _get_global_builtin_expert_init_path(user_id)
    if init_path.exists():
        return []

    policy_path = _get_visibility_policy_path(user_id=user_id, scope="global")
    if policy_path.exists() or has_any_installed_subagents_for_scope(
        user_id=user_id,
        scope="global",
    ):
        _write_policy_file(
            init_path,
            {
                "initialized": True,
                "default_builtin_expert_ids": [],
            },
        )
        return []

    installed: list[str] = []
    for name in DEFAULT_BUILTIN_EXPERT_INSTALLS:
        enable_builtin_subagent_to_scope(
            user_id=user_id,
            name=name,
            scope="global",
        )
        installed.append(name)

    _write_policy_file(
        init_path,
        {
            "initialized": True,
            "default_builtin_expert_ids": installed,
        },
    )
    return installed


def is_valid_subagent_name(name: str) -> bool:
    """校验子 Agent 标识名格式。"""
    if not name or len(name) > 64:
        return False
    return bool(_NAME_PATTERN.match(name))


def is_system_subagent_name(name: str) -> bool:
    """检查 name 是否与代码中的系统预设子 Agent 冲突。

    仅检查 _LOCAL_BASELINES 代码内建的系统预设，不检查文件系统中
    用户自定义的全局配置（用户自定义 global 子 Agent 应允许覆盖预设）。
    """
    system_names: set[str] = set()
    for baseline in _LOCAL_BASELINES.values():
        system_names.update(baseline.subagents.keys())
    return name in system_names


# ── 保存 ────────────────────────────────────────────────────────


def save_subagent(
    user_id: str,
    name: str,
    manifest: dict[str, Any],
    scope: str = "workspace",
    session_id: str | None = None,
    workspace_id: str | None = None,
    source: str = "custom",
    status: str = "active",
    builtin_baseline_id: str | None = None,
) -> Path:
    """保存子 Agent 配置。

    Args:
        user_id: 用户 ID（用于日志和权限）
        name: 子 Agent 标识名
        manifest: 子 Agent manifest（包含 name, model, tools, system_prompt 等）
        scope: "global"/"workspace"
        workspace_id: 工作区 ID，默认使用 user_id（单工作区兼容）

    Returns:
        保存的 TOML 文件路径
    """
    effective_workspace = workspace_id or user_id
    scope = scope.lower()
    if scope == "workspace":
        base_dir = _get_workspace_dir(user_id, effective_workspace)
    elif scope == "global":
        base_dir = _get_global_dir(user_id)
    else:
        raise ValueError(f"不支持的 scope: {scope}，仅支持 'global'/'workspace'")

    base_dir.mkdir(parents=True, exist_ok=True)

    clean_manifest, prompt_text = _normalize_manifest_for_storage(
        name, manifest, status=status, source=source, builtin_baseline_id=builtin_baseline_id
    )
    prompt_path = base_dir / f"{name}_prompt.md"
    _atomic_write(prompt_path, prompt_text)

    clean_manifest["system_prompt_path"] = str(prompt_path.resolve())

    toml_path = base_dir / f"{name}.toml"
    payload = {"version": 1, "agent": clean_manifest}
    _atomic_write(toml_path, tomli_w.dumps(payload))

    db_manifest = {
        key: value for key, value in clean_manifest.items() if key != "system_prompt_path"
    }
    try:
        _save_subagent_to_db(
            user_id=user_id,
            name=name,
            clean_manifest=db_manifest,
            prompt_text=prompt_text,
            scope=scope,
            config_path=toml_path,
            prompt_path=prompt_path,
            session_id=session_id,
            workspace_id=workspace_id,
            source=source,
            status=status,
            builtin_baseline_id=builtin_baseline_id,
        )
    except Exception:
        logger.warning(
            "保存子 Agent SQLite 记录失败，已保留 TOML 镜像: user=%s name=%s scope=%s",
            user_id,
            name,
            scope,
            exc_info=True,
        )

    logger.info(
        "SubAgent saved: user=%s workspace=%s name=%s scope=%s path=%s",
        user_id,
        effective_workspace if scope != "global" else "global",
        name,
        scope,
        toml_path,
    )
    return toml_path


def enable_builtin_subagent_to_scope(
    *,
    user_id: str,
    name: str,
    scope: str,
    workspace_id: str | None = None,
) -> Path:
    """将系统提供的协作专家启用到用户默认层或工作区层。"""
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise ValueError("子 Agent 角色 ID 不能为空")
    if scope not in {"global", "workspace"}:
        raise ValueError("协作专家只能启用到 global 或 workspace 作用域")
    if scope == "workspace" and not workspace_id:
        raise ValueError("启用到工作区时必须提供 workspace_id")

    manifest = build_subagent_manifest_from_seed(normalized_name)
    if manifest is None:
        raise ValueError(f"未知的系统协作专家: {normalized_name}")

    saved_path = save_subagent(
        user_id=user_id,
        name=normalized_name,
        manifest=manifest,
        scope=scope,
        workspace_id=workspace_id,
        source="builtin",
        status="active",
        builtin_baseline_id=manifest.get("baseline_id"),
    )
    save_subagent_visibility_policy(
        user_id=user_id,
        role_id=normalized_name,
        scope=scope,
        workspace_id=workspace_id,
        catalog_visible=True,
        host_selectable=True,
        default_enabled=True,
    )
    return saved_path


# ── 加载 ────────────────────────────────────────────────────────


def load_subagent(
    user_id: str,
    name: str,
    workspace_id: str | None = None,
) -> dict[str, Any] | None:
    """加载子 Agent 配置。

    优先顺序：工作区级 > 全局级(文件) > 全局级(代码预设)。
    """
    effective_workspace = workspace_id or user_id
    # 1. 工作区级
    db_manifest = _load_subagent_from_db(
        user_id=user_id,
        name=name,
        scope="workspace",
        workspace_id=workspace_id,
    )
    if db_manifest is not None:
        return db_manifest
    workspace_path = _get_workspace_dir(user_id, effective_workspace) / f"{name}.toml"
    if workspace_path.exists():
        manifest = _parse_subagent_file(workspace_path)
        if manifest is not None:
            manifest.setdefault("_source", manifest.get("source", "custom"))
            manifest.setdefault("_status", manifest.get("status", "active"))
        return manifest

    # 2. fallback 全局级(文件系统)
    db_manifest = _load_subagent_from_db(
        user_id=user_id,
        name=name,
        scope="global",
    )
    if db_manifest is not None:
        return db_manifest
    global_path = _get_global_dir(user_id) / f"{name}.toml"
    if global_path.exists():
        manifest = _parse_subagent_file(global_path)
        if manifest is not None:
            manifest.setdefault("_source", manifest.get("source", "custom"))
            manifest.setdefault("_status", manifest.get("status", "active"))
        return manifest

    # 3. fallback 全局级(代码预设)
    return _load_global_subagent_from_code(name)


def _load_global_subagent_from_code(name: str) -> dict[str, Any] | None:
    """从代码中的 _LOCAL_BASELINES 加载 global 专家配置。"""
    for baseline in _LOCAL_BASELINES.values():
        if name not in baseline.subagents:
            continue
        binding = baseline.subagents[name]
        sub_baseline = _LOCAL_BASELINES.get(binding.baseline_id)
        if sub_baseline is None:
            continue
        manifest: dict[str, Any] = {
            "name": name,
            "description": binding.description,
        }
        try:
            prompt_text = sub_baseline.prompt_template_path.read_text(encoding="utf-8")
            manifest["system_prompt"] = prompt_text
        except Exception:
            manifest["system_prompt"] = ""
        if sub_baseline.model:
            manifest["model"] = sub_baseline.model
        if sub_baseline.tools:
            manifest["tools"] = list(sub_baseline.tools)
        return manifest
    return None


def _parse_subagent_file(config_path: Path) -> dict[str, Any] | None:
    try:
        text = config_path.read_text(encoding="utf-8")
        data = tomllib.loads(text) or {}
        manifest = data.get("agent", {})
        # 过滤已停用的角色
        if manifest.get("status") == "disabled":
            return None
        # 将 system_prompt_path 解析为实际文本
        prompt_path_str = manifest.get("system_prompt_path")
        if prompt_path_str:
            prompt_path = Path(prompt_path_str)
            if not prompt_path.is_absolute():
                prompt_path = config_path.parent / prompt_path
            if prompt_path.exists():
                manifest["system_prompt"] = prompt_path.read_text(encoding="utf-8")
        normalized_tools, invalid_tools = normalize_subagent_tool_paths(manifest.get("tools"))
        if normalized_tools:
            manifest["tools"] = normalized_tools
        else:
            manifest.pop("tools", None)
        if invalid_tools:
            logger.warning(
                "加载子 Agent 时忽略不可用工具: path=%s invalid_tools=%s",
                config_path,
                invalid_tools,
            )
        return manifest
    except Exception:
        logger.warning("解析子 Agent 文件失败: %s", config_path, exc_info=True)
        return None


# ── 列出 ────────────────────────────────────────────────────────


def list_subagents(
    user_id: str,
    workspace_id: str | None = None,
    include_disabled: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """列出所有可用子 Agent。

    Returns:
        {"global": [...], "workspace": [...]}
    """
    effective_workspace = workspace_id or user_id
    result: dict[str, list[dict[str, Any]]] = {
        "global": [],
        "workspace": [],
    }
    seen_global: set[str] = set()

    # 1. SQLite 中的全局级专家（优先）
    for name, manifest in _list_subagents_from_db(
        user_id=user_id,
        scope="global",
        include_disabled=include_disabled,
    ).items():
        seen_global.add(name)
        result["global"].append(
            {
                "name": name,
                "description": manifest.get("description", ""),
                "model": manifest.get("model"),
                "role": manifest.get("role"),
                "source": manifest.get("_source", "global"),
                "status": manifest.get("_status", "active"),
                **_visibility_fields_for_item(
                    user_id=user_id,
                    role_id=name,
                    workspace_id=workspace_id,
                ),
            }
        )

    # 2. 文件系统中的全局级专家（补齐）
    global_dir = _get_global_dir(user_id)
    if global_dir.exists():
        for toml_path in sorted(global_dir.glob("*.toml")):
            name = toml_path.stem
            if name in seen_global:
                continue
            seen_global.add(name)
            manifest = _parse_subagent_file(toml_path)
            if manifest is not None:
                result["global"].append(
                    {
                        "name": name,
                        "description": manifest.get("description", ""),
                        "model": manifest.get("model"),
                        "source": manifest.get("source", "global"),
                        "status": "active",
                        **_visibility_fields_for_item(
                            user_id=user_id,
                            role_id=name,
                            workspace_id=workspace_id,
                        ),
                    }
                )

    # 3. 代码中的系统预设（补充，去重）
    for baseline in _LOCAL_BASELINES.values():
        for role_name, binding in baseline.subagents.items():
            if role_name in seen_global:
                continue
            seen_global.add(role_name)
            result["global"].append(
                {
                    "name": role_name,
                    "description": binding.description,
                    "baseline_id": binding.baseline_id,
                    "source": "builtin",
                    "status": "active",
                    **_visibility_fields_for_item(
                        user_id=user_id,
                        role_id=role_name,
                        workspace_id=workspace_id,
                    ),
                }
            )

    # 工作区级持久化
    seen_workspace: set[str] = set()
    for name, manifest in _list_subagents_from_db(
        user_id=user_id,
        scope="workspace",
        workspace_id=workspace_id,
        include_disabled=include_disabled,
    ).items():
        seen_workspace.add(name)
        result["workspace"].append(
            {
                "name": name,
                "description": manifest.get("description", ""),
                "model": manifest.get("model"),
                "role": manifest.get("role"),
                "source": manifest.get("_source", "custom"),
                "status": manifest.get("_status", "active"),
                **_visibility_fields_for_item(
                    user_id=user_id,
                    role_id=name,
                    workspace_id=workspace_id,
                ),
            }
        )
    workspace_dir = _get_workspace_dir(user_id, effective_workspace)
    if workspace_dir.exists():
        for toml_path in sorted(workspace_dir.glob("*.toml")):
            name = toml_path.stem
            if name in seen_workspace:
                continue
            manifest = _parse_subagent_file(toml_path)
            if manifest is not None:
                result["workspace"].append(
                    {
                        "name": name,
                        "description": manifest.get("description", ""),
                        "model": manifest.get("model"),
                        "source": "custom",
                        "status": "active",
                        **_visibility_fields_for_item(
                            user_id=user_id,
                            role_id=name,
                            workspace_id=workspace_id,
                        ),
                    }
                )

    return result


# ── 加载到 Host manifest ───────────────────────────────────────


def load_custom_subagents_for_manifest(
    user_id: str,
    workspace_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    """加载自定义子 Agent，用于合并到 Host manifest 的 subagents 字段。

    Args:
        user_id: 用户 ID
        workspace_id: 工作区 ID，默认使用 user_id（单工作区兼容）

    Returns:
        {name: agent_manifest_dict}
    """
    effective_workspace = workspace_id or user_id
    customs: dict[str, dict[str, Any]] = {}

    # 先加载全局级(SQLite 优先，YAML 补齐)
    customs.update(
        _list_subagents_from_db(
            user_id=user_id,
            scope="global",
        )
    )
    global_dir = _get_global_dir(user_id)
    if global_dir.exists():
        for toml_path in global_dir.glob("*.toml"):
            name = toml_path.stem
            if name in customs:
                continue
            manifest = _parse_subagent_file(toml_path)
            if manifest is not None:
                customs[name] = manifest

    # 再加载工作区级持久化（覆盖全局级同名配置）
    customs.update(
        _list_subagents_from_db(
            user_id=user_id,
            scope="workspace",
            workspace_id=workspace_id,
        )
    )
    workspace_dir = _get_workspace_dir(user_id, effective_workspace)
    if workspace_dir.exists():
        for toml_path in workspace_dir.glob("*.toml"):
            name = toml_path.stem
            if (
                name in customs
                and _load_subagent_from_db(
                    user_id=user_id,
                    name=name,
                    scope="workspace",
                    workspace_id=workspace_id,
                )
                is not None
            ):
                continue
            manifest = _parse_subagent_file(toml_path)
            if manifest is not None:
                customs[name] = manifest

    return customs


# ── 删除 ────────────────────────────────────────────────────────


def delete_subagent(
    user_id: str,
    name: str,
    scope: str = "workspace",
    session_id: str | None = None,
    workspace_id: str | None = None,
) -> bool:
    """删除子 Agent 配置。

    Args:
        scope: "global"/"workspace"
        workspace_id: 工作区 ID，默认使用 user_id（单工作区兼容）
    """
    effective_workspace = workspace_id or user_id
    if scope == "workspace":
        base_dir = _get_workspace_dir(user_id, effective_workspace)
    elif scope == "global":
        base_dir = _get_global_dir(user_id)
    else:
        return False

    toml_path = base_dir / f"{name}.toml"
    prompt_path = base_dir / f"{name}_prompt.md"

    deleted = _delete_subagent_from_db(
        user_id=user_id,
        name=name,
        scope=scope,
        session_id=session_id,
        workspace_id=workspace_id,
    )
    if toml_path.exists():
        toml_path.unlink()
        deleted = True
    if prompt_path.exists():
        prompt_path.unlink()
        deleted = True

    if scope == "global" and is_system_subagent_name(name):
        enabled = load_enabled_experts(user_id)
        if enabled is not None and name in enabled:
            enabled.remove(name)
            save_enabled_experts(user_id, enabled)
            deleted = True

    if deleted and scope in {"global", "workspace"}:
        policy_path = _get_visibility_policy_path(
            user_id=user_id,
            scope=scope,
            workspace_id=workspace_id,
        )
        policy_payload = _read_visibility_policy_file(policy_path)
        roles_payload = policy_payload.get("roles")
        if isinstance(roles_payload, dict) and name in roles_payload:
            roles_payload.pop(name, None)
            policy_payload["roles"] = roles_payload
            _write_policy_file(policy_path, policy_payload)

    if deleted:
        logger.info(
            "SubAgent deleted: user=%s workspace=%s name=%s scope=%s",
            user_id,
            effective_workspace,
            name,
            scope,
        )
    return deleted


# ── 运行时查找 ──────────────────────────────────────────────────


def load_subagent_for_runtime(
    user_id: str,
    name: str,
    session_id: str | None = None,
    workspace_id: str | None = None,
) -> dict[str, Any] | None:
    """运行时查找子 Agent 配置。

    查找顺序：workspace > global，跳过已停用的角色。
    与 load_subagent 不同，此函数不查找 session 级，也不 fallback 到代码预设。
    """
    if not is_subagent_dispatch_enabled(
        user_id=user_id,
        role_id=name,
        workspace_id=workspace_id,
    ):
        return None

    # 1. 查工作区（DB 优先，YAML 补齐）
    db_manifest = _load_subagent_from_db(
        user_id=user_id,
        name=name,
        scope="workspace",
        workspace_id=workspace_id,
    )
    if db_manifest is not None:
        if db_manifest.get("_status") != "disabled":
            return db_manifest
    else:
        effective_workspace = workspace_id or user_id
        workspace_path = _get_workspace_dir(user_id, effective_workspace) / f"{name}.toml"
        if workspace_path.exists():
            manifest = _parse_subagent_file(workspace_path)
            if manifest is not None:
                return manifest

    # 2. fallback 全局（DB 优先，YAML 补齐）
    db_manifest = _load_subagent_from_db(
        user_id=user_id,
        name=name,
        scope="global",
    )
    if db_manifest is not None:
        if db_manifest.get("_status") != "disabled":
            return db_manifest
    else:
        global_path = _get_global_dir(user_id) / f"{name}.toml"
        if global_path.exists():
            manifest = _parse_subagent_file(global_path)
            if manifest is not None:
                return manifest

    return None
