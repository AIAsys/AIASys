"""Memory resolve 预览与原始内容读写 API（纯文本版）。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.routes.memory_schemas import (
    MemoryPipelineStatusResponse,
    MemoryRetentionRequest,
    MemoryRetentionResponse,
    MemorySummaryResponse,
    MemoryVersionDetailResponse,
    MemoryVersionItem,
    MemoryVersionListResponse,
    RegenerateMemorySummaryRequest,
    ResolveMemoryRequest,
    ResolveMemoryResponse,
    RestoreMemoryVersionResponse,
)
from app.core.auth import require_auth
from app.core.config import WORKSPACE_DIR, get_user_global_memory_dir
from app.models.user import UserInfo
from app.utils.path_utils import as_system_path
from app.services.memory.constants import (
    MAX_MEMORY_SIZE,
    MAX_SUMMARY_SIZE,
    MAX_WORKSPACE_MEMORY_SIZE,
    USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
    is_user_default_global_workspace_scope,
    normalize_memory_scope_key,
)
from app.services.memory.pipeline import (
    STATE_DB_FILE_NAME,
    MemoryPipelineService,
    get_memory_state_runtime,
)
from app.services.memory.resolver import (
    MemoryResolver,
    _get_memory_summary_path_if_exists,
    get_user_memory_file_path,
    get_workspace_memory_file_path,
    get_workspace_memory_summary_file_path,
    invalidate_user_resolver_cache,
)
from app.services.memory.store import (
    MemoryCapacityError,
    MemorySecurityError,
    MemoryStore,
)
from app.services.session.config_projection import read_runtime_config_state
from app.utils.validators import validate_id

router = APIRouter(prefix="/memory", tags=["memory"])


def _get_session_dir(user_id: str, session_id: str) -> Path:
    return Path(WORKSPACE_DIR) / user_id / session_id


def _get_user_dir(user_id: str) -> Path:
    return Path(WORKSPACE_DIR) / user_id


def _get_workspace_registry():
    from app.services.workspace_registry import WorkspaceRegistryService

    return WorkspaceRegistryService(Path(WORKSPACE_DIR))


def _ensure_user_access(current_user: UserInfo, user_id: str) -> None:
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="无权访问该用户的 memory")


def _ensure_session_exists(user_id: str, session_id: str) -> Path:
    validate_id(session_id, "session_id")
    session_dir = _get_session_dir(user_id, session_id)
    if not Path(as_system_path(session_dir)).exists():
        raise HTTPException(status_code=404, detail="会话不存在")
    return session_dir


def _resolve_workspace_context(
    *,
    user_id: str,
    session_id: str | None,
    workspace_id: str | None,
    required: bool,
):
    if workspace_id is not None:
        validate_id(workspace_id, "workspace_id")
    registry = _get_workspace_registry()
    normalized_workspace_id = str(workspace_id or "").strip() or None
    bound_workspace_id: str | None = None

    if session_id:
        _ensure_session_exists(user_id, session_id)
        bound_workspace_id = registry.find_workspace_id_by_session_id(user_id, session_id)

    if (
        normalized_workspace_id
        and bound_workspace_id
        and normalized_workspace_id != bound_workspace_id
    ):
        raise HTTPException(
            status_code=400,
            detail="workspace_id 与 session 绑定的工作区不一致",
        )

    resolved_workspace_id = normalized_workspace_id or bound_workspace_id
    if resolved_workspace_id is None:
        if required:
            raise HTTPException(
                status_code=400,
                detail="workspace scope 必须提供 workspace_id 或绑定到工作区的 session_id",
            )
        return None, None

    try:
        workspace_root = registry.get_workspace_root(user_id, resolved_workspace_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="工作区不存在") from exc

    return resolved_workspace_id, workspace_root


@router.post("/resolve", response_model=ResolveMemoryResponse)
async def resolve_memory(
    request: ResolveMemoryRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> ResolveMemoryResponse:
    _ensure_user_access(current_user, request.user_id)
    session_dir = _ensure_session_exists(request.user_id, request.session_id)
    resolved_workspace_id, workspace_root = _resolve_workspace_context(
        user_id=request.user_id,
        session_id=request.session_id,
        workspace_id=request.workspace_id,
        required=False,
    )

    preview = MemoryResolver(
        session_dir=session_dir,
        user_id=request.user_id,
        session_id=request.session_id,
        user_store=MemoryStore(get_user_memory_file_path(session_dir.parent)),
        workspace_id=resolved_workspace_id,
        workspace_store=(
            MemoryStore(get_workspace_memory_file_path(workspace_root))
            if workspace_root is not None
            else None
        ),
        include_user_default_memory=request.include_user_default_memory,
        include_workspace_memory=request.include_workspace_memory,
    ).resolve_preview()
    state = read_runtime_config_state(session_dir)

    current_version = preview.snapshot_hash if preview.rendered_markdown.strip() else None
    current_hash = preview.snapshot_hash if preview.rendered_markdown.strip() else None
    applied_version = state.get("applied_memory_snapshot_version")
    applied_hash = state.get("applied_memory_snapshot_hash")
    pending_version = current_version if current_version != applied_version else None
    pending_hash = current_hash if current_hash != applied_hash else None

    return ResolveMemoryResponse(
        version=preview.version,
        snapshot_hash=preview.snapshot_hash,
        rendered_markdown=preview.rendered_markdown,
        current_memory_snapshot_version=current_version,
        current_memory_snapshot_hash=current_hash,
        applied_memory_snapshot_version=applied_version,
        applied_memory_snapshot_hash=applied_hash,
        pending_memory_snapshot_version=pending_version,
        pending_memory_snapshot_hash=pending_hash,
    )


@router.post("/summary/refresh", response_model=MemorySummaryResponse)
async def refresh_memory_summary(
    request: RegenerateMemorySummaryRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """读取当前 memory summary 内容。

    注意：当前实现仅做读取，不触发 summary 再生。
    如需重新生成 summary，请调用 consolidation 接口。
    """
    _ensure_user_access(current_user, request.user_id)
    user_dir = _get_user_dir(request.user_id)

    summary_path = _get_memory_summary_path_if_exists(user_dir)

    if summary_path is None:
        raise HTTPException(status_code=404, detail="无可用 memory summary")

    content = Path(as_system_path(summary_path)).read_text(encoding="utf-8")
    return {"content": content}


@router.get("/status", response_model=MemoryPipelineStatusResponse)
async def get_memory_pipeline_status(
    user_id: str,
    scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
    current_user: UserInfo = Depends(require_auth()),
) -> MemoryPipelineStatusResponse:
    """读取 memory pipeline 的轻量状态摘要。"""
    _ensure_user_access(current_user, user_id)
    scope_key = normalize_memory_scope_key(scope_key)
    memory_root = get_user_global_memory_dir(user_id)
    runtime = get_memory_state_runtime(user_id=user_id)
    payload = runtime.get_pipeline_status(user_id=user_id, scope_key=scope_key)
    return MemoryPipelineStatusResponse(
        **payload,
        state_db_path=str(memory_root / STATE_DB_FILE_NAME),
        memory_root_path=str(memory_root),
    )


@router.get("/citations")
async def get_memory_citations(
    current_user: UserInfo = Depends(require_auth()),
) -> dict:
    """读取 memory citation 统计。"""
    runtime = get_memory_state_runtime(user_id=current_user.user_id)
    stats = runtime.get_citation_stats(user_id=current_user.user_id)
    return {"citations": stats}


class MemoryCapacityResponse(BaseModel):
    status: str
    memory: dict
    summary: dict
    workspace: dict


@router.get("/capacity", response_model=MemoryCapacityResponse)
async def get_memory_capacity(
    user_id: str,
    session_id: str | None = None,
    workspace_id: str | None = None,
    current_user: UserInfo = Depends(require_auth()),
) -> MemoryCapacityResponse:
    """读取 memory 容量状态。"""
    _ensure_user_access(current_user, user_id)
    service = MemoryPipelineService(user_id=user_id)
    _resolved_workspace_id, workspace_root = _resolve_workspace_context(
        user_id=user_id,
        session_id=session_id,
        workspace_id=workspace_id,
        required=False,
    )
    info = service.check_capacity(
        user_id=user_id,
        workspace_root=workspace_root,
    )
    return MemoryCapacityResponse(**info)


class ConsolidateRequest(BaseModel):
    user_id: str
    force: bool = False


@router.post("/consolidate")
async def trigger_consolidation(
    request: ConsolidateRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> dict:
    """手动触发 memory consolidation。"""
    _ensure_user_access(current_user, request.user_id)
    service = MemoryPipelineService(user_id=request.user_id)
    count = await service.run_stage2_consolidation(
        user_id=request.user_id,
        force_consolidation=request.force,
    )
    return {"success": True, "consolidated_count": count}


@router.post("/retention", response_model=MemoryRetentionResponse)
async def apply_memory_retention(
    request: MemoryRetentionRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> MemoryRetentionResponse:
    """手动执行 memory 中间产物保留清理。"""
    _ensure_user_access(current_user, request.user_id)
    result = MemoryPipelineService(user_id=request.user_id).apply_retention(
        user_id=request.user_id,
        keep_latest=request.keep_latest,
        max_age_days=request.max_age_days,
    )
    return MemoryRetentionResponse(**result)


# ============ Workspace Memory 原始内容读写 ============


class WorkspaceMemoryContentResponse(BaseModel):
    content: str = Field(..., description="workspace_memory.md 原始内容")
    workspace_id: str = Field(..., description="工作区 ID")


class WorkspaceMemoryContentUpdateRequest(BaseModel):
    content: str = Field(..., description="新的 Markdown 内容")


@router.get("/workspace/content", response_model=WorkspaceMemoryContentResponse)
async def get_workspace_memory_content(
    user_id: str,
    session_id: str | None = None,
    workspace_id: str | None = None,
    current_user: UserInfo = Depends(require_auth()),
):
    """读取工作区 memory 原始 Markdown 内容。"""
    _ensure_user_access(current_user, user_id)
    resolved_workspace_id, workspace_root = _resolve_workspace_context(
        user_id=user_id,
        session_id=session_id,
        workspace_id=workspace_id,
        required=True,
    )
    assert workspace_root is not None
    memory_path = get_workspace_memory_file_path(workspace_root)
    sys_memory_path = Path(as_system_path(memory_path))
    content = sys_memory_path.read_text(encoding="utf-8") if sys_memory_path.exists() else ""
    return WorkspaceMemoryContentResponse(
        content=content,
        workspace_id=resolved_workspace_id,
    )


@router.put("/workspace/content")
async def update_workspace_memory_content(
    user_id: str,
    request: WorkspaceMemoryContentUpdateRequest,
    session_id: str | None = None,
    workspace_id: str | None = None,
    current_user: UserInfo = Depends(require_auth()),
):
    """保存工作区 memory 原始 Markdown 内容。"""
    _ensure_user_access(current_user, user_id)
    _resolved_workspace_id, workspace_root = _resolve_workspace_context(
        user_id=user_id,
        session_id=session_id,
        workspace_id=workspace_id,
        required=True,
    )
    assert workspace_root is not None
    memory_path = get_workspace_memory_file_path(workspace_root)
    from app.services.memory.pipeline import _get_memory_config

    config = _get_memory_config(user_id)
    max_size = config.max_workspace_memory_size or MAX_WORKSPACE_MEMORY_SIZE
    MemoryStore(memory_path).write_text(request.content, max_size=max_size)
    invalidate_user_resolver_cache(user_id)
    return {"success": True, "message": "工作区记忆已保存"}


# ============ Memory Versions（历史版本管理）============


@router.get("/versions", response_model=MemoryVersionListResponse)
async def list_memory_versions(
    user_id: str,
    scope_key: str = USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
    current_user: UserInfo = Depends(require_auth()),
):
    """列出版本历史（不含完整内容）。"""
    _ensure_user_access(current_user, user_id)
    scope_key = normalize_memory_scope_key(scope_key)
    runtime = get_memory_state_runtime(user_id=user_id)
    versions = runtime.list_versions(user_id=user_id, scope_key=scope_key)
    return MemoryVersionListResponse(
        versions=[
            MemoryVersionItem(
                id=v["id"],
                version_type=v["version_type"],
                source=v["source"],
                created_at=v["created_at"],
                summary=v["summary"],
            )
            for v in versions
        ]
    )


@router.get("/versions/{version_id}", response_model=MemoryVersionDetailResponse)
async def get_memory_version(
    version_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """读取单个版本的完整内容。"""
    runtime = get_memory_state_runtime(user_id=current_user.user_id)
    version = runtime.get_version(version_id=version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    _ensure_user_access(current_user, version["user_id"])
    return MemoryVersionDetailResponse(**version)


@router.post("/versions/{version_id}/restore", response_model=RestoreMemoryVersionResponse)
async def restore_memory_version(
    version_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """回滚到指定版本（获取 Stage 2 lease 防止竞态，同步更新 hash）。"""
    runtime = get_memory_state_runtime(user_id=current_user.user_id)
    version = runtime.get_version(version_id=version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    _ensure_user_access(current_user, version["user_id"])

    user_id = version["user_id"]
    scope_key = normalize_memory_scope_key(version["scope_key"])

    # 拒绝空内容版本恢复
    if not version["memory_content"].strip():
        raise HTTPException(status_code=400, detail="该版本内容为空，无法恢复")

    # 获取 Stage 2 lease，防止与正在运行的 consolidation 竞争写入
    claim = runtime.claim_stage2_job(
        user_id=user_id,
        scope_key=scope_key,
        lease_seconds=60,
    )
    if claim.status != "claimed":
        raise HTTPException(
            status_code=409,
            detail="Memory consolidation 正在运行，请稍后再试",
        )

    try:
        try:
            # 写回文件，必须经过 MemoryStore 安全扫描和容量限制。
            if is_user_default_global_workspace_scope(scope_key):
                from app.services.memory.layout import ensure_memory_layout

                layout = ensure_memory_layout(get_user_global_memory_dir(user_id))
                MemoryStore(layout.memory).write_text(
                    version["memory_content"],
                    max_size=MAX_MEMORY_SIZE,
                )
                if version.get("summary_content"):
                    MemoryStore(layout.summary).write_text(
                        version["summary_content"],
                        max_size=MAX_SUMMARY_SIZE,
                    )
            else:
                # workspace scope
                from app.services.workspace_registry import WorkspaceRegistryService

                registry = WorkspaceRegistryService(Path(WORKSPACE_DIR))
                workspace_root = registry.get_workspace_root(user_id, scope_key)
                memory_path = get_workspace_memory_file_path(workspace_root)
                MemoryStore(memory_path).write_text(
                    version["memory_content"],
                    max_size=MAX_WORKSPACE_MEMORY_SIZE,
                )
                if version.get("summary_content"):
                    summary_path = get_workspace_memory_summary_file_path(workspace_root)
                    MemoryStore(summary_path).write_text(
                        version["summary_content"],
                        max_size=MAX_SUMMARY_SIZE,
                    )
        except (MemorySecurityError, MemoryCapacityError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        # 同步更新 consolidation hash，保持 watermark 不变
        status = runtime.get_pipeline_status(user_id=user_id, scope_key=scope_key)
        current_watermark = 0
        if status.get("stage2", {}).get("consolidation"):
            current_watermark = status["stage2"]["consolidation"].get("input_watermark", 0)

        from app.services.memory.pipeline import _content_hash

        memory_hash = _content_hash(version["memory_content"])
        summary_hash = (
            _content_hash(version["summary_content"]) if version.get("summary_content") else None
        )

        runtime.update_consolidation_state(
            user_id=user_id,
            scope_key=scope_key,
            input_watermark=current_watermark,
            output_memory_hash=memory_hash,
            output_summary_hash=summary_hash,
        )
        invalidate_user_resolver_cache(user_id)
    finally:
        runtime.complete_stage2_job(user_id=user_id, scope_key=scope_key)

    return RestoreMemoryVersionResponse(
        success=True,
        version_id=version_id,
        restored_scope_key=scope_key,
    )
