"""
自动任务 API。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import require_auth
from app.models.user import UserInfo
from app.services.auto_tasks import (
    MIN_INTERVAL_SECONDS,
    AutoTask,
    AutoTaskStore,
    AutoTaskTriggerType,
    FirstRunPolicy,
    HostingBootstrapMode,
    OverlapPolicy,
    TaskCategory,
    TaskStatus,
    ensure_auto_task_allowed_for_workspace,
)
from app.services.workspace_registry import get_workspace_registry_service

router = APIRouter(prefix="/auto-tasks", tags=["auto-tasks"])


def _build_task_response(task: AutoTask) -> dict[str, Any]:
    return task.to_dict()


def _parse_trigger_type(body: dict[str, Any], *, default: str = "interval") -> AutoTaskTriggerType:
    value = body.get("trigger_type", default)
    try:
        return AutoTaskTriggerType(str(value))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="trigger_type 只支持 continuous / interval / cron / once",
        ) from exc


def _parse_session_strategy(
    body: dict[str, Any],
    bind_session_id: str | None,
) -> str:
    value = str(
        body.get(
            "session_strategy",
            "bind_session" if bind_session_id else "new_each_time",
        )
    )
    if value not in {"bind_session", "new_each_time"}:
        raise HTTPException(
            status_code=400,
            detail="session_strategy 只支持 bind_session / new_each_time",
        )
    return value


def _resolve_bind_session_id(body: dict[str, Any]) -> str | None:
    bind_session_id = body.get("bind_session_id")
    if bind_session_id is not None:
        bind_session_id = str(bind_session_id).strip() or None
    session_strategy = _parse_session_strategy(body, bind_session_id)
    if session_strategy == "new_each_time":
        return None
    if not bind_session_id:
        raise HTTPException(
            status_code=400,
            detail="绑定会话模式需要填写 bind_session_id",
        )
    return bind_session_id


def _parse_hosting_bootstrap_mode(value: Any) -> HostingBootstrapMode:
    try:
        return HostingBootstrapMode(str(value or HostingBootstrapMode.resume_only.value))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="hosting_bootstrap_mode 只支持 resume_only / launch_check",
        ) from exc


def _parse_overlap_policy(value: Any) -> OverlapPolicy:
    try:
        return OverlapPolicy(str(value or OverlapPolicy.skip.value))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="overlap_policy 只支持 skip / queue / parallel",
        ) from exc


def _validate_overlap_for_mode(overlap_policy: OverlapPolicy, bind_session_id: str | None) -> None:
    """绑定会话时不允许 parallel，因为没有新建 Session 的场景。"""
    if bind_session_id and overlap_policy == OverlapPolicy.parallel:
        raise HTTPException(
            status_code=400,
            detail="绑定会话模式下 overlap_policy 不能为 parallel，只支持 skip / queue",
        )


def _coerce_max_continuations(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="max_continuations 必须是整数") from exc


def _task_category_for_trigger(trigger_type: AutoTaskTriggerType) -> TaskCategory:
    if trigger_type == AutoTaskTriggerType.continuous:
        return TaskCategory.continuous
    return TaskCategory.scheduled


def _parse_first_run_policy(value: Any) -> FirstRunPolicy:
    try:
        return FirstRunPolicy(str(value or FirstRunPolicy.next_scheduled.value))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="first_run_policy 只支持 immediate / next_scheduled",
        ) from exc


def _parse_task_status(value: Any, *, default: TaskStatus = TaskStatus.active) -> TaskStatus:
    try:
        return TaskStatus(str(value or default.value))
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="status 只支持 active / paused / disabled / completed"
        ) from exc


def _coerce_stop_on_consecutive_errors(value: Any) -> int:
    try:
        v = int(value)
        if v < 1:
            raise ValueError()
        return v
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail="stop_on_consecutive_errors 必须是正整数"
        ) from exc


def _validate_trigger_value(trigger_type: AutoTaskTriggerType, trigger_value: str) -> None:
    if trigger_type == AutoTaskTriggerType.once:
        try:
            datetime.fromisoformat(trigger_value)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail="单次执行需要填写有效时间",
            ) from exc
    elif trigger_type == AutoTaskTriggerType.interval:
        try:
            value = int(trigger_value)
            if value < MIN_INTERVAL_SECONDS:
                raise ValueError()
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"按间隔执行最短支持 {MIN_INTERVAL_SECONDS} 秒",
            ) from exc
    elif trigger_type == AutoTaskTriggerType.cron:
        from croniter import croniter

        try:
            croniter(trigger_value)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail="按固定时间需要填写有效的 5 段时间规则，例如 0 8 * * *",
            ) from exc


@router.get("/tasks")
async def list_all_tasks(
    status: TaskStatus | None = None,
    user: UserInfo = Depends(require_auth()),
):
    """全局视角：列出当前用户所有工作区下的自动任务"""
    all_tasks: list[dict[str, Any]] = []
    registry = get_workspace_registry_service()
    for workspace in registry.list_workspaces(user.user_id, include_conversations=False):
        tasks = AutoTaskStore.list_tasks(user.user_id, workspace.workspace_id)
        for task in tasks:
            if status is not None and task.status != status:
                continue
            item = _build_task_response(task)
            item["workspace_id"] = workspace.workspace_id
            item["workspace_title"] = workspace.title
            all_tasks.append(item)
    return {"user_id": user.user_id, "tasks": all_tasks}


@router.get("/tasks/summary")
async def get_tasks_summary(
    user: UserInfo = Depends(require_auth()),
):
    """全局视角：获取当前用户所有自动任务的统计摘要"""
    counts = {"total": 0, "active": 0, "paused": 0, "disabled": 0, "completed": 0}
    registry = get_workspace_registry_service()
    workspaces: list[dict[str, Any]] = []
    latest_run: dict[str, Any] | None = None

    for workspace in registry.list_workspaces(user.user_id, include_conversations=False):
        tasks = AutoTaskStore.list_tasks(user.user_id, workspace.workspace_id)
        if not tasks:
            continue
        ws_counts = {"total": len(tasks), "active": 0, "paused": 0, "disabled": 0, "completed": 0}
        for task in tasks:
            counts["total"] += 1
            ws_counts[task.status.value] += 1
            counts[task.status.value] += 1
            if task.last_run_at:
                if latest_run is None or task.last_run_at > latest_run["last_run_at"]:
                    latest_run = {
                        "task_id": task.task_id,
                        "title": task.title,
                        "workspace_id": workspace.workspace_id,
                        "workspace_title": workspace.title,
                        "last_run_at": task.last_run_at,
                        "status": task.status.value,
                    }
        workspaces.append(
            {
                "workspace_id": workspace.workspace_id,
                "workspace_title": workspace.title,
                "counts": ws_counts,
            }
        )

    return {
        "user_id": user.user_id,
        "counts": counts,
        "workspaces": workspaces,
        "latest_run": latest_run,
    }


@router.get("/workspaces/{workspace_id}/tasks")
async def list_tasks(
    workspace_id: str,
    user: UserInfo = Depends(require_auth()),
):
    """列出工作区下的所有自动任务"""
    _ensure_workspace_exists(user.user_id, workspace_id)
    tasks = AutoTaskStore.list_tasks(user.user_id, workspace_id)
    return {"workspace_id": workspace_id, "tasks": [_build_task_response(task) for task in tasks]}


@router.post("/workspaces/{workspace_id}/tasks")
async def create_task(
    workspace_id: str,
    body: dict[str, Any],
    user: UserInfo = Depends(require_auth()),
):
    """在工作区下创建自动任务"""
    registry = _ensure_workspace_exists(user.user_id, workspace_id)
    _ensure_auto_task_control_allowed(
        user_id=user.user_id,
        workspace_id=workspace_id,
        workspace_registry=registry,
    )

    trigger_type = _parse_trigger_type(body)
    task_category = _task_category_for_trigger(trigger_type)
    first_run_policy = _parse_first_run_policy(body.get("first_run_policy"))
    if task_category == TaskCategory.continuous:
        first_run_policy = FirstRunPolicy.immediate

    trigger_value = body.get("trigger_value", "")
    if task_category == TaskCategory.continuous:
        trigger_value = ""
    if not trigger_value and trigger_type != AutoTaskTriggerType.continuous:
        raise HTTPException(status_code=400, detail="trigger_value 不能为空")

    _validate_trigger_value(trigger_type, trigger_value)

    prompt = body.get("prompt", "")
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt 不能为空")

    bind_session_id = _resolve_bind_session_id(body)

    now = datetime.now().isoformat()
    task = AutoTask(
        task_id=str(uuid4()),
        workspace_id=workspace_id,
        user_id=user.user_id,
        prompt=prompt,
        trigger_type=trigger_type,
        trigger_value=trigger_value,
        status=_parse_task_status(body.get("status")),
        title=body.get("title", ""),
        created_at=now,
        updated_at=now,
        model=body.get("model"),
        model_id=body.get("model_id"),
        sandbox_mode=body.get("sandbox_mode"),
        attachments=body.get("attachments") or [],
        auto_enable_hosting=bool(body.get("auto_enable_hosting", False)),
        hosting_bootstrap_mode=_parse_hosting_bootstrap_mode(body.get("hosting_bootstrap_mode")),
        overlap_policy=_parse_overlap_policy(body.get("overlap_policy")),
        bind_session_id=bind_session_id,
        continuation_prompt=body.get("continuation_prompt"),
        max_continuations=_coerce_max_continuations(body.get("max_continuations", -1)),
        task_category=task_category,
        first_run_policy=first_run_policy,
        stop_on_consecutive_errors=_coerce_stop_on_consecutive_errors(
            body.get("stop_on_consecutive_errors", 10)
        ),
        stop_on_signal=bool(body.get("stop_on_signal", True)),
    )

    _validate_overlap_for_mode(task.overlap_policy, task.bind_session_id)

    from app.services.auto_tasks.engine import _calculate_next_run

    next_run = _calculate_next_run(task)
    task.next_run_at = next_run.isoformat() if next_run else None

    AutoTaskStore.put_task(user.user_id, workspace_id, task)
    return _build_task_response(task)


@router.get("/workspaces/{workspace_id}/tasks/{task_id}")
async def get_task(
    workspace_id: str,
    task_id: str,
    user: UserInfo = Depends(require_auth()),
):
    """获取单个自动任务详情"""
    _ensure_workspace_exists(user.user_id, workspace_id)
    task = AutoTaskStore.get_task(user.user_id, workspace_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _build_task_response(task)


@router.put("/workspaces/{workspace_id}/tasks/{task_id}")
async def update_task(
    workspace_id: str,
    task_id: str,
    body: dict[str, Any],
    user: UserInfo = Depends(require_auth()),
):
    """更新自动任务"""
    registry = _ensure_workspace_exists(user.user_id, workspace_id)
    _ensure_auto_task_control_allowed(
        user_id=user.user_id,
        workspace_id=workspace_id,
        workspace_registry=registry,
    )
    task = AutoTaskStore.get_task(user.user_id, workspace_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if "trigger_type" in body:
        task.trigger_type = _parse_trigger_type(
            body,
            default=task.trigger_type.value,
        )
        task.task_category = _task_category_for_trigger(task.trigger_type)

    if "trigger_value" in body:
        task.trigger_value = body["trigger_value"]

    if "prompt" in body:
        task.prompt = body["prompt"]

    if "title" in body:
        task.title = body["title"]

    if "status" in body:
        task.status = _parse_task_status(body["status"], default=task.status)

    if "model" in body:
        task.model = body["model"]
    if "model_id" in body:
        task.model_id = body["model_id"]
    if "sandbox_mode" in body:
        task.sandbox_mode = body["sandbox_mode"]
    if "attachments" in body:
        task.attachments = body["attachments"] or []
    if "auto_enable_hosting" in body:
        task.auto_enable_hosting = bool(body.get("auto_enable_hosting"))
    if "hosting_bootstrap_mode" in body:
        task.hosting_bootstrap_mode = _parse_hosting_bootstrap_mode(
            body.get("hosting_bootstrap_mode")
        )
    if "overlap_policy" in body:
        task.overlap_policy = _parse_overlap_policy(body.get("overlap_policy"))

    if "bind_session_id" in body or "session_strategy" in body:
        bind_body = dict(body)
        if "bind_session_id" not in bind_body:
            bind_body["bind_session_id"] = task.bind_session_id
        task.bind_session_id = _resolve_bind_session_id(bind_body)

    if "continuation_prompt" in body:
        task.continuation_prompt = body["continuation_prompt"] or None

    if "max_continuations" in body:
        task.max_continuations = _coerce_max_continuations(body["max_continuations"])

    task.task_category = _task_category_for_trigger(task.trigger_type)

    if "first_run_policy" in body:
        task.first_run_policy = _parse_first_run_policy(body["first_run_policy"])

    if task.task_category == TaskCategory.continuous:
        task.first_run_policy = FirstRunPolicy.immediate
        task.trigger_value = ""

    if "stop_on_consecutive_errors" in body:
        task.stop_on_consecutive_errors = _coerce_stop_on_consecutive_errors(
            body["stop_on_consecutive_errors"]
        )

    if "stop_on_signal" in body:
        task.stop_on_signal = bool(body["stop_on_signal"])

    _validate_overlap_for_mode(task.overlap_policy, task.bind_session_id)
    _validate_trigger_value(task.trigger_type, task.trigger_value)

    if "prompt" in body and not task.prompt:
        raise HTTPException(status_code=400, detail="prompt 不能为空")

    task.updated_at = datetime.now().isoformat()

    from app.services.auto_tasks.engine import _calculate_next_run

    next_run = _calculate_next_run(task)
    task.next_run_at = next_run.isoformat() if next_run else None

    AutoTaskStore.put_task(user.user_id, workspace_id, task)
    return _build_task_response(task)


@router.delete("/workspaces/{workspace_id}/tasks/{task_id}")
async def delete_task(
    workspace_id: str,
    task_id: str,
    user: UserInfo = Depends(require_auth()),
):
    """删除自动任务"""
    _ensure_workspace_exists(user.user_id, workspace_id)
    ok = AutoTaskStore.delete_task(user.user_id, workspace_id, task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"task_id": task_id, "deleted": True}


@router.post("/workspaces/{workspace_id}/tasks/{task_id}/run")
async def run_task_now(
    workspace_id: str,
    task_id: str,
    user: UserInfo = Depends(require_auth()),
):
    """立即执行一次自动任务，而不只是写入 trigger。"""
    registry = _ensure_workspace_exists(user.user_id, workspace_id)
    _ensure_auto_task_control_allowed(
        user_id=user.user_id,
        workspace_id=workspace_id,
        workspace_registry=registry,
    )
    task = AutoTaskStore.get_task(user.user_id, workspace_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    from app.services.auto_tasks.engine import run_task_now_with_lock

    result = await run_task_now_with_lock(
        task,
        origin="auto_task_manual_run",
    )
    return {"task_id": task_id, "result": result}


@router.get("/workspaces/{workspace_id}/sessions/bindable")
async def list_bindable_sessions(
    workspace_id: str,
    user: UserInfo = Depends(require_auth()),
):
    """列出工作区下可绑定的活跃 session。"""
    _ensure_workspace_exists(user.user_id, workspace_id)
    sessions = AutoTaskStore.list_tasks(user.user_id, workspace_id)
    bound_ids = {t.bind_session_id for t in sessions if t.bind_session_id}

    from app.core.config import WORKSPACE_DIR
    from app.services.session.core import SessionManager

    session_manager = SessionManager(WORKSPACE_DIR)
    registry = get_workspace_registry_service()
    ws_root = registry.get_workspace_root(user.user_id, workspace_id)
    sessions_dir = ws_root / ".aiasys" / "workspace" / "sessions"
    bindable: list[dict] = []

    if sessions_dir.exists():
        for session_file in sessions_dir.iterdir():
            if not session_file.is_file() or not session_file.name.endswith(".json"):
                continue
            session_id = session_file.stem
            try:
                meta = session_manager.get_session(session_id, user.user_id)
                if meta is None:
                    continue
                # 排除已绑定到其他自动任务的 session
                if session_id in bound_ids:
                    continue
                bindable.append(
                    {
                        "session_id": session_id,
                        "title": meta.title,
                        "status": meta.status,
                        "message_count": meta.message_count,
                    }
                )
            except Exception:
                continue

    return {"workspace_id": workspace_id, "sessions": bindable}


def _ensure_workspace_exists(user_id: str, workspace_id: str):
    registry = get_workspace_registry_service()
    try:
        registry._read_workspace_meta(user_id, workspace_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="工作区不存在") from exc
    return registry


def _ensure_auto_task_control_allowed(
    *,
    user_id: str,
    workspace_id: str,
    workspace_registry,
) -> None:
    ensure_auto_task_allowed_for_workspace(
        user_id=user_id,
        workspace_id=workspace_id,
        workspace_registry=workspace_registry,
    )
