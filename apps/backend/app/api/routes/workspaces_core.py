import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.api.routes.workspaces_overview_utils import (
    _build_workspace_overview,
    _build_workspace_resource_layer_summary,
)
from app.api.routes.workspaces_runtime_utils import _wait_for_session_stop
from app.core.auth import require_auth
from app.models.expert import (
    CreateExpertRequest,
    EnableBuiltinExpertRequest,
    ExpertDetailResponse,
    GlobalCollaborationPolicyResponse,
    GlobalExpertCatalogResponse,
    SubAgentVisibilityPolicyResponse,
    UpdateExpertRequest,
    UpdateSubAgentVisibilityRequest,
    UpdateWorkspaceCollaborationPolicyRequest,
    WorkspaceCollaborationPolicyResponse,
    WorkspaceExpertCatalogResponse,
)
from app.models.llm_selection import (
    UpdateScopedModelSelectionRequest,
    WorkspaceLLMSelectionResponse,
)
from app.models.session import ExecutionRecord
from app.models.user import UserInfo
from app.models.workspace import (
    ConversationListResponse,
    ConversationRunsResponse,
    CreateConversationRequest,
    CreateWorkspaceRequest,
    DeleteWorkspaceResponse,
    FolderImportPreviewRequest,
    FolderImportPreviewResponse,
    FolderImportTreeItem,
    OrphanConversationCleanupResponse,
    UpdateWorkspaceRequest,
    WorkspaceConversationSummary,
    WorkspaceDetailResponse,
    WorkspaceListResponse,
    WorkspaceOverviewResponse,
    WorkspaceResourceLayerSummaryResponse,
)
from app.services.expert_roles import (
    get_global_collaboration_policy,
    get_global_expert_catalog,
    get_workspace_collaboration_policy,
    get_workspace_expert_catalog,
)
from app.services.folder_import import scan_folder
from app.services.llm.model_selection_service import get_model_selection_service
from app.services.workspace_registry import get_workspace_registry_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


global_experts_router = APIRouter(prefix="/experts/global", tags=["experts"])


@global_experts_router.get("", response_model=GlobalExpertCatalogResponse)
async def get_global_experts(
    current_user: UserInfo = Depends(require_auth()),
):
    return get_global_expert_catalog(user_id=current_user.user_id)


@global_experts_router.get(
    "/policy",
    response_model=GlobalCollaborationPolicyResponse,
)
async def get_global_expert_policy(
    current_user: UserInfo = Depends(require_auth()),
):
    return get_global_collaboration_policy(user_id=current_user.user_id)


