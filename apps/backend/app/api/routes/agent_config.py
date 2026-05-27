"""
Agent 配置 API

用户默认配置与当前会话覆盖的读写接口。
"""

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.aiasys_config import load_aiasys_config, save_aiasys_task_models
from app.core.auth import get_current_user, require_admin
from app.models.user import UserInfo
from app.services.agent import agent_service
from app.services.agent_config import (
    AgentMode,
    get_agent_config_service,
)
from app.storage.llm_provider_storage import get_llm_provider_storage

router = APIRouter(prefix="/agent-config", tags=["agent-config"])


# ============ 请求/响应模型 ============


class PromptUpdateRequest(BaseModel):
    """提示词更新请求"""

    content: str = Field(..., description="提示词内容")


class ToolsUpdateRequest(BaseModel):
    """工具配置更新请求"""

    enabled_tools: List[str] | None = Field(
        default=None,
        description="显式启用的工具列表；传入后按完整集合保存",
    )
    disabled_tools: List[str] = Field(default_factory=list, description="禁用的工具列表")
    extra_tools: List[str] = Field(default_factory=list, description="额外启用的工具列表")
    tool_strategy: str = Field(default="auto", description="工具加载策略")


class TaskModelsUpdateRequest(BaseModel):
    """任务模型路由更新请求"""

    task_models: dict[str, str] = Field(
        default_factory=dict,
        description="任务类型到模型ID的映射",
    )


class RuntimeConfigUpdateRequest(BaseModel):
    """运行时自动压缩配置更新请求。"""

    reserved_context_size: Optional[int] = Field(
        None,
        ge=1000,
        description="为模型回复保留的 token 空间",
    )
    compaction_trigger_ratio: Optional[float] = Field(
        None,
        ge=0.5,
        le=0.99,
        description="自动压缩触发比例",
    )


class AgentConfigResponse(BaseModel):
    """Agent 配置响应"""

    mode: str = Field(..., description="Agent 模式")
    is_customized: bool = Field(..., description="是否有用户自定义")
    prompt_source: str = Field(..., description="提示词来源")
    enabled_tools: List[str] = Field(default_factory=list, description="启用的工具列表")
    disabled_tools: List[str] = Field(default_factory=list, description="禁用的工具列表")
    tool_strategy: str = Field(default="auto", description="工具加载策略")
    system_prompt_preview: str = Field(..., description="系统提示词预览")
    reserved_context_size: int = Field(..., description="为模型回复保留的 token 空间")
    compaction_trigger_ratio: float = Field(..., description="自动压缩触发比例")
    runtime_source: str = Field(..., description="运行时配置来源")


class UserConfigResponse(BaseModel):
    """用户配置响应（仅用户自定义部分）"""

    mode: str = Field(..., description="Agent 模式")
    enabled: bool = Field(..., description="是否启用自定义")
    prompt_content: Optional[str] = Field(None, description="提示词覆盖内容")
    enabled_tools: List[str] = Field(default_factory=list, description="显式启用的工具")
    disabled_tools: List[str] = Field(default_factory=list, description="禁用的工具")
    tool_strategy: str = Field(default="auto", description="工具加载策略")
    reserved_context_size: Optional[int] = Field(None, description="保留回复空间覆盖")
    compaction_trigger_ratio: Optional[float] = Field(None, description="自动压缩触发比例覆盖")


class EditableConfigResponse(BaseModel):
    """编辑器可直接使用的配置响应。"""

    mode: str = Field(..., description="Agent 模式")
    enabled: bool = Field(..., description="是否可编辑")
    prompt_content: Optional[str] = Field(None, description="当前编辑内容")
    enabled_tools: List[str] = Field(default_factory=list, description="当前启用的工具")
    disabled_tools: List[str] = Field(default_factory=list, description="当前禁用的工具")
    tool_strategy: str = Field(default="auto", description="工具加载策略")
    reserved_context_size: int = Field(..., description="当前保留回复空间")
    compaction_trigger_ratio: float = Field(..., description="当前自动压缩触发比例")
    source: str = Field(..., description="当前编辑内容来源")
    runtime_source: str = Field(..., description="当前运行时配置来源")
    has_local_override: bool = Field(..., description="当前作用域是否已有本地覆盖")
    has_local_runtime_override: bool = Field(
        ...,
        description="当前作用域是否已有本地运行时配置覆盖",
    )


