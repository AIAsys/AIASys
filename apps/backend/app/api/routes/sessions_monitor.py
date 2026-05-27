"""Session Monitor API — 后台监听任务管理。"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import require_auth
from app.models.user import UserInfo
from app.services.agent.runtime_backends.aiasys.tools.monitor_tool import get_monitor_service
from app.services.workspace_registry import get_workspace_registry_service

from .sessions_models import (
    GlobalMonitorInfoResponse,
    GlobalMonitorListResponse,
    GlobalMonitorSummaryResponse,
    MonitorDetailResponse,
    MonitorInfoResponse,
    MonitorListResponse,
    MonitorSegment,
    MonitorSegmentsResponse,
    MonitorSpawnRequest,
    MonitorSpawnResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/monitors", response_model=GlobalMonitorListResponse)
async def list_all_monitors(
    status: str | None = None,
    user: UserInfo = Depends(require_auth()),
):
    """全局视角：列出当前用户所有 session 的 monitor"""
    service = get_monitor_service()
    all_monitors = service.list_global_monitors(user.user_id)

    if status:
        status = status.strip().lower()
        all_monitors = [m for m in all_monitors if m.get("status", "").lower() == status]

    monitors = [
        GlobalMonitorInfoResponse(
            id=m["id"],
            command=m["command"],
            status=m["status"],
            exit_code=m.get("exit_code"),
            mode=m.get("mode", "notify"),
            created_at=m["created_at"],
            completed_at=m.get("completed_at"),
            session_id=m["session_id"],
            session_key=m["session_key"],
            workspace_id=m.get("workspace_id", ""),
            workspace_title=m.get("workspace_title", ""),
        )
        for m in all_monitors
    ]
    return GlobalMonitorListResponse(monitors=monitors)


@router.get("/monitors/summary", response_model=GlobalMonitorSummaryResponse)
async def get_all_monitors_summary(
    user: UserInfo = Depends(require_auth()),
):
    """全局视角：获取当前用户所有 monitor 的统计摘要"""
    service = get_monitor_service()
    all_monitors = service.list_global_monitors(user.user_id)

    counts = {"total": 0, "running": 0, "completed": 0, "error": 0, "killed": 0}
    for m in all_monitors:
        counts["total"] += 1
        st = m.get("status", "").lower()
        if st in counts:
            counts[st] += 1

    return GlobalMonitorSummaryResponse(
        total=counts["total"],
        running=counts["running"],
        completed=counts["completed"],
        error=counts["error"],
        killed=counts["killed"],
    )


@router.post("/{user_id}/{session_id}/monitors/spawn", response_model=MonitorSpawnResponse)
async def spawn_session_monitor(
    user_id: str,
    session_id: str,
    req: MonitorSpawnRequest,
    user: UserInfo = Depends(require_auth()),
):
    """用户在前端手动启动一个后台监听任务。"""
    session_key = f"{user_id}:{session_id}"
    service = get_monitor_service()

    # 未指定 cwd 时，默认使用 session 对应的工作区目录
    cwd = req.cwd
    if cwd is None:
        try:
            cwd = str(get_workspace_registry_service().get_session_dir(user_id, session_id))
        except Exception:
            pass

    session = await service.spawn(
        command=req.command,
        session_key=session_key,
        cwd=cwd,
        timeout_seconds=req.timeout_seconds,
        mode=req.mode or "notify",
    )
    return MonitorSpawnResponse(
        monitor_id=session.id,
        command=session.command,
        status=session.status,
        mode=session.mode,
        created_at=session.created_at,
    )


@router.get("/{user_id}/{session_id}/monitors", response_model=MonitorListResponse)
async def list_session_monitors(
    user_id: str,
    session_id: str,
    user: UserInfo = Depends(require_auth()),
):
    """列出指定 session 的所有 monitor（包含持久化中的已结束任务）。"""
    session_key = f"{user_id}:{session_id}"
    service = get_monitor_service()

    # 内存中活跃态
    active = {m.id: m for m in service.list_by_session(session_key)}

    # 持久化中的全部（包含已结束）
    persistent = service.list_persistent_monitors(session_key)

    # 合并：内存态优先（状态更实时）
    merged: dict[str, dict[str, Any]] = {}
    for meta in persistent:
        mid = meta.get("id")
        if mid:
            merged[mid] = dict(meta)
    for mid, m in active.items():
        merged[mid] = {
            "id": m.id,
            "command": m.command,
            "status": m.status,
            "exit_code": m.exit_code,
            "mode": m.mode,
            "created_at": m.created_at,
            "completed_at": m.completed_at,
        }

    monitors = [
        MonitorInfoResponse(
            id=m["id"],
            command=m.get("command", ""),
            status=m.get("status", "unknown"),
            exit_code=m.get("exit_code"),
            mode=m.get("mode", "notify"),
            created_at=m.get("created_at", 0),
            completed_at=m.get("completed_at"),
        )
        for m in merged.values()
    ]
    # 按 created_at 倒序
    monitors.sort(key=lambda x: x.created_at, reverse=True)
    return MonitorListResponse(monitors=monitors)


@router.get("/{user_id}/{session_id}/monitors/{monitor_id}", response_model=MonitorDetailResponse)
async def get_session_monitor(
    user_id: str,
    session_id: str,
    monitor_id: str,
    user: UserInfo = Depends(require_auth()),
):
    """获取单个 monitor 的详情和全部 segments。"""
    session_key = f"{user_id}:{session_id}"
    service = get_monitor_service()

    detail = service.get_persistent_monitor_detail(session_key, monitor_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Monitor 不存在")

    info = detail["info"]
    segments = detail.get("segments", [])

    # 如果内存中有运行态，用内存状态覆盖
    active = service.get(monitor_id)
    if active is not None and active.session_key == session_key:
        info["status"] = active.status
        info["exit_code"] = active.exit_code
        info["completed_at"] = active.completed_at

    return MonitorDetailResponse(
        info=MonitorInfoResponse(
            id=info.get("id", monitor_id),
            command=info.get("command", ""),
            status=info.get("status", "unknown"),
            exit_code=info.get("exit_code"),
            created_at=info.get("created_at", 0),
            completed_at=info.get("completed_at"),
        ),
        segments=[
            MonitorSegment(
                index=s.get("index", 0),
                timestamp=s.get("timestamp", ""),
                content=s.get("content", ""),
                is_stderr=s.get("is_stderr", False),
            )
            for s in segments
        ],
    )


@router.get(
    "/{user_id}/{session_id}/monitors/{monitor_id}/segments",
    response_model=MonitorSegmentsResponse,
)
async def get_session_monitor_segments(
    user_id: str,
    session_id: str,
    monitor_id: str,
    since_index: int = Query(0, ge=0),
    user: UserInfo = Depends(require_auth()),
):
    """获取单个 monitor 的增量 segments（从 since_index 开始）。"""
    session_key = f"{user_id}:{session_id}"
    service = get_monitor_service()

    # 如果 monitor 还在内存中，先同步最新 segments
    monitor = service.get(monitor_id)
    if monitor is not None and monitor.session_key == session_key and monitor.status == "running":
        service._sync_segments_from_logs(monitor)

    segs = service.get_persistent_monitor_segments(session_key, monitor_id, since_index)
    return MonitorSegmentsResponse(
        monitor_id=monitor_id,
        segments=[
            MonitorSegment(
                index=s.get("index", 0),
                timestamp=s.get("timestamp", ""),
                content=s.get("content", ""),
                is_stderr=s.get("is_stderr", False),
            )
            for s in segs
        ],
    )


@router.post("/{user_id}/{session_id}/monitors/{monitor_id}/kill")
async def kill_session_monitor(
    user_id: str,
    session_id: str,
    monitor_id: str,
    user: UserInfo = Depends(require_auth()),
):
    """终止指定 monitor 进程。"""
    session_key = f"{user_id}:{session_id}"
    monitor = get_monitor_service().get(monitor_id)
    if monitor is None or monitor.session_key != session_key:
        raise HTTPException(status_code=404, detail="Monitor 不存在")
    await get_monitor_service().kill(monitor_id)
    return {"success": True, "monitor_id": monitor_id}


@router.put("/{user_id}/{session_id}/monitors/{monitor_id}/mode")
async def update_monitor_mode(
    user_id: str,
    session_id: str,
    monitor_id: str,
    mode: str,
    user: UserInfo = Depends(require_auth()),
):
    """修改指定 monitor 的模式（notify/silent）。"""
    session_key = f"{user_id}:{session_id}"
    if mode not in ("notify", "silent"):
        raise HTTPException(status_code=400, detail="mode 必须是 notify 或 silent")
    ok = get_monitor_service().set_mode_by_session(session_key, monitor_id, mode)
    if not ok:
        raise HTTPException(status_code=404, detail="Monitor 不存在")
    return {"success": True, "monitor_id": monitor_id, "mode": mode}


@router.delete("/{user_id}/{session_id}/monitors/{monitor_id}")
async def delete_session_monitor(
    user_id: str,
    session_id: str,
    monitor_id: str,
    user: UserInfo = Depends(require_auth()),
):
    """删除指定 monitor（包括持久化文件）。"""
    session_key = f"{user_id}:{session_id}"
    deleted = await get_monitor_service().delete_by_session(session_key, monitor_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Monitor 不存在")
    return {"success": True, "monitor_id": monitor_id}


@router.get("/{user_id}/{session_id}/monitors/{monitor_id}/poll")
async def poll_session_monitor(
    user_id: str,
    session_id: str,
    monitor_id: str,
    offset: int = Query(0, ge=0),
    user: UserInfo = Depends(require_auth()),
):
    """轮询 monitor 从指定 offset 开始的最新原始输出。"""
    session_key = f"{user_id}:{session_id}"
    service = get_monitor_service()
    monitor = service.get(monitor_id)
    if monitor is None or monitor.session_key != session_key:
        raise HTTPException(status_code=404, detail="Monitor 不存在")

    # 先同步最新 segments
    service._sync_segments_from_logs(monitor)
    # 从持久化 segments 读取全部内容拼接（poll 端点已弃用，/segments 为推荐接口）
    segs = service.get_persistent_monitor_segments(session_key, monitor_id, 0)
    output = "\n".join(s.get("content", "") for s in segs)

    return {
        "id": monitor.id,
        "command": monitor.command,
        "status": monitor.status,
        "exit_code": monitor.exit_code,
        "output": output,
        "output_offset": len(output.encode("utf-8")),
        "created_at": monitor.created_at,
        "completed_at": monitor.completed_at,
    }
