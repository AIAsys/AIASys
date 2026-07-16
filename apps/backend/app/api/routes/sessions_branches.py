import json
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.core.auth import require_auth, require_role
from app.core.config import WORKSPACE_DIR, validate_code_timeout
from app.models.llm_selection import (
    SessionLLMSelectionResponse,
    UpdateScopedModelSelectionRequest,
)
from app.models.session import (
    SessionReferenceItem,
    SessionReferenceResolveRequest,
    SessionReferenceResolveResponse,
    SessionReferenceSearchResponse,
    SessionSettingsSummaryResponse,
)
from app.models.user import UserInfo
from app.services.agent import agent_service
from app.services.expert_roles import get_session_expert_policy
from app.services.llm.model_selection_service import get_model_selection_service
from app.services.runtime.session_runtime_state import build_session_runtime_summary
from app.services.session import SessionManager
from app.services.session.config_projection import (
    build_runtime_config_projection,
    ensure_workspace_layout,
)
from app.services.workspace_registry import get_workspace_registry_service
from app.utils.path_utils import as_system_path

from .sessions_helpers import (
    _build_session_status_payload,
    _count_visible_workspace_files,
    _resolve_user_id,
)
from .sessions_models import (
    CreateSessionRequest,
    SessionResponse,
    UpdateTaskProfileRequest,
    UpdateTitleRequest,
)

logger = logging.getLogger(__name__)
session_manager = SessionManager(WORKSPACE_DIR)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _is_runtime_busy(user_id: str, session_id: str) -> bool:
    session_key = f"{user_id}/{session_id}"
    session_lock = getattr(agent_service, "_session_locks", {}).get(session_key)
    return bool(session_lock and session_lock.locked())


def _get_session_owner_from_metadata(
    session_manager,
    session_id: str,
    user_id: str,
) -> Optional[str]:
    try:
        metadata = session_manager.get_session(session_id, user_id)
        if metadata and hasattr(metadata, "user_id") and metadata.user_id:
            return metadata.user_id
    except Exception as exc:
        logger.warning("获取会话 owner 失败: %s/%s: %s", user_id, session_id, exc)
    return None


def _build_collaboration_node_summary(user_id: str, session_id: str) -> dict:
    try:
        from app.services.tracking import get_subagent_tracking_service

        tree = get_subagent_tracking_service().get_execution_tree(
            user_id=user_id,
            session_id=session_id,
            host_events=None,
        )
    except Exception as exc:
        logger.warning("读取协作节点摘要失败: %s", exc)
        return {
            "total_count": 0,
            "running_count": 0,
            "completed_count": 0,
            "abnormal_count": 0,
            "latest_updated_at": None,
        }

    total_count = len(tree.subagent_calls)
    running_count = 0
    completed_count = 0
    abnormal_count = 0
    latest_updated_at: str | None = None

    for call in tree.subagent_calls:
        subagent = call.get("subagent") if isinstance(call, dict) else None
        if not isinstance(subagent, dict):
            continue
        status = str(subagent.get("status") or "").strip().lower()
        if status in {"running", "queued"}:
            running_count += 1
        elif status == "completed":
            completed_count += 1
        elif status in {"failed", "cancelled"}:
            abnormal_count += 1
        updated_at = subagent.get("updated_at")
        if isinstance(updated_at, str) and (
            latest_updated_at is None or updated_at > latest_updated_at
        ):
            latest_updated_at = updated_at

    return {
        "total_count": total_count,
        "running_count": running_count,
        "completed_count": completed_count,
        "abnormal_count": abnormal_count,
        "latest_updated_at": latest_updated_at,
    }


def _find_available_draft_for_user(
    current_user: UserInfo,
    workspace_id: Optional[str] = None,
):
    user_dir = session_manager.base_dir / current_user.user_id
    if not user_dir.exists():
        return {"available": False, "reason": "no_user_dir"}

    draft_sessions = []
    now = datetime.now()
    threshold = timedelta(minutes=30)
    registry = get_workspace_registry_service()

    for session_dir in user_dir.iterdir():
        if not session_dir.is_dir():
            continue

        meta_path = session_dir / "metadata.json"
        if not meta_path.exists():
            continue

        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            created_at_str = data.get("created_at", "")

            if not session_manager.is_blank_draft_session(
                session_dir.name,
                current_user.user_id,
            ):
                continue

            # 如果指定了工作区，只返回属于该工作区的草稿，避免跨工作区复用导致 400
            if workspace_id is not None:
                session_workspace_id = registry.find_workspace_id_by_session_id(
                    current_user.user_id,
                    session_dir.name,
                )
                if session_workspace_id != workspace_id:
                    continue

            created_at = datetime.fromisoformat(created_at_str)
            age = now - created_at
            if age > threshold:
                continue

            draft_sessions.append(
                {
                    "session_id": session_dir.name,
                    "created_at": created_at,
                    "age_seconds": age.total_seconds(),
                }
            )
        except Exception as e:
            logger.warning(f"读取会话元数据失败: {e}")
            continue

    if not draft_sessions:
        return {"available": False, "reason": "no_draft"}

    draft_sessions.sort(key=lambda x: x["created_at"], reverse=True)
    best_draft = draft_sessions[0]

    logger.info(
        f"可用草稿: {current_user.user_id}/{best_draft['session_id']} (age={best_draft['age_seconds']:.0f}s)"
    )

    return {
        "available": True,
        "session_id": best_draft["session_id"],
        "created_at": best_draft["created_at"].isoformat(),
        "age_seconds": best_draft["age_seconds"],
    }


