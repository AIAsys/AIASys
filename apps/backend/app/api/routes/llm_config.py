"""
LLM 配置 API - 完整版

管理服务商配置（base_url + api_key）和模型配置
"""

import logging
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, SecretStr, field_validator

logger = logging.getLogger(__name__)

from app.core.auth import get_current_user
from app.models.llm_provider import (
    FetchModelsResult,
    LLMModelConfig,
    LLMModelDefaults,
    LLMProviderConfig,
    ModelCapability,
    ModelType,
    ProviderTestResult,
    ProviderType,
    RemoteModelInfo,
    get_provider_templates,
)
from app.models.user import UserInfo
from app.services.llm import LLMConfigService, get_llm_config_service
from app.utils.llm_url_validator import validate_llm_base_url

router = APIRouter(prefix="/llm", tags=["llm-config"])


# ========== 扩展响应模型（包含继承标记） ==========


class ProviderConfigResponse(LLMProviderConfig):
    """服务商配置响应"""

    pass


class ModelConfigResponse(LLMModelConfig):
    """模型配置响应"""

    pass


class ProviderListResponse(BaseModel):
    """服务商列表响应"""

    providers: List[ProviderConfigResponse] = Field(default_factory=list)
    total: int = Field(default=0)


class ModelListResponse(BaseModel):
    """模型列表响应"""

    models: List[ModelConfigResponse] = Field(default_factory=list)
    total: int = Field(default=0)


# ========== 请求/响应模型 ==========


class CreateProviderRequest(BaseModel):
    """创建服务商请求"""

    id: str = Field(..., min_length=1, max_length=64, description="服务商唯一标识")
    name: str = Field(..., min_length=1, max_length=128, description="显示名称")
    type: ProviderType = Field(..., description="服务商类型")
    base_url: str = Field(..., description="API 基础 URL")
    api_key: str = Field(..., description="API Key")
    env: Optional[Dict[str, str]] = Field(None, description="环境变量配置")
    custom_headers: Dict[str, str] = Field(default_factory=dict, description="自定义请求头")
    enabled: bool = Field(default=True, description="是否启用")
    is_default: bool = Field(default=False, description="是否为默认")
    description: Optional[str] = Field(None, description="描述")

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        validate_llm_base_url(v)
        return v


class UpdateProviderRequest(BaseModel):
    """更新服务商请求"""

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    base_url: Optional[str] = None
    api_key: Optional[str] = Field(None, description="API Key（留空表示不修改）")
    env: Optional[Dict[str, str]] = Field(None, description="环境变量配置")
    custom_headers: Optional[Dict[str, str]] = None
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    description: Optional[str] = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            validate_llm_base_url(v)
        return v


class CreateModelRequest(BaseModel):
    """创建模型请求"""

    id: str = Field(..., min_length=1, max_length=128, description="模型配置唯一标识")
    name: str = Field(..., min_length=1, max_length=128, description="显示名称")
    provider: str = Field(..., min_length=1, description="关联的服务商 ID")
    model: str = Field(..., min_length=1, description="模型名称")
    model_type: ModelType = Field(default="chat", description="模型用途类型：chat 或 embedding")
    dimension: Optional[int] = Field(None, gt=0, description="向量维度（仅 embedding 模型需要）")
    max_context_size: int = Field(..., gt=0, description="最大上下文长度（tokens）")
    capabilities: Optional[Set[ModelCapability]] = Field(None, description="模型能力集合")
    enabled: bool = Field(default=True, description="是否启用")
    is_default: bool = Field(default=False, description="是否为默认模型")
    description: Optional[str] = Field(None, description="模型描述")


class UpdateModelRequest(BaseModel):
    """更新模型请求"""

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    provider: Optional[str] = Field(None, min_length=1)
    model: Optional[str] = Field(None, min_length=1)
    model_type: Optional[ModelType] = None
    dimension: Optional[int] = Field(None, gt=0)
    max_context_size: Optional[int] = Field(None, gt=0)
    capabilities: Optional[Set[ModelCapability]] = None
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    description: Optional[str] = None


