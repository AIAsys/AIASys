"""
会话管理 API

支持多用户隔离和认证
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import require_auth
from app.core.config import WORKSPACE_DIR
from app.models.session import (
    SessionMetadata,
)
from app.models.user import UserInfo
from app.services.agent import agent_service
from app.services.agent.compaction import estimate_text_tokens
from app.services.export import (
    SessionExportService,
)
from app.services.llm.llm_config_service import get_llm_config_service
from app.services.llm.model_selection_service import get_model_selection_service
from app.services.session import SessionManager
from app.services.workspace_registry import get_workspace_registry_service

from .sessions_models import (
    BudgetResponse,
    SetSessionBudgetRequest,
    TokenStatsResponse,
)

logger = logging.getLogger(__name__)

CLEAR_CONTEXT_MARKER_TEXT = "当前会话已清理，后续回复不会继承以上上下文。"

session_manager = SessionManager(WORKSPACE_DIR)

session_export_service = SessionExportService(session_manager)


def _build_collaboration_node_summary(user_id: str, session_id: str) -> dict:
    """构建当前会话协作节点摘要，供前端决定默认主画布视图。"""
    try:
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


def _is_runtime_busy(user_id: str, session_id: str) -> bool:
    session_key = f"{user_id}/{session_id}"
    session_lock = getattr(agent_service, "_session_locks", {}).get(session_key)
    return bool(session_lock and session_lock.locked())


async def _manual_replay_records(
    *,
    user_id: str,
    session_id: str,
    session_dir,
    metadata: SessionMetadata,
    records: list[dict],
    restart_runtime: bool,
) -> dict:
    from app.agents.tools.local_ipython_box import (
        LocalIPythonBox,
        LocalIPythonBoxParams,
    )

    replayed_sequences: list[int] = []
    failed_sequence: Optional[int] = None
    failed_error: Optional[str] = None

    if restart_runtime:
        LocalIPythonBox.shutdown_kernel(session_id=session_id, user_id=user_id)

    tool = LocalIPythonBox()
    tool.workspace = session_dir
    tool.session_id = session_id
    tool.record_execution = False

    for record in records:
        result = await tool.invoke(
            **LocalIPythonBoxParams(
                code=record["code"],
                restart=False,
            ).model_dump()
        )
        if getattr(result, "is_error", False):
            failed_sequence = record.get("sequence")
            failed_error = getattr(result, "message", None) or getattr(result, "brief", None)
            break
        replayed_sequences.append(int(record.get("sequence") or 0))

    return {
        "replayed_sequences": replayed_sequences,
        "failed_sequence": failed_sequence,
        "error": failed_error,
        "completed": failed_sequence is None,
    }


def _get_session_owner_from_metadata(
    session_manager, session_id: str, user_id: str
) -> Optional[str]:
    """从 session metadata 中获取真实的 owner user_id"""
    try:
        metadata = session_manager.get_session(session_id, user_id)
        if metadata and hasattr(metadata, "user_id") and metadata.user_id:
            return metadata.user_id
    except Exception as exc:
        logger.warning("获取会话 owner 失败: %s/%s: %s", user_id, session_id, exc)
    return None


def _read_subagent_control_excerpt(
    user_id: str,
    session_id: str,
    agent_id: str,
    filename: str,
    *,
    limit: int = 2000,
) -> str | None:
    from app.services.tracking import _get_session_subagents_dir

    path = _get_session_subagents_dir(user_id, session_id) / agent_id / filename
    try:
        if not path.exists() or not path.is_file():
            return None
        text = path.read_text(encoding="utf-8").strip()
    except Exception:
        logger.warning("读取协作节点控制摘要失败: %s", path)
        return None

    if not text:
        return None
    return text[:limit]


def _find_available_draft_for_user(current_user: UserInfo):
    user_dir = session_manager.base_dir / current_user.user_id
    if not user_dir.exists():
        return {"available": False, "reason": "no_user_dir"}

    draft_sessions = []
    now = datetime.now()
    threshold = timedelta(minutes=30)

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


from app.services.tracking import (
    SubAgentTrackingService,
    get_subagent_tracking_service,
)


def _get_tracking_service() -> SubAgentTrackingService:
    """获取 SubAgent 跟踪服务"""
    return get_subagent_tracking_service()


def _get_hosting_binding_for_session(
    *,
    user_id: str,
    session_id: str,
):
    """返回 session 绑定的工作区信息（托管自动化已移除，control_state 固定为 None）。"""
    workspace_registry = get_workspace_registry_service()
    workspace_id = workspace_registry.find_workspace_id_by_session_id(user_id, session_id)
    if not workspace_id:
        return None, None, None
    workspace_root = workspace_registry.get_workspace_root(user_id, workspace_id)
    return workspace_id, workspace_root, None


from app.api.routes.sessions_branches import router as sessions_branches_router
from app.api.routes.sessions_execution import router as sessions_execution_router
from app.api.routes.sessions_exports import router as sessions_exports_router
from app.api.routes.sessions_messages import router as sessions_messages_router
from app.api.routes.sessions_monitor import router as sessions_monitor_router
from app.api.routes.sessions_tools import router as sessions_tools_router

router = APIRouter(tags=["sessions"])
# _monitor_router 必须先注册，其 /monitors 和 /monitors/summary 为精确路由，
# 若排在 sessions_branches_router（含 /{user_id} 通配）之后会被错误匹配。
router.include_router(sessions_monitor_router)


@router.put("/{user_id}/{session_id}/budget")
async def set_session_budget(
    user_id: str,
    session_id: str,
    request: SetSessionBudgetRequest,
    user: UserInfo = Depends(require_auth()),
):
    """设置 session 级独立预算。"""
    metadata_obj = session_manager.get_session(session_id, user_id)
    if metadata_obj is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    from app.models.session import SessionBudget

    existing = metadata_obj.budget
    budget = SessionBudget(
        token_budget=request.token_budget,
        tokens_used=existing.tokens_used if existing else 0,
        time_budget_seconds=request.time_budget_seconds,
        time_used_seconds=existing.time_used_seconds if existing else 0,
        status="active",
    )

    ok = session_manager.update_session_budget(session_id, user_id, budget=budget)
    if not ok:
        raise HTTPException(status_code=500, detail="设置失败")

    _session_key = f"{user_id}/{session_id}"
    _active_session = getattr(agent_service, "_active_sessions", {}).get(_session_key)
    if _active_session is not None and hasattr(_active_session, "budget"):
        _active_session.budget = budget

    return {"success": True}


@router.delete("/{user_id}/{session_id}/budget")
async def clear_session_budget(
    user_id: str,
    session_id: str,
    user: UserInfo = Depends(require_auth()),
):
    """关闭 session 级预算控制。"""
    metadata_obj = session_manager.get_session(session_id, user_id)
    if metadata_obj is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    ok = session_manager.update_session_budget(session_id, user_id, budget=None)
    if not ok:
        raise HTTPException(status_code=500, detail="清除失败")

    _session_key = f"{user_id}/{session_id}"
    _active_session = getattr(agent_service, "_active_sessions", {}).get(_session_key)
    if _active_session is not None and hasattr(_active_session, "budget"):
        _active_session.budget = None

    return {"success": True}


@router.get("/{user_id}/{session_id}/budget", response_model=Optional[BudgetResponse])
async def get_session_budget(
    user_id: str,
    session_id: str,
    user: UserInfo = Depends(require_auth()),
):
    """查询 session 级预算状态。"""
    metadata_obj = session_manager.get_session(session_id, user_id)
    if metadata_obj is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    budget = metadata_obj.budget
    if budget is None:
        return None

    return BudgetResponse(
        token_budget=budget.token_budget,
        tokens_used=budget.tokens_used,
        time_budget_seconds=budget.time_budget_seconds,
        time_used_seconds=budget.time_used_seconds,
        status=budget.status,
    )


@router.get("/{user_id}/{session_id}/tokens", response_model=TokenStatsResponse)
async def get_session_token_stats(
    user_id: str,
    session_id: str,
    user: UserInfo = Depends(require_auth()),
):
    """查询 session 级 Token 监控数据（上下文占用/预算/上轮消耗）。"""
    metadata_obj = session_manager.get_session(session_id, user_id)
    if metadata_obj is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    budget = metadata_obj.budget
    tokens_used = budget.tokens_used if budget else 0
    token_budget = budget.token_budget if budget else None
    context_tokens = _resolve_session_context_tokens(
        user_id=user_id,
        session_id=session_id,
        metadata_obj=metadata_obj,
    )
    budget_status = budget.status if budget else "active"

    context_window = _get_model_context_window(
        metadata_obj,
        user_id=user_id,
        session_id=session_id,
    )

    context_usage_pct = 0.0
    if context_window and context_window > 0:
        context_usage_pct = round((context_tokens / context_window) * 100, 1)

    return TokenStatsResponse(
        tokens_used=tokens_used,
        token_budget=token_budget,
        context_tokens=context_tokens,
        context_window=context_window,
        context_usage_pct=context_usage_pct,
        budget_status=budget_status,
    )


def _coerce_positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _read_model_config_value(model_cfg: Any, key: str) -> Any:
    if isinstance(model_cfg, dict):
        return model_cfg.get(key)
    return getattr(model_cfg, key, None)


def _get_model_context_window(
    metadata_obj: Any,
    *,
    user_id: str,
    session_id: str,
) -> int | None:
    """从当前会话生效模型配置中推断上下文窗口大小。"""
    model_id: str | None = None
    try:
        model_id = get_model_selection_service().resolve_effective_model_id(
            user_id=user_id,
            session_id=session_id,
        )
    except Exception:
        pass

    if not model_id:
        model_id = (
            getattr(metadata_obj, "preferred_model_id", None)
            or getattr(metadata_obj, "model_id", None)
            or getattr(metadata_obj, "model", None)
        )
    if not model_id:
        return None

    try:
        full_config = get_llm_config_service().get_full_config(user_id)
        raw_models = full_config.get("models") if isinstance(full_config, dict) else {}
        model_cfg = raw_models.get(model_id) if isinstance(raw_models, dict) else None
        if model_cfg is not None:
            return (
                _coerce_positive_int(_read_model_config_value(model_cfg, "max_context_size"))
                or _coerce_positive_int(_read_model_config_value(model_cfg, "context_window"))
                or _coerce_positive_int(_read_model_config_value(model_cfg, "context_length"))
            )
    except Exception:
        logger.debug(
            "从 LLM 配置读取上下文窗口失败: user=%s session=%s model=%s",
            user_id,
            session_id,
            model_id,
            exc_info=True,
        )
    return None


def _iter_jsonl_messages(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    messages: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    messages.append(item)
    except Exception:
        logger.debug("读取 context.jsonl 失败: %s", path, exc_info=True)
    return messages


def _iter_snapshot_messages(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.debug("读取 history snapshot 失败: %s", path, exc_info=True)
        return []
    if isinstance(payload, dict):
        messages = payload.get("messages") or []
        if isinstance(messages, list):
            return [item for item in messages if isinstance(item, dict)]
    return []


def _resolve_session_context_tokens(
    *,
    user_id: str,
    session_id: str,
    metadata_obj: Any,
) -> int:
    """返回当前上下文占用估算，不依赖预算是否开启。"""
    session_key = f"{user_id}/{session_id}"
    active_session = getattr(agent_service, "_active_sessions", {}).get(session_key)
    active_count = _coerce_positive_int(
        getattr(active_session, "_estimated_token_count", None)
        if active_session is not None
        else None
    )
    if active_count is not None:
        return active_count

    budget = getattr(metadata_obj, "budget", None)
    budget_context = _coerce_positive_int(getattr(budget, "context_tokens", None))
    if budget_context is not None:
        return budget_context

    session_dir = session_manager._get_session_dir(session_id, user_id)
    context_path = session_dir / ".aiasys/session" / session_id / "context.jsonl"
    messages = _iter_jsonl_messages(context_path)
    if messages:
        return estimate_text_tokens(messages)

    from app.services.session.constants import (
        ACTIVE_SESSION_STATE_DIR_NAME,
        HISTORY_SNAPSHOT_FILE_NAME,
    )

    snapshot_path = (
        session_dir / ".aiasys/session" / ACTIVE_SESSION_STATE_DIR_NAME / HISTORY_SNAPSHOT_FILE_NAME
    )
    return estimate_text_tokens(_iter_snapshot_messages(snapshot_path))


router.include_router(sessions_branches_router)
router.include_router(sessions_messages_router)
router.include_router(sessions_execution_router)
router.include_router(sessions_exports_router)
router.include_router(sessions_tools_router)