@router.post("/create", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest, user: UserInfo = Depends(require_auth())):
    """
    创建新会话

    user_id 可从认证信息自动获取
    """
    user_id = _resolve_user_id(request.user_id, user)

    try:
        env_id = None
        sandbox_mode = None

        # 若指定了已有工作区，继承其 runtime_binding
        if request.workspace_id:
            try:
                workspace = get_workspace_registry_service().get_workspace(
                    user_id, request.workspace_id, include_conversations=False
                )
                if workspace.runtime_binding:
                    env_id = workspace.runtime_binding.env_id
                    sandbox_mode = workspace.runtime_binding.sandbox_mode
            except FileNotFoundError as exc:
                logger.warning(f"创建会话时指定的工作区不存在: {request.workspace_id}")
                raise HTTPException(status_code=404, detail="Workspace not found") from exc
            except Exception as exc:
                logger.warning(f"读取工作区 runtime_binding 失败: {exc}")
                raise HTTPException(
                    status_code=500, detail="Failed to resolve workspace runtime binding"
                ) from exc

        validated_code_timeout = (
            validate_code_timeout(request.code_timeout, sandbox_mode or "local")
            if request.code_timeout is not None
            else None
        )

        agent_type = "analysis"

        # 创建会话，固定绑定到当前主线的本地执行运行态
        # 前端主动新建会话时传入 status="active"，避免被列表 API 过滤为空白草稿
        metadata = session_manager.create_session(
            session_id=request.session_id,
            user_id=user_id,
            title=request.title,
            status=request.status or "draft",
            env_id=env_id,
            sandbox_mode=sandbox_mode,
            recovery_policy=request.recovery_policy or "journal_only",
            code_timeout=validated_code_timeout,
            agent_type=agent_type,
            execution_policy=request.execution_policy,
        )

        # 绑定工作区：若提供了 workspace_id 则绑定到指定工作区，
        # 否则自动创建一个同名工作区并绑定，确保 RuntimeEnvironment 等工具正常工作
        try:
            registry = get_workspace_registry_service()
            workspace_id = request.workspace_id
            if workspace_id:
                # 验证工作区存在
                registry.get_workspace(user_id, workspace_id, include_conversations=False)
            else:
                # 自动创建同名工作区
                workspace_id = request.session_id
                try:
                    registry.get_workspace(user_id, workspace_id, include_conversations=False)
                except FileNotFoundError:
                    registry.create_workspace(
                        user_id=user_id,
                        title=request.title or "新会话",
                        workspace_id=workspace_id,
                        workspace_kind="task",
                        env_id="workspace-default",
                        sandbox_mode="local",
                    )
            # 写入 session -> workspace 反向索引
            registry._write_session_index(user_id, request.session_id, workspace_id)
            # 将 session 作为对话加入工作区
            registry.add_conversation_to_workspace(
                user_id=user_id,
                workspace_id=workspace_id,
                conversation_id=request.session_id,
                conversation_title=request.title or "新会话",
                make_current=True,
            )
        except Exception as e:
            logger.warning(f"会话工作区绑定失败（不影响会话创建）: {e}")

        return SessionResponse(
            session_id=metadata.session_id,
            title=metadata.title,
            created_at=metadata.created_at,
            message_count=metadata.message_count,
            code_timeout=metadata.code_timeout,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"创建会话失败: {e}")
        raise HTTPException(status_code=500, detail="Failed to create session") from e