class BatchCreateModelsRequest(BaseModel):
    """批量创建模型请求"""

    provider_id: str = Field(..., min_length=1, description="服务商 ID")
    models: List[RemoteModelInfo] = Field(
        ..., min_length=1, description="模型列表（含从 /v1/models 获取的上下文长度等信息）"
    )


class UpdateModelDefaultsRequest(BaseModel):
    """更新默认 chat / embedding 模型请求。"""

    default_chat_model: Optional[str] = Field(
        default=None,
        description="默认 chat 模型 ID；传 null 表示清空",
    )
    default_embedding_model: Optional[str] = Field(
        default=None,
        description="默认 embedding 模型 ID；传 null 表示清空",
    )


# ========== Helper ==========


def get_service() -> LLMConfigService:
    """获取服务实例"""
    return get_llm_config_service()


def get_user_id(user: UserInfo) -> str:
    """获取用户 ID"""
    return user.user_id


def _provider_to_response(provider: LLMProviderConfig) -> ProviderConfigResponse:
    """将 ProviderConfig 转换为响应模型"""
    return ProviderConfigResponse(**provider.model_dump())


def _model_to_response(model: LLMModelConfig) -> ModelConfigResponse:
    """将 ModelConfig 转换为响应模型"""
    return ModelConfigResponse(**model.model_dump())


def _defaults_to_response(defaults: LLMModelDefaults) -> LLMModelDefaults:
    return LLMModelDefaults(**defaults.model_dump())


# ========== Provider API ==========


@router.get("/providers", response_model=ProviderListResponse)
async def list_providers(
    enabled_only: bool = Query(False, description="只显示启用的"),
    user: UserInfo = Depends(get_current_user),
    service: LLMConfigService = Depends(get_service),
) -> Dict[str, Any]:
    """列出服务商配置"""
    user_id = get_user_id(user)
    providers = service.list_providers(user_id, enabled_only)
    return {
        "providers": [_provider_to_response(p) for p in providers],
        "total": len(providers),
    }


@router.get("/providers/{provider_id}", response_model=ProviderConfigResponse)
async def get_provider(
    provider_id: str,
    user: UserInfo = Depends(get_current_user),
    service: LLMConfigService = Depends(get_service),
) -> ProviderConfigResponse:
    """获取服务商配置"""
    user_id = get_user_id(user)

    provider = service.get_provider(user_id, provider_id)
    if provider:
        return _provider_to_response(provider)

    raise HTTPException(status_code=404, detail="Provider not found")


@router.post("/providers", response_model=ProviderConfigResponse)
async def create_provider(
    request: CreateProviderRequest,
    user: UserInfo = Depends(get_current_user),
    service: LLMConfigService = Depends(get_service),
) -> ProviderConfigResponse:
    """创建服务商配置"""
    user_id = get_user_id(user)

    config = LLMProviderConfig(
        id=request.id,
        name=request.name,
        type=request.type,
        base_url=request.base_url,
        api_key=SecretStr(request.api_key),
        env=request.env,
        custom_headers=request.custom_headers,
        enabled=request.enabled,
        is_default=request.is_default,
        description=request.description,
    )

    try:
        result = service.create_provider(user_id, config)
        return _provider_to_response(result)
    except ValueError as e:
        logger.error("Provider creation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid provider configuration") from e


@router.patch("/providers/{provider_id}", response_model=ProviderConfigResponse)
async def update_provider(
    provider_id: str,
    request: UpdateProviderRequest,
    user: UserInfo = Depends(get_current_user),
    service: LLMConfigService = Depends(get_service),
) -> ProviderConfigResponse:
    """更新服务商配置"""
    user_id = get_user_id(user)

    updates = request.model_dump(exclude_unset=True)

    # 处理 api_key
    if "api_key" in updates and updates["api_key"]:
        updates["api_key"] = SecretStr(updates["api_key"])
    elif "api_key" in updates:
        del updates["api_key"]

    result = service.update_provider(user_id, provider_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Provider not found")

    return _provider_to_response(result)


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: str,
    user: UserInfo = Depends(get_current_user),
    service: LLMConfigService = Depends(get_service),
) -> Dict[str, bool]:
    """删除服务商配置"""
    user_id = get_user_id(user)

    success = service.delete_provider(user_id, provider_id)
    if not success:
        raise HTTPException(status_code=404, detail="Provider not found")

    return {"success": True}


