from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any

from app.core.config import WORKSPACE_DIR
from app.models.expert import (
    ExpertRoleSummary,
    GlobalCollaborationPolicyResponse,
    GlobalExpertCatalogResponse,
    SessionExpertPolicyResponse,
    WorkspaceCollaborationPolicyResponse,
    WorkspaceExpertCatalogResponse,
)
from app.models.session import normalize_collaboration_policy
from app.services.agent.system_presets import (
    compute_expert_catalog_fingerprint_from_preset,
    get_role_type_default_tools,
    resolve_system_agent_preset_from_path,
)
from app.services.runtime_tooling import canonicalize_runtime_tool_name
from app.services.session import SessionManager
from app.services.workspace_registry import get_workspace_registry_service

CONFIGURED_ROLE_IDS_INHERIT = object()


def _subagent_catalog_module():
    from app.core import config as config_module
    from app.services.agent import subagent_catalog

    configured_root = Path(config_module.WORKSPACE_DIR)
    expert_root = Path(WORKSPACE_DIR)
    catalog_root = Path(subagent_catalog.WORKSPACE_DIR)
    if expert_root != configured_root:
        effective_root = expert_root
    elif catalog_root != configured_root:
        effective_root = catalog_root
    else:
        effective_root = expert_root
    subagent_catalog.WORKSPACE_DIR = effective_root
    return subagent_catalog


def _read_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    data = tomllib.loads(text) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _unique_tool_names(tool_paths: list[str]) -> list[str]:
    names: list[str] = []
    for tool_path in tool_paths:
        name = str(tool_path).split(":")[-1].strip()
        if name and name not in names:
            names.append(name)
    return names


