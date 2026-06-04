from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import get_user_global_config_dir
from app.models.task_profile import build_task_profile_summary
from app.services.agent_config import AgentMode, get_agent_config_service
from app.services.memory import resolve_session_memory_preview
from app.skills import get_skill_manager

CONFIG_DIR_RELATIVE_PATH = Path(".aiasys")
DATABASE_MOUNT_RELATIVE_PATH = CONFIG_DIR_RELATIVE_PATH / "database-mounts.json"
RUNTIME_CONFIG_STATE_RELATIVE_PATH = (
    Path(".aiasys/session") / "config" / "runtime-config-state.json"
)
_STATE_UNSET = object()


def ensure_workspace_layout(session_dir: Path) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    state_path = get_runtime_config_state_path(session_dir)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    # 注意：不再预创建 mcp.yaml。MCP 配置改为全局 store + 工作区 mcp_config.json 模型。


def get_workspace_database_mount_path(session_dir: Path) -> Path:
    return session_dir / DATABASE_MOUNT_RELATIVE_PATH


def _try_infer_user_id_from_path(path: Path) -> str | None:
    try:
        return path.parent.name
    except Exception:
        return None


def _list_available_knowledge_base_ids(user_id: str) -> list[str]:
    try:
        from app.knowledge import get_sqlite_kb_service

        return [
            str(kb.id)
            for kb in get_sqlite_kb_service().list_knowledge_bases(user_id)
            if getattr(kb, "id", None)
        ]
    except Exception:
        return []


def _list_available_knowledge_graph_ids(user_id: str) -> list[str]:
    try:
        from app.graphrag.core import SQLiteGraphStore

        return [g["kg_id"] for g in SQLiteGraphStore.list_graphs(user_id)]
    except Exception:
        return []


def normalize_workspace_database_mount_data(data: Any) -> dict[str, Any]:
    version = 1
    raw_ids: Any = []
    if isinstance(data, dict):
        raw_version = data.get("version")
        if isinstance(raw_version, int) and raw_version > 0:
            version = raw_version
        raw_ids = data.get("connector_ids", [])

    connector_ids: list[str] = []
    if isinstance(raw_ids, list):
        for item in raw_ids:
            normalized = str(item).strip()
            if normalized and normalized not in connector_ids:
                connector_ids.append(normalized)

    return {
        "version": version,
        "connector_ids": connector_ids,
    }


def _infer_workspace_identity(session_dir: Path) -> tuple[str | None, str | None]:
    """从工作区目录路径推断 user_id / workspace_id。"""
    try:
        workspace_id = session_dir.name.strip()
        user_id = session_dir.parent.name.strip()
    except Exception:
        return None, None
    if not user_id or not workspace_id:
        return None, None
    return user_id, workspace_id


def _ensure_workspace_resource_defaults_table() -> None:
    from app.core.database import WorkspaceResourceDefaultORM, engine

    WorkspaceResourceDefaultORM.__table__.create(bind=engine, checkfirst=True)


def _read_workspace_database_defaults_from_sqlite(
    session_dir: Path,
) -> dict[str, Any] | None:
    user_id, workspace_id = _infer_workspace_identity(session_dir)
    if not user_id or not workspace_id:
        return None
    try:
        from app.core.database import WorkspaceResourceDefaultORM, db_session

        _ensure_workspace_resource_defaults_table()
        with db_session() as db:
            records = (
                db.query(WorkspaceResourceDefaultORM)
                .filter(
                    WorkspaceResourceDefaultORM.user_id == user_id,
                    WorkspaceResourceDefaultORM.workspace_id == workspace_id,
                    WorkspaceResourceDefaultORM.resource_type == "database",
                )
                .order_by(WorkspaceResourceDefaultORM.sort_order.asc())
                .all()
            )
            if not records:
                return None
            connector_ids: list[str] = []
            for record in records:
                connector_id = str(record.resource_id or "").strip()
                if connector_id == "__none__":
                    continue
                if connector_id and connector_id not in connector_ids:
                    connector_ids.append(connector_id)
            return {"version": 1, "connector_ids": connector_ids}
    except Exception:
        return None