@global_experts_router.put(
    "/policy",
    response_model=GlobalCollaborationPolicyResponse,
)
async def update_global_expert_policy(
    request: UpdateWorkspaceCollaborationPolicyRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    from app.api.routes.sessions_helpers import (
        _normalize_requested_expert_role_ids,
        _normalize_requested_expert_role_tool_ids,
    )
    from app.services.agent.subagent_catalog import (
        enable_builtin_subagent_to_scope,
        is_system_subagent_name,
        save_global_collaboration_policy,
    )

    current_policy = get_global_collaboration_policy(user_id=current_user.user_id)
    selectable_roles = [role for role in current_policy.available_roles if role.host_selectable]
    available_role_ids = [role.role_id for role in selectable_roles]
    available_role_tool_ids = {role.role_id: list(role.tool_ids) for role in selectable_roles}
    normalized_role_ids = _normalize_requested_expert_role_ids(
        request.enabled_role_ids,
        available_role_ids,
    )
    normalized_role_tool_ids = _normalize_requested_expert_role_tool_ids(
        request.role_tool_ids,
        available_role_tool_ids,
    )
    if normalized_role_ids is not None:
        for role_id in normalized_role_ids:
            if is_system_subagent_name(role_id):
                enable_builtin_subagent_to_scope(
                    user_id=current_user.user_id,
                    name=role_id,
                    scope="global",
                )

    save_global_collaboration_policy(
        user_id=current_user.user_id,
        enabled_role_ids=normalized_role_ids,
        available_role_ids=available_role_ids,
        reset_enabled=request.enabled_role_ids is None,
        role_tool_ids=normalized_role_tool_ids,
        runtime_policy=(
            request.collaboration_policy.model_dump(mode="json")
            if request.collaboration_policy is not None
            else None
        ),
    )

    return get_global_collaboration_policy(user_id=current_user.user_id)


@global_experts_router.post("/{name}/enable", response_model=ExpertDetailResponse)
async def enable_global_builtin_expert(
    name: str,
    request: EnableBuiltinExpertRequest | None = None,
    current_user: UserInfo = Depends(require_auth()),
):
    """将系统提供的协作专家安装到我的默认。"""
    from app.services.agent.subagent_catalog import (
        enable_builtin_subagent_to_scope,
        load_subagent,
    )

    role_id = (request.role_id if request is not None else name).strip()
    if role_id != name:
        raise HTTPException(status_code=400, detail="role_id 与路径参数不一致")

    try:
        enable_builtin_subagent_to_scope(
            user_id=current_user.user_id,
            name=name,
            scope="global",
        )
        manifest = load_subagent(
            user_id=current_user.user_id,
            name=name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("安装我的默认协作专家失败: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to install expert") from exc

    if manifest is None:
        raise HTTPException(status_code=404, detail="Expert not found")

    return ExpertDetailResponse(
        name=name,
        description=manifest.get("description", ""),
        system_prompt=manifest.get("system_prompt", ""),
        model=manifest.get("model"),
        tools=manifest.get("tools"),
        scope="global",
        source=str(manifest.get("_source") or manifest.get("source") or "builtin"),
    )


@global_experts_router.post("", response_model=ExpertDetailResponse)
async def create_global_expert(
    request: CreateExpertRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """在用户默认层创建自定义协作专家。"""
    from app.services.agent.subagent_catalog import (
        is_system_subagent_name,
        is_valid_subagent_name,
        save_subagent,
    )

    name = request.name.strip()
    if not is_valid_subagent_name(name):
        raise HTTPException(
            status_code=400,
            detail="协作专家名称格式无效。要求：英文字母开头，仅包含字母、数字、下划线、连字符，长度不超过64。",
        )
    if is_system_subagent_name(name):
        raise HTTPException(
            status_code=400,
            detail="Expert name conflicts with system preset roles",
        )
    if request.scope != "global":
        raise HTTPException(
            status_code=400,
            detail="我的默认创建接口只支持 global 作用域。",
        )

    manifest: dict[str, Any] = {
        "name": name,
        "description": request.description.strip(),
        "system_prompt": request.system_prompt.strip(),
    }
    if request.model:
        manifest["model"] = request.model.strip()
    if request.tools:
        manifest["tools"] = [item.strip() for item in request.tools if item]

    response_description = manifest["description"]
    response_system_prompt = manifest["system_prompt"]
    response_model = manifest.get("model")
    response_tools = manifest.get("tools")

    try:
        save_subagent(
            user_id=current_user.user_id,
            name=name,
            manifest=manifest,
            scope="global",
        )
    except Exception as exc:
        logger.error("创建我的默认协作专家失败: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save expert config") from exc

    return ExpertDetailResponse(
        name=name,
        description=response_description,
        system_prompt=response_system_prompt,
        model=response_model,
        tools=response_tools,
        scope="global",
        source="custom",
    )


@global_experts_router.get("/{name}", response_model=ExpertDetailResponse)
async def get_global_expert_detail(
    name: str,
    current_user: UserInfo = Depends(require_auth()),
):
    from app.services.agent.subagent_catalog import (
        _get_global_dir,
        _load_global_subagent_from_code,
        _load_subagent_from_db,
        _parse_subagent_file,
    )

    manifest = _load_subagent_from_db(
        user_id=current_user.user_id,
        name=name,
        scope="global",
    )
    if manifest is None:
        toml_path = _get_global_dir(current_user.user_id) / f"{name}.toml"
        if toml_path.exists():
            manifest = _parse_subagent_file(toml_path)
    if manifest is None:
        manifest = _load_global_subagent_from_code(name)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Expert not found")

    return ExpertDetailResponse(
        name=name,
        description=manifest.get("description", ""),
        system_prompt=manifest.get("system_prompt", ""),
        model=manifest.get("model"),
        tools=manifest.get("tools"),
        scope="global",
        source=str(manifest.get("_source") or manifest.get("source") or "custom"),
    )


@global_experts_router.put(
    "/{name}/visibility",
    response_model=SubAgentVisibilityPolicyResponse,
)
async def update_global_expert_visibility(
    name: str,
    request: UpdateSubAgentVisibilityRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """更新用户默认层协作专家可见性策略。"""
    from app.services.agent.subagent_catalog import (
        resolve_subagent_visibility_policy,
        save_subagent_visibility_policy,
    )

    catalog = get_global_expert_catalog(user_id=current_user.user_id)
    if name not in {role.role_id for role in catalog.roles}:
        raise HTTPException(status_code=404, detail="Expert not found")

    try:
        save_subagent_visibility_policy(
            user_id=current_user.user_id,
            role_id=name,
            scope="global",
            catalog_visible=request.catalog_visible,
            host_selectable=request.host_selectable,
            default_enabled=request.default_enabled,
            lock_reason=request.lock_reason,
        )
        effective_policy = resolve_subagent_visibility_policy(
            user_id=current_user.user_id,
            role_id=name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("更新我的默认协作专家可见性失败: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save expert visibility") from exc

    return SubAgentVisibilityPolicyResponse(
        role_id=name,
        scope="global",
        workspace_id=None,
        catalog_visible=effective_policy.catalog_visible,
        host_selectable=effective_policy.host_selectable,
        default_enabled=effective_policy.default_enabled,
        visibility_source=effective_policy.visibility_source,
        lock_reason=effective_policy.lock_reason,
        policy=effective_policy,
    )


@global_experts_router.put("/{name}", response_model=ExpertDetailResponse)
async def update_global_expert(
    name: str,
    request: UpdateExpertRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """更新用户默认层自定义协作专家。"""
    from app.services.agent.subagent_catalog import (
        _get_global_dir,
        _load_subagent_from_db,
        _parse_subagent_file,
        is_system_subagent_name,
        save_subagent,
    )

    if is_system_subagent_name(name):
        raise HTTPException(status_code=403, detail="系统预设角色不允许修改")

    existing = _load_subagent_from_db(
        user_id=current_user.user_id,
        name=name,
        scope="global",
    )
    if existing is None:
        toml_path = _get_global_dir(current_user.user_id) / f"{name}.toml"
        if toml_path.exists():
            existing = _parse_subagent_file(toml_path)
    if existing is None:
        raise HTTPException(status_code=404, detail="Expert not found")
    if existing.get("_source") == "system" or existing.get("source") == "system":
        raise HTTPException(status_code=403, detail="系统预设角色不允许修改")

    manifest: dict[str, Any] = {
        "name": name,
        "description": existing.get("description", ""),
        "system_prompt": existing.get("system_prompt", ""),
    }
    if existing.get("model"):
        manifest["model"] = existing["model"]
    if existing.get("tools"):
        manifest["tools"] = list(existing["tools"])

    if request.description is not None:
        manifest["description"] = request.description.strip()
    if request.system_prompt is not None:
        manifest["system_prompt"] = request.system_prompt.strip()
    if request.model is not None:
        if request.model.strip():
            manifest["model"] = request.model.strip()
        else:
            manifest.pop("model", None)
    if request.tools is not None:
        if request.tools:
            manifest["tools"] = [item.strip() for item in request.tools if item]
        else:
            manifest.pop("tools", None)

    response_description = manifest["description"]
    response_system_prompt = manifest["system_prompt"]
    response_model = manifest.get("model")
    response_tools = manifest.get("tools")

    try:
        save_subagent(
            user_id=current_user.user_id,
            name=name,
            manifest=manifest,
            scope="global",
        )
    except Exception as exc:
        logger.error("更新我的默认协作专家失败: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save expert config") from exc

    return ExpertDetailResponse(
        name=name,
        description=response_description,
        system_prompt=response_system_prompt,
        model=response_model,
        tools=response_tools,
        scope="global",
        source="custom",
    )


@global_experts_router.delete("/{name}")
async def delete_global_expert(
    name: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """删除用户默认层协作专家副本。系统内置源目录不会被删除。"""
    from app.services.agent.subagent_catalog import (
        delete_subagent,
    )

    deleted = delete_subagent(
        user_id=current_user.user_id,
        name=name,
        scope="global",
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Expert not found")

    return {"success": True, "name": name}


@router.get("", response_model=WorkspaceListResponse)
async def list_workspaces(
    summary_only: bool = Query(True, description="仅返回摘要信息，不读取每个对话的详细元数据"),
    limit: int | None = Query(None, ge=1, description="限制返回数量，为空时返回全部"),
    offset: int = Query(0, ge=0, description="跳过前 N 条"),
    current_user: UserInfo = Depends(require_auth()),
):
    def _unwrap_query(val: Any) -> Any:
        return val.default if hasattr(val, "default") else val

    service = get_workspace_registry_service()
    # 先获取总数（不带分页限制），再获取分页数据
    all_workspaces = service.list_workspaces(
        current_user.user_id,
        include_conversations=False,
        summary_only=True,
    )
    total_count = len(all_workspaces)
    workspaces = service.list_workspaces(
        current_user.user_id,
        include_conversations=False,
        summary_only=summary_only,
        limit=_unwrap_query(limit),
        offset=_unwrap_query(offset),
    )
    return WorkspaceListResponse(workspaces=workspaces, total=total_count)


@router.post("", response_model=WorkspaceDetailResponse)
async def create_workspace(
    request: CreateWorkspaceRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    service = get_workspace_registry_service()
    try:
        workspace = service.create_workspace(
            user_id=current_user.user_id,
            workspace_id=request.workspace_id,
            title=request.title,
            description=request.description,
            workspace_kind=request.workspace_kind,
            execution_policy=request.execution_policy,
            initial_conversation_id=request.initial_conversation_id,
            initial_conversation_title=request.initial_conversation_title,
            recovery_policy=request.recovery_policy,
            code_timeout=request.code_timeout,
            runtime_binding=request.runtime_binding,
            template_id=request.template_id,
            install_capabilities=request.install_capabilities,
            template_files=request.template_files,
            source_folder_path=request.source_folder_path,
            temp_upload_id=request.temp_upload_id,
            import_files=request.import_files,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Operation failed: {exc}") from exc

    return workspace


@router.post("/import-folder-upload")
async def upload_import_folder(
    files: list[UploadFile] = File(...),
    current_user: UserInfo = Depends(require_auth()),
):
    """Web 版上传要导入的文件夹文件，返回临时 upload_id。"""
    from app.services.folder_import import (
        MAX_UPLOAD_FILE_SIZE_BYTES,
        MAX_UPLOAD_TOTAL_SIZE_BYTES,
        create_import_upload_dir,
    )

    if not files:
        raise HTTPException(status_code=400, detail="没有上传文件")

    total_size = 0
    for upload_file in files:
        if not upload_file.filename:
            continue
        if upload_file.size is not None and upload_file.size > MAX_UPLOAD_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"单文件大小超过限制: {upload_file.filename}",
            )
        if upload_file.size is not None:
            total_size += upload_file.size

    if total_size > MAX_UPLOAD_TOTAL_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="上传文件总大小超过 1GB 限制")

    upload_id, upload_dir = create_import_upload_dir()
    try:
        for upload_file in files:
            if not upload_file.filename:
                continue
            target_path = upload_dir / upload_file.filename
            target_path.parent.mkdir(parents=True, exist_ok=True)
            content = await upload_file.read()
            if len(content) > MAX_UPLOAD_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"单文件大小超过限制: {upload_file.filename}",
                )
            target_path.write_bytes(content)
    except HTTPException:
        from app.services.folder_import import remove_import_upload_dir

        remove_import_upload_dir(upload_id)
        raise

    return {"upload_id": upload_id, "file_count": len(files)}


@router.post("/import-folder-preview", response_model=FolderImportPreviewResponse)
async def preview_import_folder(
    request: FolderImportPreviewRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """扫描本地文件夹并返回文件树，用于导入前预览。"""
    source_path_str = request.source_path
    if not source_path_str:
        raise HTTPException(status_code=400, detail="缺少 source_path")

    source_path = Path(source_path_str).expanduser().resolve()
    try:
        preview = scan_folder(source_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"扫描文件夹失败: {exc}") from exc

    return FolderImportPreviewResponse(
        source_path=str(preview.source_path),
        files=[
            FolderImportTreeItem(
                relative_path=f.relative_path,
                is_directory=f.is_directory,
                size=f.size,
            )
            for f in preview.files
        ],
        excluded_files=preview.excluded_files,
        default_selected_files=preview.default_selected_files,
        total_file_count=preview.total_file_count,
        total_size_bytes=preview.total_size_bytes,
    )


@router.post("/import-folder-stream")
async def import_folder_stream(
    request: CreateWorkspaceRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """从本地文件夹导入并创建工作区，通过 SSE 实时返回进度。"""
    if not request.source_folder_path and not request.temp_upload_id:
        raise HTTPException(status_code=400, detail="缺少 source_folder_path 或 temp_upload_id")

    service = get_workspace_registry_service()

    async def event_generator():
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        done_event = asyncio.Event()
        workspace_result: list[WorkspaceDetailResponse] = []
        workspace_error: list[BaseException] = []

        def progress_callback(progress: int, message: str) -> None:
            try:
                queue.put_nowait(
                    {
                        "stage": "copying" if progress < 95 else "creating_workspace",
                        "progress": progress,
                        "message": message,
                    }
                )
            except asyncio.QueueFull:
                pass

        def run_create_workspace() -> None:
            try:
                workspace = service.create_workspace(
                    user_id=current_user.user_id,
                    workspace_id=request.workspace_id,
                    title=request.title,
                    description=request.description,
                    workspace_kind=request.workspace_kind,
                    execution_policy=request.execution_policy,
                    initial_conversation_id=request.initial_conversation_id,
                    initial_conversation_title=request.initial_conversation_title,
                    recovery_policy=request.recovery_policy,
                    code_timeout=request.code_timeout,
                    runtime_binding=request.runtime_binding,
                    template_id=request.template_id,
                    install_capabilities=request.install_capabilities,
                    template_files=request.template_files,
                    source_folder_path=request.source_folder_path,
                    temp_upload_id=request.temp_upload_id,
                    import_files=request.import_files,
                    progress_callback=progress_callback,
                )
                workspace_result.append(workspace)
            except BaseException as exc:  # noqa: BLE001
                workspace_error.append(exc)
            finally:
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass
                done_event.set()

        # 发送初始扫描事件
        yield f"data: {json.dumps({'stage': 'scanning', 'progress': 0, 'message': '正在扫描文件夹...'})}\n\n"

        # 在后台线程运行创建任务
        asyncio.get_event_loop().run_in_executor(None, run_create_workspace)

        # 并发读取进度队列
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                if done_event.is_set() and queue.empty():
                    break
                continue

            if event is None:
                break

            yield f"data: {json.dumps(event)}\n\n"

        if workspace_error:
            exc = workspace_error[0]
            if isinstance(exc, ValueError):
                yield f"data: {json.dumps({'stage': 'error', 'message': f'创建工作区失败: {exc}'})}\n\n"
            else:
                logger.exception("导入文件夹创建 workspace 失败")
                yield f"data: {json.dumps({'stage': 'error', 'message': f'导入失败: {exc}'})}\n\n"
        elif workspace_result:
            workspace = workspace_result[0]
            yield f"data: {json.dumps({'stage': 'completed', 'progress': 100, 'message': '工作区创建完成', 'workspace_id': workspace.workspace_id, 'warnings': workspace.warnings})}\n\n"
        else:
            yield f"data: {json.dumps({'stage': 'error', 'message': '导入失败: 未知错误'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{workspace_id}", response_model=WorkspaceDetailResponse)
async def get_workspace(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    service = get_workspace_registry_service()
    try:
        return service.get_workspace(
            current_user.user_id,
            workspace_id,
            include_conversations=True,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc


@router.get("/{workspace_id}/overview", response_model=WorkspaceOverviewResponse)
async def get_workspace_overview(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    service = get_workspace_registry_service()
    try:
        return await _build_workspace_overview(
            service=service,
            user_id=current_user.user_id,
            workspace_id=workspace_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc


@router.get(
    "/{workspace_id}/resource-layers",
    response_model=WorkspaceResourceLayerSummaryResponse,
)
async def get_workspace_resource_layers(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    service = get_workspace_registry_service()
    try:
        return await _build_workspace_resource_layer_summary(
            service=service,
            user_id=current_user.user_id,
            workspace_id=workspace_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc


@router.get(
    "/{workspace_id}/experts",
    response_model=WorkspaceExpertCatalogResponse,
)
async def get_workspace_experts(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    try:
        return get_workspace_expert_catalog(
            user_id=current_user.user_id,
            workspace_id=workspace_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc


@router.get(
    "/{workspace_id}/experts/policy",
    response_model=WorkspaceCollaborationPolicyResponse,
)
async def get_workspace_expert_policy(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """获取工作区级协作专家启用策略。"""
    service = get_workspace_registry_service()
    try:
        service.get_workspace(
            current_user.user_id,
            workspace_id,
            include_conversations=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    return get_workspace_collaboration_policy(
        user_id=current_user.user_id,
        workspace_id=workspace_id,
    )


@router.put(
    "/{workspace_id}/experts/policy",
    response_model=WorkspaceCollaborationPolicyResponse,
)
async def update_workspace_expert_policy(
    workspace_id: str,
    request: UpdateWorkspaceCollaborationPolicyRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """更新工作区级协作专家启用策略。"""
    from app.api.routes.sessions_helpers import (
        _normalize_requested_expert_role_ids,
        _normalize_requested_expert_role_tool_ids,
    )
    from app.services.agent.subagent_catalog import (
        enable_builtin_subagent_to_scope,
        is_system_subagent_name,
        save_workspace_collaboration_policy,
    )

    service = get_workspace_registry_service()
    try:
        service.get_workspace(
            current_user.user_id,
            workspace_id,
            include_conversations=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    current_policy = get_workspace_collaboration_policy(
        user_id=current_user.user_id,
        workspace_id=workspace_id,
    )
    selectable_roles = [role for role in current_policy.available_roles if role.host_selectable]
    available_role_ids = [role.role_id for role in selectable_roles]
    available_role_tool_ids = {role.role_id: list(role.tool_ids) for role in selectable_roles}
    normalized_role_ids = _normalize_requested_expert_role_ids(
        request.enabled_role_ids,
        available_role_ids,
    )
    normalized_role_tool_ids = _normalize_requested_expert_role_tool_ids(
        request.role_tool_ids,
        available_role_tool_ids,
    )
    if normalized_role_ids is not None:
        for role_id in normalized_role_ids:
            if is_system_subagent_name(role_id):
                enable_builtin_subagent_to_scope(
                    user_id=current_user.user_id,
                    name=role_id,
                    scope="workspace",
                    workspace_id=workspace_id,
                )

    save_workspace_collaboration_policy(
        user_id=current_user.user_id,
        workspace_id=workspace_id,
        enabled_role_ids=normalized_role_ids,
        available_role_ids=available_role_ids,
        reset_enabled=request.enabled_role_ids is None,
        role_tool_ids=normalized_role_tool_ids,
        runtime_policy=(
            request.collaboration_policy.model_dump(mode="json")
            if request.collaboration_policy is not None
            else None
        ),
    )

    return get_workspace_collaboration_policy(
        user_id=current_user.user_id,
        workspace_id=workspace_id,
    )


@router.post(
    "/{workspace_id}/experts/{name}/enable",
    response_model=ExpertDetailResponse,
)
async def enable_workspace_builtin_expert(
    workspace_id: str,
    name: str,
    request: EnableBuiltinExpertRequest | None = None,
    current_user: UserInfo = Depends(require_auth()),
):
    """将系统提供的协作专家安装到当前工作区。"""
    from app.services.agent.subagent_catalog import (
        enable_builtin_subagent_to_scope,
        load_subagent,
    )

    role_id = (request.role_id if request is not None else name).strip()
    if role_id != name:
        raise HTTPException(status_code=400, detail="role_id 与路径参数不一致")

    service = get_workspace_registry_service()
    try:
        service.get_workspace(
            current_user.user_id,
            workspace_id,
            include_conversations=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    try:
        enable_builtin_subagent_to_scope(
            user_id=current_user.user_id,
            name=name,
            scope="workspace",
            workspace_id=workspace_id,
        )
        manifest = load_subagent(
            user_id=current_user.user_id,
            name=name,
            workspace_id=workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("安装工作区协作专家失败: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to install expert") from exc

    if manifest is None:
        raise HTTPException(status_code=404, detail="Expert not found")

    return ExpertDetailResponse(
        name=name,
        description=manifest.get("description", ""),
        system_prompt=manifest.get("system_prompt", ""),
        model=manifest.get("model"),
        tools=manifest.get("tools"),
        scope="workspace",
        source=str(manifest.get("_source") or manifest.get("source") or "builtin"),
    )


@router.post("/{workspace_id}/experts", response_model=ExpertDetailResponse)
async def create_workspace_expert(
    workspace_id: str,
    request: CreateExpertRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """在工作区下创建自定义协作专家（子 Agent）。"""
    from app.services.agent.subagent_catalog import (
        is_system_subagent_name,
        is_valid_subagent_name,
        save_subagent,
    )

    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    name = request.name.strip()
    if not is_valid_subagent_name(name):
        raise HTTPException(
            status_code=400,
            detail="专家名称格式无效。要求：英文字母开头，仅包含字母、数字、下划线、连字符，长度不超过64。",
        )
    if is_system_subagent_name(name):
        raise HTTPException(
            status_code=400,
            detail="Expert name conflicts with system preset roles",
        )
    if request.scope != "workspace":
        raise HTTPException(
            status_code=400,
            detail="当前工作区创建接口只支持 workspace 作用域。",
        )

    manifest: dict[str, Any] = {
        "name": name,
        "description": request.description.strip(),
        "system_prompt": request.system_prompt.strip(),
    }
    if request.model:
        manifest["model"] = request.model.strip()
    if request.tools:
        manifest["tools"] = [t.strip() for t in request.tools if t]

    # 保存原始值用于响应（save_subagent 会 pop system_prompt）
    response_description = manifest["description"]
    response_system_prompt = manifest["system_prompt"]
    response_model = manifest.get("model")
    response_tools = manifest.get("tools")

    try:
        save_subagent(
            user_id=current_user.user_id,
            name=name,
            manifest=manifest,
            scope="workspace",
            workspace_id=workspace_id,
        )
    except Exception as exc:
        logger.error("创建工作区专家失败: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save expert config") from exc

    return ExpertDetailResponse(
        name=name,
        description=response_description,
        system_prompt=response_system_prompt,
        model=response_model,
        tools=response_tools,
        scope="workspace",
        source="custom",
    )


@router.get("/{workspace_id}/experts/{name}", response_model=ExpertDetailResponse)
async def get_workspace_expert_detail(
    workspace_id: str,
    name: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """获取工作区下自定义专家的完整详情（含 system_prompt）。"""
    from app.services.agent.subagent_catalog import load_subagent

    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    manifest = load_subagent(
        user_id=current_user.user_id,
        name=name,
        workspace_id=workspace_id,
    )
    if manifest is None:
        raise HTTPException(status_code=404, detail="Expert not found")

    return ExpertDetailResponse(
        name=name,
        description=manifest.get("description", ""),
        system_prompt=manifest.get("system_prompt", ""),
        model=manifest.get("model"),
        tools=manifest.get("tools"),
        scope="workspace",
        source="custom",
    )


@router.put(
    "/{workspace_id}/experts/{name}/visibility",
    response_model=SubAgentVisibilityPolicyResponse,
)
async def update_workspace_expert_visibility(
    workspace_id: str,
    name: str,
    request: UpdateSubAgentVisibilityRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """更新工作区级子 Agent 可见性策略。"""
    from app.services.agent.subagent_catalog import (
        resolve_subagent_visibility_policy,
        save_subagent_visibility_policy,
    )

    service = get_workspace_registry_service()
    try:
        service.get_workspace(
            current_user.user_id,
            workspace_id,
            include_conversations=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    catalog = get_workspace_expert_catalog(
        user_id=current_user.user_id,
        workspace_id=workspace_id,
    )
    if name not in {role.role_id for role in catalog.roles}:
        raise HTTPException(status_code=404, detail="Expert not found")

    try:
        save_subagent_visibility_policy(
            user_id=current_user.user_id,
            role_id=name,
            scope="workspace",
            workspace_id=workspace_id,
            catalog_visible=request.catalog_visible,
            host_selectable=request.host_selectable,
            default_enabled=request.default_enabled,
            lock_reason=request.lock_reason,
        )
        effective_policy = resolve_subagent_visibility_policy(
            user_id=current_user.user_id,
            role_id=name,
            workspace_id=workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("更新工作区专家可见性失败: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save expert visibility") from exc

    return SubAgentVisibilityPolicyResponse(
        role_id=name,
        scope="workspace",
        workspace_id=workspace_id,
        catalog_visible=effective_policy.catalog_visible,
        host_selectable=effective_policy.host_selectable,
        default_enabled=effective_policy.default_enabled,
        visibility_source=effective_policy.visibility_source,
        lock_reason=effective_policy.lock_reason,
        policy=effective_policy,
    )


@router.put("/{workspace_id}/experts/{name}", response_model=ExpertDetailResponse)
async def update_workspace_expert(
    workspace_id: str,
    name: str,
    request: UpdateExpertRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """更新工作区下自定义专家配置。"""
    from app.services.agent.subagent_catalog import (
        is_system_subagent_name,
        load_subagent,
        save_subagent,
    )

    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    # 系统预设不允许通过 REST 修改
    if is_system_subagent_name(name):
        raise HTTPException(status_code=403, detail="系统预设角色不允许修改")

    existing = load_subagent(
        user_id=current_user.user_id,
        name=name,
        workspace_id=workspace_id,
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="Expert not found")

    # 合并更新字段
    manifest: dict[str, Any] = {
        "name": name,
        "description": existing.get("description", ""),
        "system_prompt": existing.get("system_prompt", ""),
    }
    if existing.get("model"):
        manifest["model"] = existing["model"]
    if existing.get("tools"):
        manifest["tools"] = list(existing["tools"])

    if request.description is not None:
        manifest["description"] = request.description.strip()
    if request.system_prompt is not None:
        manifest["system_prompt"] = request.system_prompt.strip()
    if request.model is not None:
        if request.model.strip():
            manifest["model"] = request.model.strip()
        else:
            manifest.pop("model", None)
    if request.tools is not None:
        if request.tools:
            manifest["tools"] = [t.strip() for t in request.tools if t]
        else:
            manifest.pop("tools", None)

    # 保存原始值用于响应（save_subagent 会 pop system_prompt）
    response_description = manifest["description"]
    response_system_prompt = manifest["system_prompt"]
    response_model = manifest.get("model")
    response_tools = manifest.get("tools")

    try:
        save_subagent(
            user_id=current_user.user_id,
            name=name,
            manifest=manifest,
            scope="workspace",
            workspace_id=workspace_id,
        )
    except Exception as exc:
        logger.error("更新工作区专家失败: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save expert config") from exc

    return ExpertDetailResponse(
        name=name,
        description=response_description,
        system_prompt=response_system_prompt,
        model=response_model,
        tools=response_tools,
        scope="workspace",
        source="custom",
    )


@router.delete("/{workspace_id}/experts/{name}")
async def delete_workspace_expert(
    workspace_id: str,
    name: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """删除工作区下协作专家副本。系统内置源目录不会被删除。"""
    from app.services.agent.subagent_catalog import (
        delete_subagent,
    )

    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    deleted = delete_subagent(
        user_id=current_user.user_id,
        name=name,
        scope="workspace",
        workspace_id=workspace_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Expert not found")

    return {"success": True, "name": name}


@router.patch("/{workspace_id}", response_model=WorkspaceDetailResponse)
async def update_workspace(
    workspace_id: str,
    request: UpdateWorkspaceRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    service = get_workspace_registry_service()
    try:
        return service.update_workspace(
            user_id=current_user.user_id,
            workspace_id=workspace_id,
            title=request.title,
            description=request.description,
            execution_policy=request.execution_policy,
            runtime_binding=request.runtime_binding,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Operation failed") from exc


@router.get(
    "/{workspace_id}/llm-selection",
    response_model=WorkspaceLLMSelectionResponse,
)
async def get_workspace_llm_selection(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    service = get_workspace_registry_service()
    try:
        service.get_workspace(
            current_user.user_id,
            workspace_id,
            include_conversations=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    return get_model_selection_service().get_workspace_selection(
        user_id=current_user.user_id,
        workspace_id=workspace_id,
    )


@router.put(
    "/{workspace_id}/llm-selection",
    response_model=WorkspaceLLMSelectionResponse,
)
async def update_workspace_llm_selection(
    workspace_id: str,
    request: UpdateScopedModelSelectionRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    service = get_workspace_registry_service()
    try:
        service.get_workspace(
            current_user.user_id,
            workspace_id,
            include_conversations=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    try:
        return get_model_selection_service().update_workspace_model_selection(
            user_id=current_user.user_id,
            workspace_id=workspace_id,
            model_id=request.model_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Operation failed") from exc


@router.delete("/{workspace_id}", response_model=DeleteWorkspaceResponse)
async def delete_workspace(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    service = get_workspace_registry_service()
    try:
        workspace = service.get_workspace(
            current_user.user_id,
            workspace_id,
            include_conversations=True,
            include_hidden_conversations=True,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    session_ids: list[str] = []
    for conversation in workspace.conversations:
        session_id = conversation.session_id
        if session_id not in session_ids:
            session_ids.append(session_id)

    if workspace.current_conversation_id:
        try:
            current_session_id = service.resolve_session_id_for_conversation(
                user_id=current_user.user_id,
                workspace_id=workspace_id,
                conversation_id=workspace.current_conversation_id,
            )
        except FileNotFoundError:
            current_session_id = None
        if current_session_id and current_session_id not in session_ids:
            session_ids.append(current_session_id)

    if session_ids:
        from app.agents.tools.local_ipython_box import LocalIPythonBox
        from app.services.agent import agent_service

        for session_id in session_ids:
            try:
                await agent_service.stop_session(current_user.user_id, session_id)
            except Exception as stop_err:
                logger.warning(
                    "删除工作区前中断会话失败（继续）: workspace=%s session=%s error=%s",
                    workspace_id,
                    session_id,
                    stop_err,
                )

        for session_id in session_ids:
            stopped = await _wait_for_session_stop(
                current_user.user_id,
                session_id,
            )
            if not stopped:
                logger.warning(
                    "删除工作区前等待会话停稳超时，将继续清理目录: workspace=%s session=%s",
                    workspace_id,
                    session_id,
                )
            try:
                LocalIPythonBox.shutdown_kernel(session_id=session_id, user_id=current_user.user_id)
            except Exception as kernel_err:
                logger.warning(
                    "删除工作区前关闭本地运行态失败（继续）: workspace=%s session=%s error=%s",
                    workspace_id,
                    session_id,
                    kernel_err,
                )

    try:
        service.delete_workspace(current_user.user_id, workspace_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    return DeleteWorkspaceResponse(success=True, workspace_id=workspace_id)


@router.get(
    "/{workspace_id}/conversations",
    response_model=ConversationListResponse,
)
async def list_workspace_conversations(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    service = get_workspace_registry_service()
    try:
        conversations = service.list_conversations(current_user.user_id, workspace_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc
    return ConversationListResponse(
        workspace_id=workspace_id,
        conversations=conversations,
        total=len(conversations),
    )


@router.get(
    "/{workspace_id}/conversations/{conversation_id}",
    response_model=WorkspaceConversationSummary,
)
async def get_workspace_conversation(
    workspace_id: str,
    conversation_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    service = get_workspace_registry_service()
    try:
        return service.get_conversation(
            user_id=current_user.user_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc


@router.post(
    "/{workspace_id}/conversations",
    response_model=WorkspaceConversationSummary,
)
async def create_workspace_conversation(
    workspace_id: str,
    request: CreateConversationRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    service = get_workspace_registry_service()
    try:
        return service.create_conversation(
            user_id=current_user.user_id,
            workspace_id=workspace_id,
            conversation_id=request.conversation_id,
            title=request.title,
            execution_policy=request.execution_policy,
            branched_from_conversation_id=request.branched_from_conversation_id,
            recovery_policy=request.recovery_policy,
            code_timeout=request.code_timeout,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Operation failed") from exc


@router.get(
    "/{workspace_id}/conversations/{conversation_id}/runs",
    response_model=ConversationRunsResponse,
)
async def list_conversation_runs(
    workspace_id: str,
    conversation_id: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: UserInfo = Depends(require_auth()),
):
    service = get_workspace_registry_service()
    try:
        raw_runs = service.get_conversation_runs(
            user_id=current_user.user_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            limit=limit,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    runs = [ExecutionRecord(**item) if isinstance(item, dict) else item for item in raw_runs]
    return ConversationRunsResponse(
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        runs=runs,
        total=len(runs),
    )


@router.post(
    "/cleanup-orphan-conversations",
    response_model=OrphanConversationCleanupResponse,
)
async def cleanup_orphan_conversations(
    dry_run: bool = Query(True, description="是否仅预览，不实际删除"),
    current_user: UserInfo = Depends(require_auth()),
):
    service = get_workspace_registry_service()
    return service.cleanup_orphan_conversations(
        current_user.user_id,
        dry_run=dry_run,
    )