def _normalize_tool_ids(tool_ids: Any) -> list[str]:
    if not isinstance(tool_ids, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_tool_id in tool_ids:
        tool_id = canonicalize_runtime_tool_name(str(raw_tool_id or "").strip())
        if not tool_id or tool_id in seen:
            continue
        normalized.append(tool_id)
        seen.add(tool_id)
    return normalized


def _normalize_enabled_role_ids(
    configured_role_ids: list[str] | None | object,
    available_role_ids: list[str],
    default_role_ids: list[str] | None = None,
) -> list[str]:
    if configured_role_ids is CONFIGURED_ROLE_IDS_INHERIT:
        return list(default_role_ids if default_role_ids is not None else available_role_ids)
    if configured_role_ids is None:
        return []

    normalized: list[str] = []
    for role_id in configured_role_ids:
        text = str(role_id or "").strip()
        if text and text in available_role_ids and text not in normalized:
            normalized.append(text)
    return normalized


def _apply_visibility_to_role(
    role: ExpertRoleSummary,
    *,
    user_id: str,
    workspace_id: str | None,
) -> ExpertRoleSummary:
    installed_to_global = False
    installed_to_workspace = False
    try:
        subagent_catalog = _subagent_catalog_module()

        policy = subagent_catalog.resolve_subagent_visibility_policy(
            user_id=user_id,
            role_id=role.role_id,
            workspace_id=workspace_id,
        )
        installed_to_global = subagent_catalog.is_subagent_installed_to_scope(
            user_id=user_id,
            name=role.role_id,
            scope="global",
        )
        installed_to_workspace = (
            subagent_catalog.is_subagent_installed_to_scope(
                user_id=user_id,
                name=role.role_id,
                scope="workspace",
                workspace_id=workspace_id,
            )
            if workspace_id
            else False
        )
    except Exception:
        return role

    installed_scope = (
        "workspace" if installed_to_workspace else "global" if installed_to_global else "system"
    )

    return role.model_copy(
        update={
            "catalog_visible": policy.catalog_visible,
            "host_selectable": policy.host_selectable,
            "default_enabled": policy.default_enabled,
            "visibility_source": policy.visibility_source,
            "installed_to_global": installed_to_global,
            "installed_to_workspace": installed_to_workspace,
            "installed_scope": installed_scope,
            "lock_reason": policy.lock_reason,
        }
    )


def _read_configured_enabled_role_ids(
    raw_roles: Any,
    selectable_role_ids: list[str],
) -> list[str] | None:
    if not isinstance(raw_roles, dict):
        return None
    selectable_set = set(selectable_role_ids)
    explicit_enabled: list[str] = []
    has_explicit_enabled = False
    for role_id in selectable_role_ids:
        role_payload = raw_roles.get(role_id)
        if not isinstance(role_payload, dict):
            continue
        if "enabled" in role_payload or "default_enabled" in role_payload:
            has_explicit_enabled = True
            if bool(role_payload.get("enabled", role_payload.get("default_enabled"))):
                explicit_enabled.append(role_id)
    for raw_role_id, role_payload in raw_roles.items():
        role_id = str(raw_role_id or "").strip()
        if role_id in selectable_set:
            continue
        if not isinstance(role_payload, dict):
            continue
        if "enabled" in role_payload or "default_enabled" in role_payload:
            has_explicit_enabled = True
    return explicit_enabled if has_explicit_enabled else None


def _resolve_role_artifact_snapshot(
    *,
    profile_path: Path,
    role_id: str,
    subagent_spec: dict[str, Any],
) -> dict[str, str | None]:
    raw_subagent_path = subagent_spec.get("path")
    if not isinstance(raw_subagent_path, str):
        return {
            "role_id": role_id,
            "agent_file": None,
            "agent_sha256": None,
            "prompt_file": None,
            "prompt_sha256": None,
        }

    role_path = (profile_path.parent / raw_subagent_path).resolve()
    role_sha256 = (
        hashlib.sha256(role_path.read_bytes()).hexdigest()
        if role_path.exists() and role_path.is_file()
        else None
    )

    prompt_path: Path | None = None
    if role_path.exists() and role_path.is_file():
        role_data = _read_config(role_path)
        role_agent = role_data.get("agent", {})
        if isinstance(role_agent, dict):
            raw_prompt_path = role_agent.get("system_prompt_path")
            if isinstance(raw_prompt_path, str) and raw_prompt_path.strip():
                prompt_path = (role_path.parent / raw_prompt_path).resolve()

    prompt_sha256 = (
        hashlib.sha256(prompt_path.read_bytes()).hexdigest()
        if prompt_path is not None and prompt_path.exists() and prompt_path.is_file()
        else None
    )

    return {
        "role_id": role_id,
        "agent_file": role_path.name if role_path.exists() else None,
        "agent_sha256": role_sha256,
        "prompt_file": (
            prompt_path.name if prompt_path is not None and prompt_path.exists() else None
        ),
        "prompt_sha256": prompt_sha256,
    }


def _default_display_name(role_id: str) -> str:
    mapping = {
        "data_analyst": "数据分析专家",
        "researcher": "研究专家",
        "coder": "代码专家",
        "reviewer": "审查专家",
    }
    return mapping.get(role_id, role_id)


def _default_agent_artifact_name(role_id: str, baseline_id: str) -> str:
    return baseline_id or role_id


def _build_role_summary_from_preset(
    *,
    role_id: str,
    binding_description: str,
    baseline: Any,
) -> ExpertRoleSummary:
    expert_profile = baseline.expert_profile or {}
    policy = str(baseline.tool_policy or "").strip().lower() or "inherit"
    if policy == "allowlist":
        effective_tools = _normalize_string_list(list(get_role_type_default_tools(role_id)))
    else:
        effective_tools = []
    tool_names = _unique_tool_names(effective_tools)
    description = (
        str(expert_profile.get("description") or "").strip()
        or str(binding_description or "").strip()
        or str(baseline.when_to_use or "").strip()
        or _default_display_name(role_id)
    )
    return ExpertRoleSummary(
        role_id=role_id,
        display_name=str(
            expert_profile.get("display_name") or _default_display_name(role_id)
        ).strip(),
        description=description,
        when_to_use=str(baseline.when_to_use or "").strip(),
        default_model=str(baseline.model or "").strip() or None,
        tool_policy=policy,
        tool_ids=effective_tools,
        tool_names=tool_names,
        tool_count=len(tool_names),
        permissions=_normalize_string_list(expert_profile.get("permissions")),
        capabilities=_normalize_string_list(expert_profile.get("capabilities")),
        supports_background=bool(expert_profile.get("supports_background", True)),
        agent_file=_default_agent_artifact_name(role_id, baseline.baseline_id),
        source="system",
    )


def build_expert_catalog_from_profile(
    profile_path: Path,
) -> list[ExpertRoleSummary]:
    preset = resolve_system_agent_preset_from_path(profile_path)
    if preset is not None:
        roles: list[ExpertRoleSummary] = []
        for role_id, binding in preset.baseline.subagents.items():
            baseline = preset.subagent_baselines[binding.baseline_id]
            roles.append(
                _build_role_summary_from_preset(
                    role_id=str(role_id).strip(),
                    binding_description=binding.description,
                    baseline=baseline,
                )
            )
        return roles

    profile_data = _read_config(profile_path)
    subagents = profile_data.get("agent", {}).get("subagents", {})
    if not isinstance(subagents, dict):
        return []

    roles: list[ExpertRoleSummary] = []
    for role_id, subagent_spec in subagents.items():
        if not isinstance(subagent_spec, dict):
            continue

        raw_subagent_path = subagent_spec.get("path")
        if not isinstance(raw_subagent_path, str):
            continue

        role_path = (profile_path.parent / raw_subagent_path).resolve()
        if not role_path.exists():
            continue

        role_data = _read_config(role_path)
        role_agent = role_data.get("agent", {})
        if not isinstance(role_agent, dict):
            continue

        expert_profile = role_agent.get("expert_profile", {})
        if not isinstance(expert_profile, dict):
            expert_profile = {}

        tool_paths = _normalize_tool_ids(
            role_agent.get("allowed_tools") or role_agent.get("tools") or []
        )
        tool_names = _unique_tool_names(tool_paths)
        role_id_text = str(role_id).strip()
        description = (
            str(expert_profile.get("description") or "").strip()
            or str(subagent_spec.get("description") or "").strip()
            or str(role_agent.get("when_to_use") or "").strip()
            or _default_display_name(role_id_text)
        )
        roles.append(
            ExpertRoleSummary(
                role_id=role_id_text,
                display_name=str(
                    expert_profile.get("display_name") or _default_display_name(role_id_text)
                ).strip(),
                description=description,
                when_to_use=str(role_agent.get("when_to_use") or "").strip(),
                default_model=str(role_agent.get("model") or "").strip() or None,
                tool_policy="allowlist" if tool_paths else "inherit",
                tool_ids=tool_paths,
                tool_names=tool_names,
                tool_count=len(tool_names),
                permissions=_normalize_string_list(expert_profile.get("permissions")),
                capabilities=_normalize_string_list(expert_profile.get("capabilities")),
                supports_background=bool(expert_profile.get("supports_background", True)),
                agent_file=role_path.name,
                source="system",
            )
        )

    return roles


def _build_role_summary_from_custom_manifest(
    *,
    role_id: str,
    manifest: dict[str, Any],
    scope: str,
) -> ExpertRoleSummary:
    tools = _normalize_tool_ids(manifest.get("tools") or [])
    tool_names = _unique_tool_names(tools)
    description = str(manifest.get("description") or "").strip()
    return ExpertRoleSummary(
        role_id=role_id,
        display_name=str(manifest.get("display_name") or role_id).strip(),
        description=description or role_id,
        when_to_use=str(manifest.get("when_to_use") or "").strip(),
        default_model=str(manifest.get("model") or "").strip() or None,
        tool_policy="allowlist" if tools else "inherit",
        tool_ids=tools,
        tool_names=tool_names,
        tool_count=len(tool_names),
        permissions=_normalize_string_list(manifest.get("permissions")),
        capabilities=_normalize_string_list(manifest.get("capabilities")),
        supports_background=bool(manifest.get("supports_background", True)),
        agent_file=role_id,
        source=scope if scope in {"global", "workspace"} else "custom",
    )


def build_expert_catalog_for_scope(
    *,
    profile_path: Path,
    user_id: str,
    workspace_id: str | None = None,
    session_id: str | None = None,
) -> list[ExpertRoleSummary]:
    roles = build_expert_catalog_from_profile(profile_path)
    seen = {role.role_id for role in roles}

    try:
        subagent_catalog = _subagent_catalog_module()

        catalog = subagent_catalog.list_subagents(
            user_id=user_id,
            workspace_id=workspace_id,
            include_disabled=False,
        )
        for scope in ("global", "workspace"):
            for item in catalog.get(scope, []):
                role_id = str(item.get("name") or "").strip()
                if not role_id or role_id in seen:
                    continue
                manifest = subagent_catalog.load_subagent(
                    user_id,
                    role_id,
                    workspace_id=workspace_id,
                )
                if not isinstance(manifest, dict):
                    manifest = item
                roles.append(
                    _build_role_summary_from_custom_manifest(
                        role_id=role_id,
                        manifest=manifest,
                        scope=scope,
                    )
                )
                seen.add(role_id)
    except Exception:
        # 自定义目录缺失不能影响系统预设目录。
        pass

    return [
        _apply_visibility_to_role(
            role,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        for role in roles
    ]


def build_installed_expert_catalog_for_scope(
    *,
    profile_path: Path,
    user_id: str,
    scope: str,
    workspace_id: str | None = None,
    include_global_in_workspace: bool = False,
) -> list[ExpertRoleSummary]:
    if scope not in {"global", "workspace"}:
        return []

    roles = build_expert_catalog_for_scope(
        profile_path=profile_path,
        user_id=user_id,
        workspace_id=workspace_id if scope == "workspace" else None,
    )
    if scope == "global":
        return [role for role in roles if role.installed_to_global or role.source == "global"]

    return [
        role
        for role in roles
        if role.installed_to_workspace
        or role.source == "workspace"
        or (include_global_in_workspace and role.installed_to_global)
    ]


def compute_expert_catalog_fingerprint(profile_path: Path) -> str:
    preset = resolve_system_agent_preset_from_path(profile_path)
    if preset is not None:
        return compute_expert_catalog_fingerprint_from_preset(preset)

    profile_data = _read_config(profile_path)
    subagents = profile_data.get("agent", {}).get("subagents", {})
    artifact_snapshots: list[dict[str, str | None]] = []
    if isinstance(subagents, dict):
        for role_id, subagent_spec in sorted(subagents.items()):
            if not isinstance(subagent_spec, dict):
                continue
            artifact_snapshots.append(
                _resolve_role_artifact_snapshot(
                    profile_path=profile_path,
                    role_id=str(role_id).strip(),
                    subagent_spec=subagent_spec,
                )
            )

    payload = {
        "roles": [
            role.model_dump(mode="json") for role in build_expert_catalog_from_profile(profile_path)
        ],
        "artifacts": artifact_snapshots,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def resolve_workspace_profile_path(user_id: str, workspace_id: str) -> Path:
    from app.services.agent.config import resolve_agent_system_default_paths

    _workspace = get_workspace_registry_service().get_workspace(
        user_id,
        workspace_id,
        include_conversations=False,
    )
    profile_path, _ = resolve_agent_system_default_paths(
        sandbox_mode="local",
    )
    return profile_path


def resolve_global_profile_path(user_id: str) -> Path:
    from app.services.agent.config import resolve_agent_system_default_paths

    profile_path, _ = resolve_agent_system_default_paths(
        sandbox_mode="local",
    )
    return profile_path


def resolve_session_profile_path(user_id: str, session_id: str) -> Path:
    from app.services.agent.config import resolve_agent_system_default_paths

    metadata = SessionManager(WORKSPACE_DIR).get_session(session_id, user_id)
    if metadata is None:
        raise FileNotFoundError("会话不存在")

    profile_path, _ = resolve_agent_system_default_paths(
        sandbox_mode=getattr(metadata, "sandbox_mode", None),
    )
    return profile_path


def get_workspace_expert_catalog(
    *,
    user_id: str,
    workspace_id: str,
) -> WorkspaceExpertCatalogResponse:
    _subagent_catalog_module().ensure_default_builtin_experts_installed(user_id)
    profile_path = resolve_workspace_profile_path(user_id, workspace_id)
    preset = resolve_system_agent_preset_from_path(profile_path)
    return WorkspaceExpertCatalogResponse(
        workspace_id=workspace_id,
        profile_name=preset.config_ref if preset is not None else profile_path.name,
        roles=build_expert_catalog_for_scope(
            profile_path=profile_path,
            user_id=user_id,
            workspace_id=workspace_id,
        ),
    )


def get_global_expert_catalog(
    *,
    user_id: str,
) -> GlobalExpertCatalogResponse:
    _subagent_catalog_module().ensure_default_builtin_experts_installed(user_id)
    profile_path = resolve_global_profile_path(user_id)
    preset = resolve_system_agent_preset_from_path(profile_path)
    return GlobalExpertCatalogResponse(
        profile_name=preset.config_ref if preset is not None else profile_path.name,
        roles=build_expert_catalog_for_scope(
            profile_path=profile_path,
            user_id=user_id,
            workspace_id=None,
        ),
    )


def get_workspace_collaboration_policy(
    *,
    user_id: str,
    workspace_id: str,
) -> WorkspaceCollaborationPolicyResponse:
    _subagent_catalog_module().ensure_default_builtin_experts_installed(user_id)
    profile_path = resolve_workspace_profile_path(user_id, workspace_id)
    preset = resolve_system_agent_preset_from_path(profile_path)
    available_roles = build_installed_expert_catalog_for_scope(
        profile_path=profile_path,
        user_id=user_id,
        scope="workspace",
        workspace_id=workspace_id,
        include_global_in_workspace=True,
    )
    selectable_roles = [role for role in available_roles if role.host_selectable]
    available_role_ids = [role.role_id for role in selectable_roles]
    available_role_tool_ids = {role.role_id: list(role.tool_ids) for role in selectable_roles}

    from app.services.agent.subagent_catalog import (
        load_workspace_collaboration_policy,
        resolve_workspace_collaboration_runtime_policy,
        resolve_workspace_role_tool_ids,
    )

    global_policy = load_workspace_collaboration_policy(
        user_id=user_id,
        scope="global",
    )
    global_enabled_role_ids = _read_configured_enabled_role_ids(
        global_policy.get("roles"),
        available_role_ids,
    )

    raw_policy = load_workspace_collaboration_policy(
        user_id=user_id,
        scope="workspace",
        workspace_id=workspace_id,
    )
    raw_roles = raw_policy.get("roles")
    configured_enabled_role_ids = _read_configured_enabled_role_ids(
        raw_roles,
        available_role_ids,
    )

    configured_role_tool_ids: dict[str, list[str]] = {}
    for role in selectable_roles:
        configured_tools = resolve_workspace_role_tool_ids(
            user_id=user_id,
            role_id=role.role_id,
            workspace_id=workspace_id,
        )
        if configured_tools is None:
            continue
        selected_tool_ids = [
            tool_id for tool_id in role.tool_ids if tool_id in set(configured_tools)
        ]
        if selected_tool_ids != role.tool_ids:
            configured_role_tool_ids[role.role_id] = selected_tool_ids

    effective_role_tool_ids = _resolve_effective_role_tool_ids(
        configured_role_tool_ids or None,
        available_role_tool_ids,
    )

    return WorkspaceCollaborationPolicyResponse(
        workspace_id=workspace_id,
        profile_name=preset.config_ref if preset is not None else profile_path.name,
        configured_enabled_role_ids=configured_enabled_role_ids,
        configured_role_tool_ids=configured_role_tool_ids or None,
        effective_enabled_role_ids=_normalize_enabled_role_ids(
            (
                configured_enabled_role_ids
                if configured_enabled_role_ids is not None
                else CONFIGURED_ROLE_IDS_INHERIT
            ),
            available_role_ids,
            global_enabled_role_ids or [],
        ),
        effective_role_tool_ids=effective_role_tool_ids,
        available_roles=available_roles,
        collaboration_policy=normalize_collaboration_policy(
            resolve_workspace_collaboration_runtime_policy(
                user_id=user_id,
                workspace_id=workspace_id,
            )
        ),
    )


def get_global_collaboration_policy(
    *,
    user_id: str,
) -> GlobalCollaborationPolicyResponse:
    _subagent_catalog_module().ensure_default_builtin_experts_installed(user_id)
    profile_path = resolve_global_profile_path(user_id)
    preset = resolve_system_agent_preset_from_path(profile_path)
    available_roles = build_installed_expert_catalog_for_scope(
        profile_path=profile_path,
        user_id=user_id,
        scope="global",
    )
    selectable_roles = [role for role in available_roles if role.host_selectable]
    available_role_ids = [role.role_id for role in selectable_roles]
    _default_role_ids = [role.role_id for role in selectable_roles if role.default_enabled]
    available_role_tool_ids = {role.role_id: list(role.tool_ids) for role in selectable_roles}

    from app.services.agent.subagent_catalog import (
        load_workspace_collaboration_policy,
        resolve_workspace_collaboration_runtime_policy,
        resolve_workspace_role_tool_ids,
    )

    raw_policy = load_workspace_collaboration_policy(
        user_id=user_id,
        scope="global",
    )
    raw_roles = raw_policy.get("roles")
    configured_enabled_role_ids = _read_configured_enabled_role_ids(
        raw_roles,
        available_role_ids,
    )

    configured_role_tool_ids: dict[str, list[str]] = {}
    for role in selectable_roles:
        configured_tools = resolve_workspace_role_tool_ids(
            user_id=user_id,
            role_id=role.role_id,
            workspace_id=None,
        )
        if configured_tools is None:
            continue
        selected_tool_ids = [
            tool_id for tool_id in role.tool_ids if tool_id in set(configured_tools)
        ]
        if selected_tool_ids != role.tool_ids:
            configured_role_tool_ids[role.role_id] = selected_tool_ids

    effective_role_tool_ids = _resolve_effective_role_tool_ids(
        configured_role_tool_ids or None,
        available_role_tool_ids,
    )

    return GlobalCollaborationPolicyResponse(
        profile_name=preset.config_ref if preset is not None else profile_path.name,
        configured_enabled_role_ids=configured_enabled_role_ids,
        configured_role_tool_ids=configured_role_tool_ids or None,
        effective_enabled_role_ids=_normalize_enabled_role_ids(
            configured_enabled_role_ids,
            available_role_ids,
        ),
        effective_role_tool_ids=effective_role_tool_ids,
        available_roles=available_roles,
        collaboration_policy=normalize_collaboration_policy(
            resolve_workspace_collaboration_runtime_policy(
                user_id=user_id,
                workspace_id=None,
            )
        ),
    )


def get_session_expert_policy(
    *,
    user_id: str,
    session_id: str,
) -> SessionExpertPolicyResponse:
    _subagent_catalog_module().ensure_default_builtin_experts_installed(user_id)
    session_manager = SessionManager(WORKSPACE_DIR)
    metadata = session_manager.get_session(session_id, user_id)
    if metadata is None:
        raise FileNotFoundError("会话不存在")
    raw_configured_role_ids = getattr(metadata, "enabled_expert_role_ids", None)

    profile_path = resolve_session_profile_path(user_id, session_id)
    preset = resolve_system_agent_preset_from_path(profile_path)
    workspace_id: str | None = None
    try:
        workspace_id = get_workspace_registry_service().find_workspace_id_by_session_id(
            user_id,
            session_id,
        )
    except Exception:
        workspace_id = None
    available_roles = build_installed_expert_catalog_for_scope(
        profile_path=profile_path,
        user_id=user_id,
        scope="workspace",
        workspace_id=workspace_id,
        include_global_in_workspace=True,
    )
    if isinstance(raw_configured_role_ids, list):
        configured_set = {
            str(role_id or "").strip()
            for role_id in raw_configured_role_ids
            if str(role_id or "").strip()
        }
        existing_role_ids = {role.role_id for role in available_roles}
        if not configured_set.issubset(existing_role_ids):
            full_catalog = build_expert_catalog_for_scope(
                profile_path=profile_path,
                user_id=user_id,
                workspace_id=workspace_id,
            )
            available_roles.extend(
                role
                for role in full_catalog
                if role.role_id in configured_set and role.role_id not in existing_role_ids
            )
    selectable_roles = [role for role in available_roles if role.host_selectable]
    available_role_ids = [role.role_id for role in selectable_roles]
    default_role_ids = [role.role_id for role in selectable_roles if role.default_enabled]
    available_role_tool_ids = {role.role_id: list(role.tool_ids) for role in selectable_roles}
    configured_role_ids = (
        _normalize_enabled_role_ids(
            raw_configured_role_ids,
            available_role_ids,
        )
        if raw_configured_role_ids is not None
        else None
    )
    configured_role_tool_ids = _normalize_configured_role_tool_ids(
        getattr(metadata, "expert_role_tool_ids", None),
        available_role_tool_ids,
    )
    effective_enabled_role_ids = _normalize_enabled_role_ids(
        configured_role_ids if configured_role_ids is not None else CONFIGURED_ROLE_IDS_INHERIT,
        available_role_ids,
        default_role_ids,
    )
    effective_role_tool_ids = _resolve_effective_role_tool_ids(
        configured_role_tool_ids,
        available_role_tool_ids,
    )

    return SessionExpertPolicyResponse(
        session_id=session_id,
        profile_name=preset.config_ref if preset is not None else profile_path.name,
        policy_mode="custom" if configured_role_ids is not None else "inherit_all",
        configured_enabled_role_ids=configured_role_ids,
        configured_role_tool_ids=configured_role_tool_ids,
        effective_enabled_role_ids=effective_enabled_role_ids,
        effective_role_tool_ids=effective_role_tool_ids,
        available_roles=available_roles,
        collaboration_policy=normalize_collaboration_policy(
            getattr(metadata, "collaboration_policy", None)
        ),
    )


def _normalize_configured_role_tool_ids(
    configured_role_tool_ids: Any,
    available_role_tool_ids: dict[str, list[str]],
) -> dict[str, list[str]] | None:
    if not isinstance(configured_role_tool_ids, dict):
        return None

    normalized: dict[str, list[str]] = {}
    for raw_role_id, raw_tool_ids in configured_role_tool_ids.items():
        role_id = str(raw_role_id or "").strip()
        if role_id not in available_role_tool_ids:
            continue

        requested_tool_ids = _normalize_tool_ids(raw_tool_ids)
        requested_tool_id_set = set(requested_tool_ids)
        system_tool_ids = available_role_tool_ids[role_id]
        selected_tool_ids = [
            tool_id for tool_id in system_tool_ids if tool_id in requested_tool_id_set
        ]
        if selected_tool_ids != system_tool_ids:
            normalized[role_id] = selected_tool_ids

    return normalized or None


def _resolve_effective_role_tool_ids(
    configured_role_tool_ids: dict[str, list[str]] | None,
    available_role_tool_ids: dict[str, list[str]],
) -> dict[str, list[str]]:
    if configured_role_tool_ids is None:
        return {role_id: list(tool_ids) for role_id, tool_ids in available_role_tool_ids.items()}

    effective: dict[str, list[str]] = {}
    for role_id, system_tool_ids in available_role_tool_ids.items():
        if role_id in configured_role_tool_ids:
            effective[role_id] = list(configured_role_tool_ids[role_id])
            continue
        effective[role_id] = list(system_tool_ids)
    return effective