def _ensure_session_scope_editable(
    *,
    current_user: UserInfo,
    session_id: str | None,
) -> None:
    if not session_id:
        return
    session_key = f"{current_user.user_id}/{session_id}"
    if session_key in agent_service._active_sessions:
        raise HTTPException(
            status_code=409,
            detail="当前会话正在执行中，结束本轮执行后才能修改当前会话配置。",
        )


@router.get("/task-models")
async def get_task_models(
    current_user: UserInfo = Depends(get_current_user),
):
    """获取当前任务模型路由配置和可用模型列表。"""
    toml_cfg = load_aiasys_config(user_id=current_user.user_id)
    storage = get_llm_provider_storage()
    models = storage.list_models(current_user.user_id, enabled_only=True)
    available_model_ids = [m.get("id") for m in models if m.get("id")]
    return {
        "task_models": toml_cfg.llm.task_models,
        "available_models": available_model_ids,
    }


@router.put("/task-models")
async def update_task_models(
    request: TaskModelsUpdateRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """更新任务模型路由配置。"""
    storage = get_llm_provider_storage()
    models = storage.list_models(current_user.user_id, enabled_only=True)
    available_ids = {m.get("id") for m in models if m.get("id")}

    for task, model_id in request.task_models.items():
        if model_id and model_id not in available_ids:
            raise HTTPException(
                status_code=400,
                detail="Model not found in available models",
            )

    save_aiasys_task_models(current_user.user_id, request.task_models)
    return {"success": True, "message": "任务模型路由已保存"}


# ============ 用户配置 API ============


@router.get("/{mode}", response_model=AgentConfigResponse)
async def get_merged_config(
    mode: AgentMode,
    session_id: str | None = None,
    workspace_id: str | None = None,
    current_user: UserInfo = Depends(get_current_user),
) -> AgentConfigResponse:
    """
    获取合并后的 Agent 配置（预览用）

    返回系统默认配置和用户自定义配置合并后的结果。
    """
    service = get_agent_config_service()

    try:
        config = await service.get_merged_config(
            mode=mode,
            user_id=current_user.user_id,
            session_id=session_id,
            workspace_id=workspace_id,
        )

        return AgentConfigResponse(
            mode=config.mode.value,
            is_customized=config.is_customized,
            prompt_source=config.prompt_source,
            enabled_tools=config.enabled_tools,
            disabled_tools=config.disabled_tools,
            tool_strategy=config.tool_strategy,
            system_prompt_preview=config.system_prompt,
            reserved_context_size=config.runtime_config.reserved_context_size,
            compaction_trigger_ratio=config.runtime_config.compaction_trigger_ratio,
            runtime_source=config.runtime_source,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to get config")


@router.get("/{mode}/editor", response_model=EditableConfigResponse)
async def get_editor_config(
    mode: AgentMode,
    session_id: str,
    current_user: UserInfo = Depends(get_current_user),
) -> EditableConfigResponse:
    """获取当前会话编辑器所需的有效配置。"""
    service = get_agent_config_service()

    try:
        config = await service.get_session_editor_config(
            mode=mode,
            user_id=current_user.user_id,
            session_id=session_id,
        )
        return EditableConfigResponse(**config)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to get session config")


@router.get("/{mode}/workspace/editor", response_model=EditableConfigResponse)
async def get_workspace_editor_config(
    mode: AgentMode,
    workspace_id: str,
    current_user: UserInfo = Depends(get_current_user),
) -> EditableConfigResponse:
    """获取工作区编辑器所需的有效配置。"""
    service = get_agent_config_service()

    try:
        config = await service.get_workspace_editor_config(
            mode=mode,
            user_id=current_user.user_id,
            workspace_id=workspace_id,
        )
        return EditableConfigResponse(**config)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to get workspace config")


@router.get("/{mode}/user", response_model=UserConfigResponse)
async def get_user_config(
    mode: AgentMode,
    current_user: UserInfo = Depends(get_current_user),
) -> UserConfigResponse:
    """
    获取用户自定义配置（编辑用）

    仅返回用户自己定义的配置部分，不包含系统默认。
    """
    service = get_agent_config_service()

    try:
        user_config = await service.get_user_config(current_user.user_id)

        if not user_config:
            return UserConfigResponse(mode=mode.value, enabled=False)

        mode_config = None
        if mode == AgentMode.ANALYSIS and user_config.analysis:
            mode_config = user_config.analysis

        if not mode_config:
            return UserConfigResponse(mode=mode.value, enabled=False)

        return UserConfigResponse(
            mode=mode.value,
            enabled=mode_config.enabled,
            prompt_content=mode_config.prompt.content if mode_config.prompt else None,
            enabled_tools=mode_config.tools.enabled_tools if mode_config.tools else [],
            disabled_tools=mode_config.tools.disabled_tools if mode_config.tools else [],
            tool_strategy=mode_config.tools.tool_strategy if mode_config.tools else "auto",
            reserved_context_size=(
                mode_config.runtime.reserved_context_size if mode_config.runtime else None
            ),
            compaction_trigger_ratio=(
                mode_config.runtime.compaction_trigger_ratio if mode_config.runtime else None
            ),
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to get user config")


@router.put("/{mode}/prompt")
async def update_prompt(
    mode: AgentMode,
    request: PromptUpdateRequest,
    session_id: str | None = None,
    workspace_id: str | None = None,
    current_user: UserInfo = Depends(get_current_user),
):
    """
    更新提示词覆盖
    """
    service = get_agent_config_service()

    try:
        _ensure_session_scope_editable(
            current_user=current_user,
            session_id=session_id,
        )
        success = await service.save_prompt_override(
            mode=mode,
            user_id=current_user.user_id,
            content=request.content,
            session_id=session_id,
            workspace_id=workspace_id,
        )

        if not success:
            raise HTTPException(status_code=500, detail="保存提示词失败")

        return {"success": True, "message": "提示词已保存"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to save prompt")


@router.put("/{mode}/tools")
async def update_tools(
    mode: AgentMode,
    request: ToolsUpdateRequest,
    session_id: str | None = None,
    workspace_id: str | None = None,
    current_user: UserInfo = Depends(get_current_user),
):
    """
    更新工具配置
    """
    service = get_agent_config_service()

    try:
        _ensure_session_scope_editable(
            current_user=current_user,
            session_id=session_id,
        )
        success = await service.save_tools_config(
            mode=mode,
            user_id=current_user.user_id,
            disabled_tools=request.disabled_tools,
            extra_tools=request.extra_tools,
            enabled_tools=request.enabled_tools,
            tool_strategy=request.tool_strategy,
            session_id=session_id,
            workspace_id=workspace_id,
        )

        if not success:
            raise HTTPException(status_code=500, detail="保存工具配置失败")

        return {"success": True, "message": "工具配置已保存"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to save tool config")


@router.put("/{mode}/runtime")
async def update_runtime(
    mode: AgentMode,
    request: RuntimeConfigUpdateRequest,
    session_id: str | None = None,
    workspace_id: str | None = None,
    current_user: UserInfo = Depends(get_current_user),
):
    """
    更新运行时自动压缩配置
    """
    service = get_agent_config_service()

    try:
        _ensure_session_scope_editable(
            current_user=current_user,
            session_id=session_id,
        )
        success = await service.save_runtime_config(
            mode=mode,
            user_id=current_user.user_id,
            reserved_context_size=request.reserved_context_size,
            compaction_trigger_ratio=request.compaction_trigger_ratio,
            session_id=session_id,
            workspace_id=workspace_id,
        )

        if not success:
            raise HTTPException(status_code=500, detail="保存运行时配置失败")

        return {"success": True, "message": "运行时配置已保存"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to save runtime config")


@router.post("/{mode}/reset")
async def reset_to_default(
    mode: AgentMode,
    session_id: str | None = None,
    workspace_id: str | None = None,
    current_user: UserInfo = Depends(get_current_user),
):
    """
    重置为系统默认配置

    删除指定作用域的自定义配置，恢复使用系统默认。
    """
    service = get_agent_config_service()

    try:
        _ensure_session_scope_editable(
            current_user=current_user,
            session_id=session_id,
        )
        success = await service.reset_to_default(
            mode=mode,
            user_id=current_user.user_id,
            session_id=session_id,
            workspace_id=workspace_id,
        )

        if not success:
            raise HTTPException(status_code=500, detail="重置配置失败")

        return {"success": True, "message": "配置已重置为系统默认"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to reset config")


@router.post("/{mode}/validate")
async def validate_config(
    mode: AgentMode,
    session_id: str | None = None,
    workspace_id: str | None = None,
    current_user: UserInfo = Depends(get_current_user),
):
    """
    验证用户配置的有效性
    """
    service = get_agent_config_service()

    try:
        is_valid, errors = await service.validate_config(
            mode=mode,
            user_id=current_user.user_id,
            session_id=session_id,
            workspace_id=workspace_id,
        )

        return {
            "valid": is_valid,
            "errors": errors,
        }
    except Exception:
        raise HTTPException(status_code=500, detail="Configuration validation failed")


# ============ 管理员 API ============


@router.get("/admin/system/{mode}")
async def get_system_default_config(
    mode: AgentMode,
    current_user: UserInfo = Depends(require_admin),
):
    """
    获取系统默认配置（仅管理员）

    用于管理员查看和编辑系统默认配置。
    """
    from app.services.agent.system_presets import (
        build_system_config_from_preset,
        resolve_system_agent_preset_from_path,
    )
    from app.services.agent_config.models import get_system_default_config_path

    try:
        config_path = get_system_default_config_path(mode)
        preset = resolve_system_agent_preset_from_path(config_path)
        if preset is not None:
            config_data = build_system_config_from_preset(preset)
            config_ref = preset.config_ref
        else:
            if not config_path.exists():
                raise HTTPException(status_code=404, detail="系统默认配置不存在")
            import tomllib

            config_content = config_path.read_text(encoding="utf-8")
            config_data = tomllib.loads(config_content)
            config_ref = str(config_path)

        # 获取提示词文件路径
        prompt_path_str = config_data.get("agent", {}).get("system_prompt_path", "")
        prompt_content = ""
        if prompt_path_str:
            prompt_path = config_path.parent / prompt_path_str
            if prompt_path.exists():
                prompt_content = prompt_path.read_text(encoding="utf-8")

        return {
            "mode": mode.value,
            "config_path": config_ref,
            "config": config_data,
            "prompt_content": prompt_content,
        }
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to retrieve system config")


@router.put("/admin/system/{mode}/prompt")
async def update_system_prompt(
    mode: AgentMode,
    request: PromptUpdateRequest,
    current_user: UserInfo = Depends(require_admin),
):
    """
    更新系统默认提示词（仅管理员）

    ⚠️ 警告：这会影响到所有用户！
    """
    from app.services.agent.system_presets import (
        build_system_config_from_preset,
        resolve_system_agent_preset_from_path,
    )
    from app.services.agent_config.models import get_system_default_config_path

    try:
        config_path = get_system_default_config_path(mode)

        # 读取配置获取提示词文件路径
        preset = resolve_system_agent_preset_from_path(config_path)
        if preset is not None:
            config_data = build_system_config_from_preset(preset)
        else:
            import tomllib

            config_data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        prompt_path_str = config_data.get("agent", {}).get("system_prompt_path", "")

        if not prompt_path_str:
            raise HTTPException(status_code=500, detail="无法确定提示词文件路径")

        prompt_path = Path(prompt_path_str)
        if not prompt_path.is_absolute():
            prompt_path = config_path.parent / prompt_path

        # 备份原文件
        backup_path = prompt_path.with_suffix(".md.backup")
        if prompt_path.exists() and not backup_path.exists():
            backup_path.write_text(prompt_path.read_text(encoding="utf-8"), encoding="utf-8")

        # 写入新内容
        prompt_path.write_text(request.content, encoding="utf-8")

        return {
            "success": True,
            "message": "系统默认提示词已更新",
            "backup_created": backup_path.exists(),
        }
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to update system prompt")