# ========== Model API ==========


@router.get("/models", response_model=ModelListResponse)
async def list_models(
    enabled_only: bool = Query(False, description="只显示启用的"),
    provider_id: Optional[str] = Query(None, description="按服务商过滤"),
    user: UserInfo = Depends(get_current_user),
    service: LLMConfigService = Depends(get_service),
) -> Dict[str, Any]:
    """列出模型配置"""
    user_id = get_user_id(user)
    models = service.list_models(user_id, enabled_only, provider_id)
    return {
        "models": [_model_to_response(m) for m in models],
        "total": len(models),
    }


@router.get("/models/by-id", response_model=ModelConfigResponse)
async def get_model(
    model_id: str = Query(..., min_length=1, description="模型配置唯一标识"),
    user: UserInfo = Depends(get_current_user),
    service: LLMConfigService = Depends(get_service),
) -> ModelConfigResponse:
    """获取模型配置"""
    user_id = get_user_id(user)

    model = service.get_model(user_id, model_id)
    if model:
        return _model_to_response(model)

    raise HTTPException(status_code=404, detail="Model not found")


@router.post("/models", response_model=ModelConfigResponse)
async def create_model(
    request: CreateModelRequest,
    user: UserInfo = Depends(get_current_user),
    service: LLMConfigService = Depends(get_service),
) -> ModelConfigResponse:
    """创建模型配置"""
    user_id = get_user_id(user)

    # embedding 模型且未填写 dimension，自动探测
    dimension = request.dimension
    if request.model_type == "embedding" and dimension is None:
        try:
            dimension = await service.probe_embedding_dimension(
                user_id, request.provider, request.model
            )
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail="Dimension not specified and auto-detection failed, please set it manually",
            ) from e

    config = LLMModelConfig(
        id=request.id,
        name=request.name,
        provider=request.provider,
        model=request.model,
        model_type=request.model_type,
        dimension=dimension,
        max_context_size=request.max_context_size,
        capabilities=request.capabilities,
        enabled=request.enabled,
        is_default=request.is_default,
        description=request.description,
    )

    try:
        result = service.create_model(user_id, config)
        return _model_to_response(result)
    except ValueError as e:
        logger.error("Provider creation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid provider configuration") from e