def _write_workspace_database_defaults_to_sqlite(
    session_dir: Path,
    connector_ids: list[str],
) -> None:
    user_id, workspace_id = _infer_workspace_identity(session_dir)
    if not user_id or not workspace_id:
        return
    from app.core.database import WorkspaceResourceDefaultORM, db_session

    _ensure_workspace_resource_defaults_table()
    with db_session() as db:
        try:
            db.query(WorkspaceResourceDefaultORM).filter(
                WorkspaceResourceDefaultORM.user_id == user_id,
                WorkspaceResourceDefaultORM.workspace_id == workspace_id,
                WorkspaceResourceDefaultORM.resource_type == "database",
            ).delete(synchronize_session=False)
            effective_ids = connector_ids or ["__none__"]
            for index, connector_id in enumerate(effective_ids):
                db.add(
                    WorkspaceResourceDefaultORM(
                        id=f"wrd_{uuid4().hex[:16]}",
                        user_id=user_id,
                        workspace_id=workspace_id,
                        resource_type="database",
                        resource_id=connector_id,
                        resource_scope=(
                            "workspace" if connector_id != "__none__" else "empty_marker"
                        ),
                        sort_order=index,
                        meta_info={},
                    )
                )
            db.commit()
        except Exception:
            db.rollback()
            raise


def read_workspace_database_mount_data(session_dir: Path) -> dict[str, Any]:
    sqlite_data = _read_workspace_database_defaults_from_sqlite(session_dir)
    if sqlite_data is not None:
        return sqlite_data

    path = get_workspace_database_mount_path(session_dir)
    if not path.exists():
        return {"version": 1, "connector_ids": []}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "connector_ids": []}

    return normalize_workspace_database_mount_data(data)


def read_workspace_knowledge_base_mount_data(session_dir: Path) -> dict[str, Any]:
    """读取当前工作区可见的知识库集合。"""
    user_id, _workspace_id = _infer_workspace_identity(session_dir)
    knowledge_base_ids = _list_available_knowledge_base_ids(user_id) if user_id else []
    return {"version": 1, "knowledge_base_ids": knowledge_base_ids}