@router.get("/status/{session_id}")
async def get_session_status(
    session_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """获取会话状态（用于 MCP 配置锁定检查）

    返回会话的消息数量，用于前端判断是否可以编辑 MCP 配置：
    - message_count = 0: 空会话，可自由编辑 MCP
    - message_count > 0: 进行中会话，MCP 配置锁定

    如果会话不存在，自动创建草稿文件夹（幂等操作）
    """
    try:
        metadata = session_manager.get_session(session_id, current_user.user_id)

        # 如果会话不存在，自动创建草稿
        if not metadata:
            metadata = session_manager.create_session(
                session_id=session_id,
                user_id=current_user.user_id,
                title="新会话",
                env_id=None,
                sandbox_mode=None,
            )

            session_dir = session_manager._get_session_dir(
                session_id,
                current_user.user_id,
            )
            ensure_workspace_layout(session_dir)
            logger.info(f"[AutoCreate] 自动创建草稿: {current_user.user_id}/{session_id}")

        session_dir = session_manager._get_session_dir(
            session_id,
            current_user.user_id,
        )
        ensure_workspace_layout(session_dir)
        execution_summary = session_manager.get_execution_summary(
            session_id,
            current_user.user_id,
        )
        payload = _build_session_status_payload(metadata, execution_summary)
        payload["collaboration_node_summary"] = _build_collaboration_node_summary(
            current_user.user_id,
            session_id,
        )
        payload["can_edit_task_profile_now"] = not _is_runtime_busy(
            current_user.user_id,
            session_id,
        )
        payload["runtime_summary"] = build_session_runtime_summary(
            session_dir=session_dir,
            session_id=session_id,
            user_id=current_user.user_id,
            sandbox_mode=metadata.sandbox_mode,
            env_id=metadata.env_id,
            last_runtime_state=payload.get("last_runtime_state"),
            runtime_busy=_is_runtime_busy(current_user.user_id, session_id),
        )
        payload.update(
            await build_runtime_config_projection(
                session_dir=session_dir,
                user_id=current_user.user_id,
                session_id=session_id,
                sandbox_mode=metadata.sandbox_mode,
                runtime_busy=_is_runtime_busy(current_user.user_id, session_id),
            )
        )
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话状态失败: {e}")
        raise HTTPException(status_code=500, detail="Failed to get session status") from e


@router.get("/workspace-summary/{session_id}")
async def get_session_workspace_summary(
    session_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """获取当前任务工作区摘要。"""
    try:
        metadata = session_manager.get_session(session_id, current_user.user_id)
        if not metadata:
            metadata = session_manager.create_session(
                session_id=session_id,
                user_id=current_user.user_id,
                title="新会话",
                env_id=None,
                sandbox_mode=None,
            )

        session_dir = session_manager._get_session_dir(session_id, current_user.user_id)
        ensure_workspace_layout(session_dir)
        workspace_id = get_workspace_registry_service().find_workspace_id_by_session_id(
            current_user.user_id,
            session_id,
        )
        workspace_summary = None
        if workspace_id:
            try:
                workspace_summary = get_workspace_registry_service().get_workspace(
                    current_user.user_id,
                    workspace_id,
                    include_conversations=False,
                )
            except FileNotFoundError:
                workspace_summary = None

        execution_summary = session_manager.get_execution_summary(
            session_id,
            current_user.user_id,
        )
        config_projection = await build_runtime_config_projection(
            session_dir=session_dir,
            user_id=current_user.user_id,
            session_id=session_id,
            sandbox_mode=metadata.sandbox_mode,
            runtime_busy=_is_runtime_busy(current_user.user_id, session_id),
        )

        return {
            "workspace_id": workspace_id,
            "workspace_id_source": ("workspace_registry" if workspace_id else "unbound_session"),
            "workspace_title": (workspace_summary.title if workspace_summary is not None else None),
            "workspace_current_conversation_id": (
                workspace_summary.current_conversation_id if workspace_summary is not None else None
            ),
            "session_id": metadata.session_id,
            "title": metadata.title,
            "execution_policy": (
                metadata.execution_policy.model_dump(mode="json")
                if getattr(metadata, "execution_policy", None) is not None
                else None
            ),
            "status": metadata.status,
            "created_at": metadata.created_at,
            "updated_at": metadata.updated_at,
            "is_empty": metadata.message_count == 0,
            "message_count": metadata.message_count,
            "workspace_file_count": _count_visible_workspace_files(session_dir),
            "has_execution_journal": bool(execution_summary.get("has_execution_journal", False)),
            "execution_record_count": int(execution_summary.get("execution_record_count") or 0),
            "last_execution_status": execution_summary.get("last_execution_status"),
            "last_execution_record_id": execution_summary.get("last_execution_record_id"),
            "runtime": {
                "env_id": metadata.env_id,
                "sandbox_mode": metadata.sandbox_mode,
                "last_runtime_state": execution_summary.get("last_runtime_state"),
                "runtime_summary": build_session_runtime_summary(
                    session_dir=session_dir,
                    session_id=session_id,
                    user_id=current_user.user_id,
                    sandbox_mode=metadata.sandbox_mode,
                    env_id=metadata.env_id,
                    last_runtime_state=execution_summary.get("last_runtime_state"),
                    runtime_busy=_is_runtime_busy(current_user.user_id, session_id),
                ),
            },
            "recovery_policy": metadata.recovery_policy,
            "code_timeout": metadata.code_timeout,
            **config_projection,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取工作区摘要失败: {e}")
        raise HTTPException(status_code=500, detail="Failed to get workspace summary") from e


def _resolve_actual_session_user(
    *,
    requested_user_id: str,
    session_id: str,
    current_user: UserInfo,
) -> str:
    actual_user_id = _get_session_owner_from_metadata(
        session_manager,
        session_id,
        requested_user_id,
    )
    if not actual_user_id:
        actual_user_id = requested_user_id
    if not current_user.can_access_user_data(actual_user_id):
        raise HTTPException(status_code=403, detail="You can only access your own session data")
    return actual_user_id


def _normalize_session_reference_ids(value) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


_WORKSPACE_REFERENCE_INTERNAL_DIRS = {
    ".aiasys",
    ".env",
    "env",
}
_WORKSPACE_REFERENCE_INTERNAL_FILES = {
    ".cleanup_marker",
    "file_snapshots.json",
    "history.json",
    "metadata.json",
}


def _iter_workspace_visible_files(workspace_root: Path, *, limit: int = 50) -> list[Path]:
    if not workspace_root.exists():
        return []
    visible_files: list[Path] = []
    for file_path in sorted(workspace_root.rglob("*")):
        if not file_path.is_file():
            continue
        try:
            relative_parts = file_path.relative_to(workspace_root).parts
        except ValueError:
            continue
        if not relative_parts:
            continue
        if relative_parts[0] in _WORKSPACE_REFERENCE_INTERNAL_DIRS:
            continue
        if len(relative_parts) == 1 and relative_parts[0] in _WORKSPACE_REFERENCE_INTERNAL_FILES:
            continue
        visible_files.append(file_path)
        if len(visible_files) >= limit:
            break
    return visible_files


def _matches_reference_query(item: SessionReferenceItem, query: str) -> bool:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return True
    haystack = " ".join(
        [
            item.reference_id,
            item.display_name,
            item.description or "",
            item.reference_kind,
        ]
    ).lower()
    return normalized_query in haystack


async def _build_session_reference_items(
    *,
    user_id: str,
    session_id: str,
) -> tuple[str | None, list[SessionReferenceItem]]:
    from app.services.connector import DatabaseConnectorService
    from app.services.session.config_projection import (
        read_workspace_database_mount_data,
        read_workspace_knowledge_base_mount_data,
    )

    service = get_workspace_registry_service()
    workspace_id = service.find_workspace_id_by_session_id(user_id, session_id)
    workspace_root = service.get_logical_workspace_root(user_id, session_id)
    items: list[SessionReferenceItem] = []

    for file_path in _iter_workspace_visible_files(workspace_root, limit=100):
        relative_path = file_path.relative_to(workspace_root).as_posix()
        items.append(
            SessionReferenceItem(
                reference_id=f"file:{relative_path}",
                reference_kind="file",
                display_name=file_path.name,
                description=relative_path,
                scope="workspace",
                metadata={"relative_path": relative_path},
            )
        )

    if workspace_id:
        database_mounts = read_workspace_database_mount_data(workspace_root)
        knowledge_base_mounts = read_workspace_knowledge_base_mount_data(workspace_root)
        for connector_id in _normalize_session_reference_ids(database_mounts.get("connector_ids")):
            items.append(
                SessionReferenceItem(
                    reference_id=f"database_connector:{connector_id}",
                    reference_kind="database_connector",
                    display_name=connector_id,
                    scope="workspace",
                    metadata={"connector_id": connector_id},
                )
            )
        for knowledge_base_id in _normalize_session_reference_ids(
            knowledge_base_mounts.get("knowledge_base_ids")
        ):
            items.append(
                SessionReferenceItem(
                    reference_id=f"knowledge_base:{knowledge_base_id}",
                    reference_kind="knowledge_base",
                    display_name=knowledge_base_id,
                    scope="workspace",
                    metadata={"knowledge_base_id": knowledge_base_id},
                )
            )
    try:
        for attachment in DatabaseConnectorService(
            get_workspace_registry_service().base_dir,
            session_manager=session_manager,
        ).list_session_attachments(user_id, session_id):
            handle = str(getattr(attachment, "handle", "") or "").strip()
            if not handle:
                continue
            items.append(
                SessionReferenceItem(
                    reference_id=f"database_handle:{handle}",
                    reference_kind="database_handle",
                    display_name=handle,
                    description=getattr(attachment, "name", None),
                    scope="runtime",
                    metadata={
                        "connector_id": getattr(attachment, "connector_id", None),
                        "handle": handle,
                    },
                )
            )
    except Exception as exc:
        logger.warning("读取数据库引用失败: session=%s error=%s", session_id, exc)

    try:
        expert_policy = get_session_expert_policy(user_id=user_id, session_id=session_id)
        for role in expert_policy.available_roles:
            items.append(
                SessionReferenceItem(
                    reference_id=f"expert:{role.role_id}",
                    reference_kind="expert",
                    display_name=role.display_name,
                    description=role.description,
                    scope="session",
                    metadata=role.model_dump(mode="json"),
                )
            )
    except Exception as exc:
        logger.warning("读取专家引用失败: session=%s error=%s", session_id, exc)

    try:
        from app.services.agent_config import AgentMode, get_agent_config_service

        merged = await get_agent_config_service().get_merged_config(
            mode=AgentMode.ANALYSIS,
            user_id=user_id,
            session_id=session_id,
            workspace_id=workspace_id,
        )
        for tool_name in merged.enabled_tools:
            items.append(
                SessionReferenceItem(
                    reference_id=f"tool:{tool_name}",
                    reference_kind="tool",
                    display_name=tool_name.split(":")[-1],
                    description=tool_name,
                    scope="session",
                    metadata={"tool_name": tool_name},
                )
            )
    except Exception as exc:
        logger.warning("读取当前工具引用失败: session=%s error=%s", session_id, exc)

    deduped: dict[str, SessionReferenceItem] = {}
    for item in items:
        deduped.setdefault(item.reference_id, item)
    return workspace_id, list(deduped.values())


@router.get(
    "/{user_id}/{session_id}/settings-summary",
    response_model=SessionSettingsSummaryResponse,
)
async def get_session_settings_summary(
    user_id: str,
    session_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    actual_user_id = _resolve_actual_session_user(
        requested_user_id=user_id,
        session_id=session_id,
        current_user=current_user,
    )
    metadata = session_manager.get_session(session_id, actual_user_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="会话不存在")

    service = get_workspace_registry_service()
    workspace_id = service.find_workspace_id_by_session_id(actual_user_id, session_id)
    session_dir = session_manager._get_session_dir(session_id, actual_user_id)
    execution_summary = session_manager.get_execution_summary(session_id, actual_user_id)
    runtime_busy = _is_runtime_busy(actual_user_id, session_id)
    runtime_summary = build_session_runtime_summary(
        session_dir=session_dir,
        session_id=session_id,
        user_id=actual_user_id,
        sandbox_mode=metadata.sandbox_mode,
        env_id=metadata.env_id,
        last_runtime_state=execution_summary.get("last_runtime_state"),
        runtime_busy=runtime_busy,
    )
    config_projection = await build_runtime_config_projection(
        session_dir=session_dir,
        user_id=actual_user_id,
        session_id=session_id,
        sandbox_mode=metadata.sandbox_mode,
        runtime_busy=runtime_busy,
    )
    model_selection = get_model_selection_service().get_session_selection(
        user_id=actual_user_id,
        session_id=session_id,
    )
    expert_policy = get_session_expert_policy(
        user_id=actual_user_id,
        session_id=session_id,
    )

    return SessionSettingsSummaryResponse(
        user_id=actual_user_id,
        session_id=session_id,
        workspace_id=workspace_id,
        generated_at=datetime.now().isoformat(),
        agent_config={
            "effect": config_projection.get("agent_config_effect"),
            "can_edit_now": config_projection.get("can_edit_agent_config_now"),
            "current_version": config_projection.get("current_agent_config_version"),
            "applied_version": config_projection.get("applied_agent_config_version"),
            "pending_version": config_projection.get("pending_agent_config_version"),
            "config_sync_state": config_projection.get("config_sync_state"),
            "rebuild_required": config_projection.get("rebuild_required"),
            "rebuild_required_reasons": config_projection.get("rebuild_required_reasons"),
        },
        model_selection=model_selection.model_dump(mode="json"),
        expert_policy=expert_policy.model_dump(mode="json"),
        memory={
            "effect": config_projection.get("memory_effect"),
            "current_version": config_projection.get("current_memory_snapshot_version"),
            "pending_version": config_projection.get("pending_memory_snapshot_version"),
            "preview": config_projection.get("memory_snapshot_preview"),
        },
        capabilities={
            "current_version": config_projection.get("current_capability_snapshot_version"),
            "applied_version": config_projection.get("applied_capability_snapshot_version"),
            "pending_version": config_projection.get("pending_capability_snapshot_version"),
            "summary": config_projection.get("workspace_capability_summary"),
        },
        runtime=runtime_summary,
        execution=execution_summary,
    )


@router.get(
    "/{user_id}/{session_id}/references/search",
    response_model=SessionReferenceSearchResponse,
)
async def search_session_references(
    user_id: str,
    session_id: str,
    query: str = Query("", alias="q"),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserInfo = Depends(require_auth()),
):
    query_text = query if isinstance(query, str) else ""
    limit_value = limit if isinstance(limit, int) else 50
    actual_user_id = _resolve_actual_session_user(
        requested_user_id=user_id,
        session_id=session_id,
        current_user=current_user,
    )
    if not session_manager.get_session(session_id, actual_user_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    workspace_id, items = await _build_session_reference_items(
        user_id=actual_user_id,
        session_id=session_id,
    )
    matched = [item for item in items if _matches_reference_query(item, query_text)]
    return SessionReferenceSearchResponse(
        user_id=actual_user_id,
        session_id=session_id,
        workspace_id=workspace_id,
        query=query_text,
        items=matched[:limit_value],
        total=len(matched),
    )


@router.post(
    "/{user_id}/{session_id}/references/resolve",
    response_model=SessionReferenceResolveResponse,
)
async def resolve_session_references(
    user_id: str,
    session_id: str,
    request: SessionReferenceResolveRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    from app.services.task_resource_context import build_task_resource_context

    actual_user_id = _resolve_actual_session_user(
        requested_user_id=user_id,
        session_id=session_id,
        current_user=current_user,
    )
    if not session_manager.get_session(session_id, actual_user_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    workspace_id, items = await _build_session_reference_items(
        user_id=actual_user_id,
        session_id=session_id,
    )
    by_id = {item.reference_id: item for item in items}
    normalized_ids = _normalize_session_reference_ids(request.reference_ids)
    resolved = [by_id[item_id] for item_id in normalized_ids if item_id in by_id]
    unresolved = [item_id for item_id in normalized_ids if item_id not in by_id]
    workspace_root = get_workspace_registry_service().get_logical_workspace_root(
        actual_user_id,
        session_id,
    )
    attached_files = [
        item.metadata.get("relative_path")
        for item in resolved
        if item.reference_kind == "file" and item.metadata.get("relative_path")
    ]
    return SessionReferenceResolveResponse(
        user_id=actual_user_id,
        session_id=session_id,
        workspace_id=workspace_id,
        resolved=resolved,
        unresolved_reference_ids=unresolved,
        task_resource_context=build_task_resource_context(
            user_id=actual_user_id,
            session_id=session_id,
            workspace_dir=workspace_root,
            attached_files=attached_files,
        ),
    )


@router.get("/{user_id}/{session_id}", response_model=SessionResponse)
async def get_session(
    user_id: str,
    session_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """获取会话信息"""
    # 检查是否有权访问该用户的数据
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(status_code=403, detail="You can only access your own sessions")

    try:
        metadata = session_manager.get_session(session_id, user_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="会话不存在")
        return SessionResponse(
            session_id=metadata.session_id,
            title=metadata.title,
            created_at=metadata.created_at,
            message_count=metadata.message_count,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed") from e


@router.get("/{user_id}/{session_id}/metadata")
async def get_session_metadata(
    user_id: str,
    session_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """获取会话完整元数据

    返回 session 的详细信息，用于前端"查看元数据"功能。
    """
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(status_code=403, detail="You can only access your own sessions")

    try:
        metadata = session_manager.get_session(session_id, user_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="会话不存在")

        execution_summary = session_manager.get_execution_summary(session_id, user_id)

        return {
            "session_id": metadata.session_id,
            "title": metadata.title,
            "status": metadata.status,
            "message_count": metadata.message_count,
            "created_at": metadata.created_at,
            "updated_at": metadata.updated_at,
            "is_empty": metadata.message_count == 0,
            "has_execution_journal": bool(execution_summary.get("has_execution_journal", False)),
            "execution_record_count": int(execution_summary.get("execution_record_count") or 0),
            "sandbox_mode": metadata.sandbox_mode,
            "env_id": metadata.env_id,
            "enabled_expert_role_ids": getattr(metadata, "enabled_expert_role_ids", None),
            "expert_role_tool_ids": getattr(metadata, "expert_role_tool_ids", None),
            "collaboration_policy": (
                metadata.collaboration_policy.model_dump(mode="json")
                if getattr(metadata, "collaboration_policy", None) is not None
                else None
            ),
            "execution_policy": (
                metadata.execution_policy.model_dump(mode="json")
                if getattr(metadata, "execution_policy", None) is not None
                else None
            ),
            "recovery_policy": metadata.recovery_policy,
            "code_timeout": metadata.code_timeout,
            "last_execution_status": execution_summary.get("last_execution_status"),
            "last_execution_record_id": execution_summary.get("last_execution_record_id"),
            "completed_at": metadata.completed_at,
            "completed_message_count": metadata.completed_message_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话元数据失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed") from e


@router.get(
    "/{user_id}/{session_id}/llm-selection",
    response_model=SessionLLMSelectionResponse,
)
async def get_session_llm_selection(
    user_id: str,
    session_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    actual_user_id = _get_session_owner_from_metadata(session_manager, session_id, user_id)
    if not actual_user_id:
        actual_user_id = user_id

    if not current_user.can_access_user_data(actual_user_id):
        raise HTTPException(
            status_code=403, detail="You can only access your own session LLM settings"
        )

    metadata = session_manager.get_session(session_id, actual_user_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="会话不存在")

    return get_model_selection_service().get_session_selection(
        user_id=actual_user_id,
        session_id=session_id,
    )


@router.put(
    "/{user_id}/{session_id}/llm-selection",
    response_model=SessionLLMSelectionResponse,
)
async def update_session_llm_selection(
    user_id: str,
    session_id: str,
    request: UpdateScopedModelSelectionRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    actual_user_id = _get_session_owner_from_metadata(session_manager, session_id, user_id)
    if not actual_user_id:
        actual_user_id = user_id

    if not current_user.can_access_user_data(actual_user_id):
        raise HTTPException(
            status_code=403, detail="You can only update your own session LLM settings"
        )

    try:
        return get_model_selection_service().update_session_model_selection(
            user_id=actual_user_id,
            session_id=session_id,
            model_id=request.model_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{user_id}/{session_id}/title")
async def update_session_title_endpoint(
    user_id: str,
    session_id: str,
    request: UpdateTitleRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """更新会话标题"""
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(status_code=403, detail="You can only update your own session titles")

    try:
        ok = session_manager.update_session_title(
            session_id=session_id,
            user_id=user_id,
            title=request.title,
        )
        if not ok:
            raise HTTPException(status_code=500, detail="更新标题失败")
        return {"success": True, "title": request.title}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新会话标题失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed") from e


@router.post("/{user_id}/{session_id}/task-profile")
async def update_session_task_profile(
    user_id: str,
    session_id: str,
    request: UpdateTaskProfileRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """更新当前会话的任务工作层配置。"""
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(
            status_code=403, detail="You can only update your own session task profile"
        )

    try:
        metadata = session_manager.get_session(session_id, user_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="会话不存在")
        if _is_runtime_busy(user_id, session_id):
            raise HTTPException(
                status_code=409,
                detail="当前会话正在执行，不能并发改写任务配置，请等待本轮完成。",
            )

        updated = session_manager.update_task_profile(
            session_id=session_id,
            user_id=user_id,
            execution_policy=request.execution_policy,
        )
        if updated is None:
            raise HTTPException(status_code=500, detail="更新任务配置失败")

        from app.services.workspace_registry import get_workspace_registry_service

        get_workspace_registry_service().sync_conversation_task_profile(
            user_id=user_id,
            session_id=session_id,
        )

        return {
            "success": True,
            "execution_policy": updated.execution_policy.model_dump(mode="json"),
            "task_profile_effect": "next_run_only",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新会话任务配置失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed") from e


@router.get("/available-draft")
async def get_available_draft(
    workspace_id: Optional[str] = Query(None, description="限制返回指定工作区的草稿"),
    current_user: UserInfo = Depends(require_auth()),
):
    """
    获取一个可用的预热草稿会话

    传入 workspace_id 时，只返回属于该工作区的草稿，避免跨工作区复用导致 workspace binding 失败。
    """
    try:
        return _find_available_draft_for_user(current_user, workspace_id=workspace_id)
    except Exception as e:
        logger.error(f"获取可用草稿失败: {e}")
        return {"available": False, "reason": "error", "error": str(e)}


@router.get("/{user_id}")
async def list_sessions(user_id: str, current_user: UserInfo = Depends(require_auth())):
    """列出用户的所有会话"""
    # 检查是否有权访问该用户的数据
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(status_code=403, detail="You can only list your own sessions")

    try:
        sessions = session_manager.list_user_sessions(user_id)
        return {"sessions": sessions}
    except Exception as e:
        logger.error(f"列会话失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed") from e


@router.get("/", tags=["admin"])
async def list_all_sessions(
    current_user: UserInfo = Depends(require_role("admin")),
):
    """
    列出所有用户的所有会话（仅管理员）
    """
    try:
        # 遍历所有用户目录
        all_sessions = []
        workspaces_path = WORKSPACE_DIR

        if workspaces_path.exists():
            for user_dir in workspaces_path.iterdir():
                if user_dir.name.startswith(".") or not user_dir.is_dir():
                    continue
                sessions = session_manager.list_user_sessions(user_dir.name, include_drafts=True)
                all_sessions.extend(sessions)

        # 按创建时间排序
        all_sessions.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        return {
            "sessions": all_sessions,
            "total": len(all_sessions),
            "admin": current_user.user_id,
        }
    except Exception as e:
        logger.error(f"列所有会话失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed") from e


@router.post("/cleanup-drafts")
async def cleanup_draft_sessions(
    request: Optional[dict] = None,
    current_user: UserInfo = Depends(require_auth()),
):
    """
    清理过期的草稿会话

    删除条件：
    - 状态为draft（message_count == 0）
    - 创建时间超过30分钟
    - 不是当前正在访问的会话（如前端传入 current_session_id）
    - 不是最近访问的3个会话之一（按创建时间保留最新的3个）
    """
    try:
        user_dir = session_manager.base_dir / current_user.user_id
        if not user_dir.exists():
            return {"cleaned": [], "total": 0}

        current_session_id = None
        if request:
            current_session_id = request.get("current_session_id") or request.get(
                "currentSessionId"
            )

        draft_sessions = []
        now = datetime.now()

        # 收集所有草稿会话
        for session_dir in user_dir.iterdir():
            if not session_dir.is_dir():
                continue
            if current_session_id and session_dir.name == current_session_id:
                continue

            meta_path = session_dir / "metadata.json"
            if not meta_path.exists():
                continue

            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                created_at = datetime.fromisoformat(data.get("created_at", "0"))

                # 只收集真正的空白草稿。
                if session_manager.is_blank_draft_session(
                    session_dir.name,
                    current_user.user_id,
                ):
                    draft_sessions.append(
                        {
                            "session_id": session_dir.name,
                            "created_at": created_at,
                            "dir": session_dir,
                        }
                    )
            except Exception as e:
                logger.warning(f"读取会话元数据失败: {e}")
                continue

        # 按创建时间排序（最早的在前）
        draft_sessions.sort(key=lambda x: x["created_at"])

        # 保留最新的3个草稿
        to_keep = draft_sessions[-3:] if len(draft_sessions) > 3 else draft_sessions
        to_keep_ids = {s["session_id"] for s in to_keep}

        # 清理过期草稿（超过30分钟且不在保留列表中）
        # 被标记的草稿使用更短的过期时间（5分钟）
        cleaned = []
        THRESHOLD = timedelta(minutes=30)
        MARKED_THRESHOLD = timedelta(minutes=5)

        for draft in draft_sessions:
            # 跳过保留的
            if draft["session_id"] in to_keep_ids:
                continue

            # 检查是否有清理标记
            marker_path = draft["dir"] / ".cleanup_marker"
            is_marked = marker_path.exists()

            # 被标记的草稿使用更短的过期时间
            effective_threshold = MARKED_THRESHOLD if is_marked else THRESHOLD

            # 检查是否过期
            age = now - draft["created_at"]
            if age > effective_threshold:
                try:
                    shutil.rmtree(as_system_path(draft["dir"]))
                    cleaned.append(draft["session_id"])
                    logger.info(
                        f"清理草稿: {current_user.user_id}/{draft['session_id']} (marked={is_marked})"
                    )
                except Exception as e:
                    logger.warning(f"删除草稿失败: {e}")

        return {
            "cleaned": cleaned,
            "total": len(cleaned),
            "drafts_total": len(draft_sessions),
            "drafts_kept": len(to_keep),
        }
    except Exception as e:
        logger.error(f"清理草稿失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed") from e


@router.post("/mark-draft-for-cleanup")
async def mark_draft_for_cleanup(
    request: dict,
    current_user: UserInfo = Depends(require_auth()),
):
    """
    标记草稿会话以便快速清理（页面关闭时使用）

    前端在用户关闭页面时发送此请求标记空草稿会话。
    被标记的会话将在下次清理时被优先处理。
    """
    try:
        session_id = request.get("sessionId") or request.get("session_id")
        is_empty = request.get("empty", False)

        if not session_id or not is_empty:
            return {"ok": False, "reason": "invalid_request"}

        session_dir = session_manager._get_session_dir(session_id, current_user.user_id)

        if not session_dir.exists():
            return {"ok": False, "reason": "not_found"}

        # 检查metadata确认是空草稿
        meta_path = session_dir / "metadata.json"
        if not meta_path.exists():
            return {"ok": False, "reason": "no_metadata"}

        if not session_manager.is_blank_draft_session(
            session_id,
            current_user.user_id,
        ):
            return {"ok": False, "reason": "not_blank_draft"}

        # 写入标记文件，表示这个草稿可以被快速清理
        # 下次cleanup-drafts时会更严格地检查这个会话
        marker_path = session_dir / ".cleanup_marker"
        marker_path.write_text(
            json.dumps({"marked_at": datetime.now().isoformat(), "reason": "page_closed"}),
            encoding="utf-8",
        )

        logger.info(f"草稿标记为可清理: {current_user.user_id}/{session_id}")
        return {"ok": True}

    except Exception as e:
        logger.error(f"标记草稿失败: {e}")
        return {"ok": False, "reason": "error"}


@router.delete("/{user_id}/{session_id}")
async def delete_session(
    user_id: str,
    session_id: str,
    background_tasks: BackgroundTasks,
    current_user: UserInfo = Depends(require_auth()),
):
    """删除会话"""
    # 检查是否有权访问该用户的数据
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(status_code=403, detail="You can only delete your own sessions")

    try:
        from app.agents.tools.local_ipython_box import LocalIPythonBox

        # 先中断活跃会话，避免流式执行在删除后重新写回 context.jsonl
        try:
            await agent_service.stop_session(user_id, session_id)
        except Exception as stop_err:
            logger.warning(f"中断会话失败（继续删除流程）: {stop_err}")

        LocalIPythonBox.shutdown_kernel(session_id=session_id, user_id=user_id)

        # 先将会话目录快速移出活跃工作区，再后台执行物理删除，
        # 避免同步 rmtree 把浏览器请求拖到超时。
        workspace_registry = get_workspace_registry_service()
        removed_from_workspace = workspace_registry.remove_conversation_by_session_id(
            user_id=user_id,
            session_id=session_id,
        )
        detached_path = session_manager.detach_session_for_deletion(session_id, user_id)
        if detached_path is None and not removed_from_workspace:
            raise HTTPException(status_code=404, detail="会话不存在")

        if detached_path is not None:
            background_tasks.add_task(session_manager.purge_detached_session, detached_path)

        # Session 删除后，触发 Claw runtime 刷新，解除已不存在的 binding
        try:
            from app.services.claw_runtime import get_claw_runtime_manager

            get_claw_runtime_manager().schedule_refresh_for_user(user_id)
        except Exception:
            pass

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除会话失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed") from e