@router.patch("/models/by-id", response_model=ModelConfigResponse)
async def update_model(
    request: UpdateModelRequest,
    model_id: str = Query(..., min_length=1, description="模型配置唯一标识"),
    user: UserInfo = Depends(get_current_user),
    service: LLMConfigService = Depends(get_service),
) -> ModelConfigResponse:
    """更新模型配置"""
    user_id = get_user_id(user)

    updates = request.model_dump(exclude_unset=True)

    # embedding 模型且未填写 dimension，自动探测
    if updates.get("model_type") == "embedding" and updates.get("dimension") is None:
        # 获取现有模型信息以确定 provider 和 model
        existing = service.get_model(user_id, model_id)
        if existing:
            provider_id = updates.get("provider") or existing.provider
            model_name = updates.get("model") or existing.model
            try:
                updates["dimension"] = await service.probe_embedding_dimension(
                    user_id, provider_id, model_name
                )
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail="Dimension not specified and auto-detection failed, please set it manually",
                ) from e

    result = service.update_model(user_id, model_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Model not found")

    return _model_to_response(result)


@router.delete("/models/by-id")
async def delete_model(
    model_id: str = Query(..., min_length=1, description="模型配置唯一标识"),
    user: UserInfo = Depends(get_current_user),
    service: LLMConfigService = Depends(get_service),
) -> Dict[str, bool]:
    """删除模型配置"""
    user_id = get_user_id(user)

    success = service.delete_model(user_id, model_id)
    if not success:
        raise HTTPException(status_code=404, detail="Model not found")

    return {"success": True}


@router.post("/models/by-id/default", response_model=ModelConfigResponse)
async def set_default_model(
    model_id: str = Query(..., min_length=1, description="模型配置唯一标识"),
    user: UserInfo = Depends(get_current_user),
    service: LLMConfigService = Depends(get_service),
) -> ModelConfigResponse:
    """设置默认模型"""
    user_id = get_user_id(user)

    result = service.set_default_model(user_id, model_id)
    if not result:
        raise HTTPException(status_code=404, detail="Model not found")

    return _model_to_response(result)


@router.get("/defaults", response_model=LLMModelDefaults)
async def get_model_defaults(
    user: UserInfo = Depends(get_current_user),
    service: LLMConfigService = Depends(get_service),
) -> LLMModelDefaults:
    """获取默认 chat / embedding 模型。"""
    user_id = get_user_id(user)
    return _defaults_to_response(service.get_model_defaults(user_id))


@router.put("/defaults", response_model=LLMModelDefaults)
async def update_model_defaults(
    request: UpdateModelDefaultsRequest,
    user: UserInfo = Depends(get_current_user),
    service: LLMConfigService = Depends(get_service),
) -> LLMModelDefaults:
    """更新默认 chat / embedding 模型。"""
    user_id = get_user_id(user)
    try:
        return _defaults_to_response(
            service.update_model_defaults(
                user_id,
                default_chat_model=request.default_chat_model,
                default_embedding_model=request.default_embedding_model,
            )
        )
    except ValueError as e:
        logger.error("Provider creation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid provider configuration") from e


# ========== 远程模型获取 API ==========


@router.post("/providers/{provider_id}/fetch-models", response_model=FetchModelsResult)
async def fetch_provider_models(
    provider_id: str,
    user: UserInfo = Depends(get_current_user),
    service: LLMConfigService = Depends(get_service),
) -> FetchModelsResult:
    """从 provider API 获取可用模型列表"""
    user_id = get_user_id(user)

    result = await service.fetch_remote_models(user_id, provider_id)
    return result


@router.post("/models/batch", response_model=ModelListResponse)
async def batch_create_models(
    request: BatchCreateModelsRequest,
    user: UserInfo = Depends(get_current_user),
    service: LLMConfigService = Depends(get_service),
) -> Dict[str, Any]:
    """批量创建模型（幂等，已存在的跳过）"""
    user_id = get_user_id(user)

    try:
        results = service.batch_create_models(user_id, request.provider_id, request.models)
        return {
            "models": [_model_to_response(m) for m in results],
            "total": len(results),
        }
    except ValueError as e:
        logger.error("Provider creation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid provider configuration") from e


# ========== 测试 API ==========


@router.post("/providers/{provider_id}/test", response_model=ProviderTestResult)
async def test_provider(
    provider_id: str,
    user: UserInfo = Depends(get_current_user),
    service: LLMConfigService = Depends(get_service),
) -> ProviderTestResult:
    """测试服务商连通性"""
    user_id = get_user_id(user)

    result = await service.test_provider(user_id, provider_id)
    return result


# ========== 配置管理 API ==========


@router.get("/templates")
async def get_templates(
    user: UserInfo = Depends(get_current_user),
) -> Dict[str, Any]:
    """获取服务商模板（仅作为前端默认值参考，需登录）"""
    return get_provider_templates()


@router.post("/initialize")
async def initialize_defaults(
    user: UserInfo = Depends(get_current_user),
    service: LLMConfigService = Depends(get_service),
) -> Dict[str, str]:
    """初始化默认配置（空配置）"""
    user_id = get_user_id(user)
    service.initialize_defaults(user_id)
    return {"message": "配置初始化成功"}