def write_workspace_database_mount_data(
    session_dir: Path,
    data: dict[str, Any],
) -> Path:
    ensure_workspace_layout(session_dir)
    path = get_workspace_database_mount_path(session_dir)
    normalized = normalize_workspace_database_mount_data(data)
    _write_workspace_database_defaults_to_sqlite(
        session_dir,
        list(normalized.get("connector_ids", [])),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def get_runtime_config_state_path(session_dir: Path) -> Path:
    return session_dir / RUNTIME_CONFIG_STATE_RELATIVE_PATH


def read_runtime_config_state(session_dir: Path) -> dict[str, Any]:
    path = get_runtime_config_state_path(session_dir)
    if not path.exists():
        return {
            "applied_agent_config_version": None,
            "applied_capability_snapshot_version": None,
            "applied_llm_config_signature": None,
            "applied_memory_snapshot_version": None,
            "applied_memory_snapshot_hash": None,
            "updated_at": None,
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "applied_agent_config_version": None,
            "applied_capability_snapshot_version": None,
            "applied_llm_config_signature": None,
            "applied_memory_snapshot_version": None,
            "applied_memory_snapshot_hash": None,
            "updated_at": None,
        }

    return {
        "applied_agent_config_version": data.get("applied_agent_config_version"),
        "applied_capability_snapshot_version": data.get("applied_capability_snapshot_version"),
        "applied_llm_config_signature": data.get("applied_llm_config_signature"),
        "applied_memory_snapshot_version": data.get("applied_memory_snapshot_version"),
        "applied_memory_snapshot_hash": data.get("applied_memory_snapshot_hash"),
        "updated_at": data.get("updated_at"),
    }


def write_runtime_config_state(
    session_dir: Path,
    *,
    applied_agent_config_version: str | None | object = _STATE_UNSET,
    applied_capability_snapshot_version: str | None | object = _STATE_UNSET,
    applied_llm_config_signature: str | None | object = _STATE_UNSET,
    applied_memory_snapshot_version: str | None | object = _STATE_UNSET,
    applied_memory_snapshot_hash: str | None | object = _STATE_UNSET,
) -> dict[str, Any]:
    ensure_workspace_layout(session_dir)
    state = read_runtime_config_state(session_dir)
    if applied_agent_config_version is not _STATE_UNSET:
        state["applied_agent_config_version"] = applied_agent_config_version
    if applied_capability_snapshot_version is not _STATE_UNSET:
        state["applied_capability_snapshot_version"] = applied_capability_snapshot_version
    if applied_llm_config_signature is not _STATE_UNSET:
        state["applied_llm_config_signature"] = applied_llm_config_signature
    if applied_memory_snapshot_version is not _STATE_UNSET:
        state["applied_memory_snapshot_version"] = applied_memory_snapshot_version
    if applied_memory_snapshot_hash is not _STATE_UNSET:
        state["applied_memory_snapshot_hash"] = applied_memory_snapshot_hash
    state["updated_at"] = datetime.now().isoformat()

    path = get_runtime_config_state_path(session_dir)
    path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return state


def _stable_hash(payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


async def compute_agent_config_version(
    *,
    user_id: str,
    session_id: str,
    sandbox_mode: str | None,
    session_dir: Path | None = None,
    execution_policy: Any = None,
) -> str:
    # 延迟导入，避免 `config_projection -> agent package init -> mixins/session|execution
    # -> config_projection` 的循环导入。
    from app.services.agent.config import resolve_agent_system_default_paths
    from app.services.agent.subagent_catalog import (
        compute_subagent_visibility_fingerprint,
    )
    from app.services.agent.system_presets import (
        compute_expert_catalog_fingerprint_from_preset,
        resolve_system_agent_preset_from_path,
    )
    from app.services.expert_roles import compute_expert_catalog_fingerprint

    metadata_payload: dict[str, Any] = {}
    if session_dir is not None:
        metadata_path = session_dir / "metadata.json"
        if metadata_path.exists():
            try:
                metadata_payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            except Exception:
                metadata_payload = {}

    effective_execution_policy = (
        execution_policy
        if execution_policy is not None
        else metadata_payload.get("execution_policy")
    )
    system_config_path, _ = resolve_agent_system_default_paths(
        sandbox_mode=sandbox_mode,
        execution_policy=effective_execution_policy,
    )
    preset = resolve_system_agent_preset_from_path(system_config_path)
    enabled_expert_role_ids = metadata_payload.get("enabled_expert_role_ids")
    expert_role_tool_ids = metadata_payload.get("expert_role_tool_ids")
    collaboration_policy = metadata_payload.get("collaboration_policy")
    workspace_id = metadata_payload.get("workspace_id")
    if not workspace_id:
        try:
            from app.services.workspace_registry import get_workspace_registry_service

            workspace_id = get_workspace_registry_service().find_workspace_id_by_session_id(
                user_id,
                session_id,
            )
        except Exception:
            workspace_id = None
    agent_mode = AgentMode.ANALYSIS
    merged = await get_agent_config_service().get_merged_config(
        mode=agent_mode,
        user_id=user_id,
        sandbox_mode=sandbox_mode,
        session_id=session_id,
        workspace_id=workspace_id,
        base_config_path=system_config_path,
    )
    tool_overrides = {
        name: override.model_dump() for name, override in merged.tool_overrides.items()
    }
    payload = {
        "mode": agent_mode.value,
        "prompt_source": merged.prompt_source,
        "system_prompt": merged.system_prompt,
        "enabled_tools": list(merged.enabled_tools),
        "disabled_tools": list(merged.disabled_tools),
        "tool_overrides": tool_overrides,
        "model": merged.model,
        "model_params": merged.model_params,
        "runtime_config": merged.runtime_config.model_dump(),
        "runtime_source": merged.runtime_source,
        "base_config_path": merged.base_config_path,
        "sandbox_mode": sandbox_mode,
        "session_id": session_id,
        "enabled_expert_role_ids": enabled_expert_role_ids,
        "expert_role_tool_ids": expert_role_tool_ids,
        "collaboration_policy": collaboration_policy,
        "expert_catalog_fingerprint": (
            compute_expert_catalog_fingerprint_from_preset(preset)
            if preset is not None
            else compute_expert_catalog_fingerprint(system_config_path)
        ),
        "subagent_visibility_fingerprint": compute_subagent_visibility_fingerprint(
            user_id=user_id,
            workspace_id=workspace_id,
        ),
    }
    return _stable_hash(payload)


def _infer_global_workspace_from_session(session_dir: Path) -> Path | None:
    """从会话目录推断对应的全局工作区路径。"""
    try:
        global_ws = session_dir.parent / "global_workspace"
        if global_ws.exists() and global_ws.is_dir():
            return global_ws
    except Exception:
        pass
    return None


def compute_capability_snapshot_version(session_dir: Path) -> str:
    ensure_workspace_layout(session_dir)
    mgr = get_skill_manager()
    workspace_skills = mgr.list_workspace_skills(session_dir)
    global_ws = _infer_global_workspace_from_session(session_dir)
    global_skills = mgr.list_workspace_skills(global_ws) if global_ws else []
    all_skills = {s.name: s for s in workspace_skills}
    all_skills.update({s.name: s for s in global_skills})
    from app.mcp import get_mcp_manager

    mcp_servers = get_mcp_manager().list_effective_servers(session_dir)
    user_id = _try_infer_user_id_from_path(session_dir)
    knowledge_base_ids = _list_available_knowledge_base_ids(user_id) if user_id else []
    knowledge_graph_ids = _list_available_knowledge_graph_ids(user_id) if user_id else []
    metadata_payload: dict[str, Any] = {}
    metadata_path = session_dir / "metadata.json"
    if metadata_path.exists():
        try:
            metadata_payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            metadata_payload = {}
    payload = {
        "skills": [
            {
                "name": skill.name,
                "entry_relative_path": skill.entry_relative_path,
            }
            for skill in all_skills.values()
        ],
        "mcp": {
            "version": 1,
            "servers": {s.name: {"enabled": True, "type": s.type} for s in mcp_servers},
        },
        "knowledge_bases": knowledge_base_ids,
        "knowledge_graphs": knowledge_graph_ids,
        "task_profile": build_task_profile_summary(
            execution_policy=metadata_payload.get("execution_policy"),
        ),
    }
    return _stable_hash(payload)


def build_workspace_capability_summary(session_dir: Path) -> dict[str, Any]:
    ensure_workspace_layout(session_dir)
    mgr = get_skill_manager()
    workspace_skills = mgr.list_workspace_skills(session_dir)
    global_ws = _infer_global_workspace_from_session(session_dir)
    global_skills = mgr.list_workspace_skills(global_ws) if global_ws else []
    all_skills = {s.name: s for s in workspace_skills}
    all_skills.update({s.name: s for s in global_skills})
    from app.mcp import get_mcp_manager

    mcp_servers = get_mcp_manager().list_effective_servers(session_dir)
    user_id = _try_infer_user_id_from_path(session_dir)
    knowledge_base_ids = _list_available_knowledge_base_ids(user_id) if user_id else []
    knowledge_graph_ids = _list_available_knowledge_graph_ids(user_id) if user_id else []

    skill_names = sorted(
        {str(skill.name).strip() for skill in all_skills.values() if str(skill.name).strip()}
    )
    enabled_mcp_server_names = sorted(s.name for s in mcp_servers)
    metadata_payload: dict[str, Any] = {}
    metadata_path = session_dir / "metadata.json"
    if metadata_path.exists():
        try:
            metadata_payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            metadata_payload = {}
    task_profile_summary = build_task_profile_summary(
        execution_policy=metadata_payload.get("execution_policy"),
    )

    return {
        "skill_count": len(skill_names),
        "skill_names": skill_names,
        "mcp_server_count": len(mcp_servers),
        "enabled_mcp_server_count": len(enabled_mcp_server_names),
        "enabled_mcp_server_names": enabled_mcp_server_names,
        "mcp_config_version": 1,
        "mounted_knowledge_base_count": len(knowledge_base_ids),
        "mounted_knowledge_base_ids": knowledge_base_ids,
        "mounted_knowledge_graph_count": len(knowledge_graph_ids),
        "mounted_knowledge_graph_ids": knowledge_graph_ids,
        "primary_knowledge_graph_id": None,
        "execution_policy": task_profile_summary["execution_policy"],
    }


async def build_runtime_config_projection(
    *,
    session_dir: Path,
    user_id: str,
    session_id: str,
    sandbox_mode: str | None,
    runtime_busy: bool,
) -> dict[str, Any]:
    ensure_workspace_layout(session_dir)
    state = read_runtime_config_state(session_dir)
    current_agent_version = await compute_agent_config_version(
        user_id=user_id,
        session_id=session_id,
        sandbox_mode=sandbox_mode,
        session_dir=session_dir,
    )
    current_capability_version = compute_capability_snapshot_version(session_dir)
    memory_preview = resolve_session_memory_preview(
        session_dir=session_dir,
        user_id=user_id,
        session_id=session_id,
    )
    has_current_memory = bool(memory_preview.rendered_markdown.strip())
    current_memory_version = memory_preview.version if has_current_memory else None
    current_memory_hash = memory_preview.snapshot_hash if has_current_memory else None

    applied_agent_version = state.get("applied_agent_config_version")
    applied_capability_version = state.get("applied_capability_snapshot_version")
    applied_memory_version = state.get("applied_memory_snapshot_version")
    applied_memory_hash = state.get("applied_memory_snapshot_hash")

    pending_agent_version = (
        current_agent_version if current_agent_version != applied_agent_version else None
    )
    pending_capability_version = (
        current_capability_version
        if current_capability_version != applied_capability_version
        else None
    )
    pending_memory_version = (
        current_memory_version if current_memory_version != applied_memory_version else None
    )
    pending_memory_hash = (
        current_memory_hash if current_memory_hash != applied_memory_hash else None
    )
    rebuild_required_reasons: list[str] = []
    if pending_agent_version:
        rebuild_required_reasons.append("agent_config_updated")
    if pending_capability_version:
        rebuild_required_reasons.append("capabilities_updated")
    if pending_memory_version:
        rebuild_required_reasons.append("memory_snapshot_updated")

    capability_summary = build_workspace_capability_summary(session_dir)
    config_sync_state = "pending" if rebuild_required_reasons else "aligned"

    return {
        "can_edit_agent_config_now": not runtime_busy,
        "agent_config_effect": "next_run_only",
        "config_sync_state": config_sync_state,
        "rebuild_required": bool(rebuild_required_reasons),
        "rebuild_required_reasons": rebuild_required_reasons,
        "config_state_updated_at": state.get("updated_at"),
        "current_agent_config_version": current_agent_version,
        "applied_agent_config_version": applied_agent_version,
        "pending_agent_config_version": pending_agent_version,
        "current_capability_snapshot_version": current_capability_version,
        "applied_capability_snapshot_version": applied_capability_version,
        "pending_capability_snapshot_version": pending_capability_version,
        "current_memory_snapshot_version": current_memory_version,
        "current_memory_snapshot_hash": current_memory_hash,
        "applied_memory_snapshot_version": applied_memory_version,
        "applied_memory_snapshot_hash": applied_memory_hash,
        "pending_memory_snapshot_version": pending_memory_version,
        "pending_memory_snapshot_hash": pending_memory_hash,
        "memory_effect": "next_run_only",
        "memory_snapshot_preview": memory_preview.model_dump(mode="json"),
        "workspace_capability_summary": capability_summary,
    }


# ---------------------------------------------------------------------------
# 用户 UI 设置（JSON 文件存储，独立于 memory 系统）
# ---------------------------------------------------------------------------

UI_SETTINGS_CONFIG_RELATIVE_PATH = Path(".config") / "ui-settings.json"


def get_user_ui_settings_path(user_id: str) -> Path:
    """返回用户 UI 设置文件的绝对路径。"""
    return get_user_global_config_dir(user_id) / "ui-settings.json"


def read_user_ui_settings(user_id: str) -> dict[str, Any]:
    """读取用户 UI 设置；文件不存在或解析失败时返回空字典。"""
    path = get_user_ui_settings_path(user_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def write_user_ui_settings(user_id: str, data: dict[str, Any]) -> Path:
    """写入用户 UI 设置；自动创建父目录。"""
    path = get_user_ui_settings_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path
