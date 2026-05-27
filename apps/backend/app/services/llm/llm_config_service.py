"""
LLM 配置服务

管理服务商配置（base_url + api_key）和模型配置
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import SecretStr

from app.core.config import LLM_CONFIG, LLM_PROVIDERS
from app.core.encryption import mask_api_key
from app.models.llm_provider import (
    FetchModelsResult,
    LLMModelConfig,
    LLMModelDefaults,
    LLMProviderConfig,
    ProviderTestResult,
    RemoteModelInfo,
)
from app.storage.llm_provider_storage import LLMProviderStorage, get_llm_provider_storage

logger = logging.getLogger(__name__)


class LLMConfigService:
    """LLM 配置服务"""

    def __init__(self, storage: Optional[LLMProviderStorage] = None) -> None:
        self._storage = storage or get_llm_provider_storage()

    # ========== Provider 操作 ==========

    def create_provider(self, user_id: str, config: LLMProviderConfig) -> LLMProviderConfig:
        """创建服务商配置"""
        data = {
            "id": config.id,
            "name": config.name,
            "type": config.type,
            "base_url": config.base_url,
            "api_key": config.api_key.get_secret_value(),
            "custom_headers": config.custom_headers,
            "enabled": config.enabled,
            "is_default": config.is_default,
            "description": config.description,
        }

        result = self._storage.create_provider(user_id, data)
        return self._dict_to_provider_config(result)

    def get_provider(self, user_id: str, provider_id: str) -> Optional[LLMProviderConfig]:
        """获取服务商配置（脱敏 API Key）"""
        data = self._storage.get_provider(user_id, provider_id)
        if not data:
            return None
        return self._dict_to_provider_config(data)

    def get_provider_with_key(self, user_id: str, provider_id: str) -> Optional[LLMProviderConfig]:
        """获取服务商配置（含解密的 API Key）"""
        data = self._storage.get_provider_with_key(user_id, provider_id)
        if not data:
            return None

        config = self._dict_to_provider_config(data)
        if data.get("api_key"):
            config.api_key = SecretStr(data["api_key"])
        return config

    def list_providers(self, user_id: str, enabled_only: bool = False) -> List[LLMProviderConfig]:
        """列出服务商配置"""
        data_list = self._storage.list_providers(user_id, enabled_only)
        return [self._dict_to_provider_config(d) for d in data_list]

    def update_provider(
        self, user_id: str, provider_id: str, updates: Dict[str, Any]
    ) -> Optional[LLMProviderConfig]:
        """更新服务商配置"""
        # 处理 is_default 变更
        if updates.get("is_default"):
            self._storage.unset_default_providers(user_id, exclude_provider_id=provider_id)

        if "api_key" in updates and isinstance(updates["api_key"], SecretStr):
            updates["api_key"] = updates["api_key"].get_secret_value()

        result = self._storage.update_provider(user_id, provider_id, updates)
        if not result:
            return None

        return self._dict_to_provider_config(result)

    def delete_provider(self, user_id: str, provider_id: str) -> bool:
        """删除服务商配置（会级联删除关联的模型）"""
        return self._storage.delete_provider(user_id, provider_id)

    # ========== Model 操作 ==========

    def create_model(self, user_id: str, config: LLMModelConfig) -> LLMModelConfig:
        """创建模型配置"""
        # 验证 provider 是否存在
        provider = self._storage.get_provider(user_id, config.provider)
        if not provider:
            raise ValueError(f"Provider '{config.provider}' not found")

        data = {
            "id": config.id,
            "name": config.name,
            "provider": config.provider,
            "model": config.model,
            "model_type": config.model_type,
            "dimension": config.dimension,
            "max_context_size": config.max_context_size,
            "capabilities": config.capabilities,
            "enabled": config.enabled,
            "is_default": config.is_default,
            "description": config.description,
        }

        # 如果设置为默认，取消其他模型的默认状态
        if config.is_default:
            self._storage.unset_default_models(user_id, exclude_model_id=config.id)

        result = self._storage.create_model(user_id, data)
        if config.is_default:
            self.update_model_defaults(
                user_id,
                default_chat_model=config.id if config.model_type != "embedding" else None,
                default_embedding_model=config.id if config.model_type == "embedding" else None,
                merge=True,
            )
        return self._dict_to_model_config(result)

    def get_model(self, user_id: str, model_id: str) -> Optional[LLMModelConfig]:
        """获取模型配置"""
        data = self._storage.get_model(user_id, model_id)
        if not data:
            return None
        return self._dict_to_model_config(data)

    def list_models(
        self, user_id: str, enabled_only: bool = False, provider_id: Optional[str] = None
    ) -> List[LLMModelConfig]:
        """列出模型配置"""
        data_list = self._storage.list_models(user_id, enabled_only, provider_id)
        return [self._dict_to_model_config(d) for d in data_list]

    def update_model(
        self, user_id: str, model_id: str, updates: Dict[str, Any]
    ) -> Optional[LLMModelConfig]:
        """更新模型配置"""
        # 如果设置为默认，取消其他模型的默认状态
        if updates.get("is_default"):
            self._storage.unset_default_models(user_id, exclude_model_id=model_id)

        result = self._storage.update_model(user_id, model_id, updates)
        if not result:
            return None

        result_model = self._dict_to_model_config(result)
        if updates.get("is_default"):
            self.update_model_defaults(
                user_id,
                default_chat_model=model_id if result_model.model_type != "embedding" else None,
                default_embedding_model=(
                    model_id if result_model.model_type == "embedding" else None
                ),
                merge=True,
            )

        return result_model

    def delete_model(self, user_id: str, model_id: str) -> bool:
        """删除模型配置"""
        return self._storage.delete_model(user_id, model_id)

    def set_default_model(self, user_id: str, model_id: str) -> Optional[LLMModelConfig]:
        """设置默认模型，取消其他模型的默认状态"""
        model = self._storage.get_model(user_id, model_id)
        if not model:
            return None

        # 取消其他模型的默认状态
        self._storage.unset_default_models(user_id, exclude_model_id=model_id)

        # 设置当前模型为默认
        result = self._storage.update_model(user_id, model_id, {"is_default": True})
        if result:
            model_config = self._dict_to_model_config(result)
            self.update_model_defaults(
                user_id,
                default_chat_model=model_id if model_config.model_type != "embedding" else None,
                default_embedding_model=(
                    model_id if model_config.model_type == "embedding" else None
                ),
                merge=True,
            )
            return model_config
        return None

    def get_model_defaults(self, user_id: str) -> LLMModelDefaults:
        """获取默认 chat / embedding 模型。"""
        data = self._storage.get_full_config(user_id)
        raw_default_chat = data.get("default_chat_model") or data.get("default_model")
        raw_default_embedding = data.get("default_embedding_model")
        return LLMModelDefaults(
            default_chat_model=self._coerce_configured_default_model_id(
                data,
                raw_default_chat,
                expected_model_type="chat",
            ),
            default_embedding_model=self._coerce_configured_default_model_id(
                data,
                raw_default_embedding,
                expected_model_type="embedding",
            ),
        )

    def update_model_defaults(
        self,
        user_id: str,
        *,
        default_chat_model: Optional[str],
        default_embedding_model: Optional[str],
        merge: bool = False,
    ) -> LLMModelDefaults:
        """更新默认 chat / embedding 模型。"""
        current = self.get_model_defaults(user_id) if merge else None
        data = self._storage.get_full_config(user_id)

        next_default_chat = (
            current.default_chat_model
            if merge and default_chat_model is None
            else default_chat_model
        )
        next_default_embedding = (
            current.default_embedding_model
            if merge and default_embedding_model is None
            else default_embedding_model
        )

        validated_chat = self._validate_default_model_id(
            data,
            next_default_chat,
            expected_model_type="chat",
        )
        validated_embedding = self._validate_default_model_id(
            data,
            next_default_embedding,
            expected_model_type="embedding",
        )
        updated = self._storage.update_model_defaults(
            user_id,
            {
                "default_model": validated_chat,
                "default_chat_model": validated_chat,
                "default_embedding_model": validated_embedding,
            },
        )
        return LLMModelDefaults(
            default_chat_model=updated.get("default_chat_model"),
            default_embedding_model=updated.get("default_embedding_model"),
        )

    def resolve_default_chat_model_id(self, user_id: str) -> Optional[str]:
        data = self._storage.get_full_config(user_id)
        return self._select_default_model_id(data, model_type="chat")

    def resolve_default_embedding_model_id(self, user_id: str) -> Optional[str]:
        data = self._storage.get_full_config(user_id)
        return self._select_default_model_id(data, model_type="embedding")

    def resolve_embedding_model_config(
        self,
        user_id: str,
        model_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """解析默认或指定 embedding 模型的运行时配置。"""
        target_model_id = model_id or self.resolve_default_embedding_model_id(user_id)
        if not target_model_id:
            return None

        model = self.get_model(user_id, target_model_id)
        if not model or model.model_type != "embedding" or not model.enabled:
            return None

        provider = self.get_provider_with_key(user_id, model.provider)
        if not provider or not provider.enabled:
            return None

        api_key = provider.api_key.get_secret_value()
        if not api_key:
            return None

        return {
            "model_id": model.id,
            "model_name": model.model,
            "provider_id": provider.id,
            "provider_type": provider.type,
            "provider_name": provider.name,
            "base_url": provider.base_url,
            "api_key": api_key,
            "custom_headers": provider.custom_headers or {},
            "dimension": model.dimension,
        }

    # ========== Full Config ==========

    def get_full_config(self, user_id: str) -> Dict[str, Any]:
        """获取完整配置（用于运行时）

        返回格式:
        {
            "providers": {
                "provider_id": {
                    "type": "anthropic_messages",
                    "base_url": "...",
                    "api_key": "...",
                    "custom_headers": {...}
                }
            },
            "models": {
                "model_id": {
                    "provider": "provider_id",
                    "model": "kimi-for-coding",
                    "max_context_size": 200000,
                    "capabilities": ["thinking", "image_in"]
                }
            },
            "default_model": "model_id"
        }
        """
        # 获取用户配置
        data = self._storage.get_full_config(user_id)

        providers_config = {}
        models_config = {}
        default_chat_model = self.resolve_default_chat_model_id(user_id)
        default_embedding_model = self.resolve_default_embedding_model_id(user_id)

        # 处理 providers
        for provider in data.get("providers", []):
            if not provider.get("enabled", True):
                continue

            provider_id = provider.get("id")
            providers_config[provider_id] = {
                "type": provider.get("type"),
                "base_url": provider.get("base_url"),
                "api_key": provider.get("api_key", ""),
                "custom_headers": provider.get("custom_headers", {}),
            }
            if provider.get("reasoning_key") is not None:
                providers_config[provider_id]["reasoning_key"] = provider.get("reasoning_key")
            if provider.get("reasoning_format") is not None:
                providers_config[provider_id]["reasoning_format"] = provider.get("reasoning_format")

            # Kimi Coding API 需要特定的 User-Agent
            base_url = provider.get("base_url", "")
            if "kimi.com/coding" in base_url:
                custom_headers = providers_config[provider_id].get("custom_headers") or {}
                if "User-Agent" not in custom_headers:
                    custom_headers["User-Agent"] = "KimiCLI/1.16.0"
                    providers_config[provider_id]["custom_headers"] = custom_headers

        # 处理 models
        for model in data.get("models", []):
            if not model.get("enabled", True):
                continue

            model_id = model.get("id")

            # 处理 capabilities 字段
            capabilities = model.get("capabilities", [])
            if isinstance(capabilities, str):
                try:
                    import ast

                    capabilities = ast.literal_eval(capabilities)
                    if isinstance(capabilities, (list, set)):
                        capabilities = list(capabilities)
                    else:
                        capabilities = [capabilities]
                except (ValueError, SyntaxError):
                    capabilities = []
            elif isinstance(capabilities, set):
                capabilities = list(capabilities)

            models_config[model_id] = {
                "id": model_id,
                "name": model.get("name"),
                "provider": model.get("provider"),
                "model": model.get("model"),
                "model_type": model.get("model_type", "chat"),
                "dimension": model.get("dimension"),
                "max_context_size": model.get("max_context_size", 128000),
                "capabilities": capabilities,
            }

        return {
            "providers": providers_config,
            "models": models_config,
            "default_model": (default_chat_model if default_chat_model in models_config else None),
            "default_chat_model": (
                default_chat_model if default_chat_model in models_config else None
            ),
            "default_embedding_model": (
                default_embedding_model if default_embedding_model in models_config else None
            ),
        }

    def initialize_defaults(self, user_id: str) -> None:
        """初始化默认配置（空配置）"""
        self._storage.initialize_defaults(user_id)

    def sync_config_json_to_user(self, user_id: str) -> None:
        """将 config.json 的 llm.providers 同步到用户配置

        仅在用户配置为空时执行（幂等），避免覆盖用户已有配置。
        使用 config.json 中的静态模型列表，避免启动时网络请求阻塞。
        """
        # 检查用户配置是否已有数据
        existing = self._storage.get_full_config(user_id)
        if existing.get("providers") or existing.get("models"):
            logger.info("用户 LLM 配置已存在，跳过 config.json 同步")
            return

        if not LLM_PROVIDERS:
            logger.warning("config.json 中无 llm.providers，跳过同步")
            return

        default_provider_id = LLM_CONFIG.get("default_provider")

        logger.info("开始同步 config.json → 用户 LLM 配置")

        created_providers = 0
        created_models = 0

        for provider_id, provider_cfg in LLM_PROVIDERS.items():
            provider_type = str(
                provider_cfg.get("protocol")
                or provider_cfg.get("type")
                or "openai_chat_completions"
            )
            base_url = provider_cfg.get("base_url", "")
            api_key = provider_cfg.get("api_key", "")
            models_list = provider_cfg.get("models", [])

            # 创建 provider
            provider_data = LLMProviderConfig(
                id=provider_id,
                name=provider_id,
                type=provider_type,
                base_url=base_url,
                api_key=SecretStr(api_key),
                custom_headers={},
                enabled=True,
                is_default=(provider_id == default_provider_id),
            )
            try:
                self.create_provider(user_id, provider_data)
                created_providers += 1
            except Exception as e:
                logger.warning("创建 provider '%s' 失败: %s", provider_id, e)
                continue

            # 使用 config.json 中的静态模型列表
            defaults = self._infer_model_defaults(provider_type)
            for model_name in models_list:
                model_id = f"{provider_id}-{model_name}"
                model_data = LLMModelConfig(
                    id=model_id,
                    name=f"{model_name} ({provider_id})",
                    provider=provider_id,
                    model=model_name,
                    max_context_size=defaults["max_context_size"],
                    capabilities=defaults["capabilities"],
                    enabled=True,
                    is_default=False,
                )
                try:
                    self.create_model(user_id, model_data)
                    created_models += 1
                except Exception as e:
                    logger.warning("创建 model '%s' 失败: %s", model_id, e)

        logger.info(f"config.json 同步完成: {created_providers} providers, {created_models} models")

    async def test_provider(self, user_id: str, provider_id: str) -> ProviderTestResult:
        """测试服务商连接"""
        import httpx

        provider = self.get_provider_with_key(user_id, provider_id)
        if not provider:
            return ProviderTestResult(
                provider_id=provider_id,
                status="error",
                error_message=f"服务商 '{provider_id}' 不存在",
            )

        if not provider.api_key.get_secret_value():
            return ProviderTestResult(
                provider_id=provider_id, status="error", error_message="API Key 未设置"
            )

        # 构建请求头部
        headers = {
            "Authorization": f"Bearer {provider.api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

        # Kimi Coding API 需要特定的 User-Agent
        if "kimi.com/coding" in provider.base_url:
            headers["User-Agent"] = "KimiCLI/1.16.0"

        if provider.custom_headers:
            headers.update(provider.custom_headers)

        import time

        start_time = time.time()

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # 测试模型列表
                resp = await client.get(f"{provider.base_url}/models", headers=headers)

                latency_ms = int((time.time() - start_time) * 1000)

                if resp.status_code == 200:
                    return ProviderTestResult(
                        provider_id=provider_id, status="success", latency_ms=latency_ms
                    )
                elif resp.status_code == 401:
                    return ProviderTestResult(
                        provider_id=provider_id,
                        status="error",
                        error_message="认证失败，请检查 API Key 是否正确",
                    )
                elif resp.status_code == 403:
                    error_text = resp.text[:200]
                    if "access_terminated" in error_text or "Coding Agents" in error_text:
                        return ProviderTestResult(
                            provider_id=provider_id,
                            status="error",
                            error_message="访问被拒绝。请使用 Coding Agent 专用的 User-Agent",
                        )
                    return ProviderTestResult(
                        provider_id=provider_id,
                        status="error",
                        error_message=f"访问被拒绝: {error_text}",
                    )
                else:
                    return ProviderTestResult(
                        provider_id=provider_id,
                        status="error",
                        error_message=f"HTTP {resp.status_code}: {resp.text[:200]}",
                    )

        except httpx.TimeoutException:
            return ProviderTestResult(
                provider_id=provider_id,
                status="timeout",
                error_message="连接超时，请检查网络或 Base URL 是否正确",
            )
        except Exception as e:
            logger.error("Provider test failed for %s: %s", provider_id, e)
            return ProviderTestResult(
                provider_id=provider_id, status="error", error_message="测试失败，请检查服务商配置"
            )

    # ========== 远程模型获取 ==========

    def _build_provider_headers(self, provider: LLMProviderConfig) -> Dict[str, str]:
        """构建 provider 请求头"""
        headers = {
            "Authorization": f"Bearer {provider.api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        # Kimi Coding API 需要特定的 User-Agent
        if "kimi.com/coding" in provider.base_url:
            headers["User-Agent"] = "KimiCLI/1.16.0"
        if provider.custom_headers:
            headers.update(provider.custom_headers)
        return headers

    @classmethod
    def _infer_model_defaults(cls, provider_type: str, model_type: str = "chat") -> Dict[str, Any]:
        """根据接口格式类型和模型用途推断模型默认参数

        不再硬编码任何模型映射，只按接口格式给保守默认值。
        """
        if model_type == "embedding":
            # embedding 模型不需要对话能力，上下文给 8192 作为常见默认值
            return {"max_context_size": 8192, "capabilities": []}

        if provider_type == "anthropic_messages":
            return {"max_context_size": 200000, "capabilities": ["thinking", "image_in"]}
        elif provider_type == "openai_responses":
            return {
                "max_context_size": 128000,
                "capabilities": ["thinking", "image_in", "always_thinking"],
            }
        else:
            # openai_chat_completions 及兜底
            return {"max_context_size": 128000, "capabilities": ["thinking", "image_in"]}

    async def fetch_remote_models(self, user_id: str, provider_id: str) -> "FetchModelsResult":
        """从 provider API 获取可用模型列表"""
        import httpx

        provider = self.get_provider_with_key(user_id, provider_id)
        if not provider:
            return FetchModelsResult(
                provider_id=provider_id,
                success=False,
                error_message=f"服务商 '{provider_id}' 不存在",
            )

        headers = self._build_provider_headers(provider)

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{provider.base_url}/models",
                    headers=headers,
                )

                if resp.status_code != 200:
                    status = resp.status_code
                    if status == 404:
                        msg = "该服务商不支持获取模型列表，请手动添加模型"
                        unsupported = True
                    elif status in (401, 403):
                        msg = "API Key 无效或无权限，请检查服务商密钥配置"
                        unsupported = False
                    else:
                        msg = f"服务商返回错误（状态码 {status}），请检查配置"
                        unsupported = False
                    return FetchModelsResult(
                        provider_id=provider_id,
                        success=False,
                        unsupported=unsupported,
                        error_message=msg,
                    )

                data = resp.json()
                raw_models = data.get("data", [])
                models = []
                for m in raw_models:
                    model_id = m.get("id", "").strip()
                    if not model_id:
                        continue
                    # 解析 context_length（不同厂商字段名可能不同）
                    ctx_len = m.get("context_length")
                    if ctx_len is None:
                        ctx_len = m.get("max_context_length")
                    if ctx_len is not None:
                        try:
                            ctx_len = int(ctx_len)
                        except (ValueError, TypeError):
                            ctx_len = None
                    models.append(
                        RemoteModelInfo(
                            model_name=model_id,
                            owned_by=m.get("owned_by"),
                            display_name=m.get("display_name") or m.get("name"),
                            context_length=ctx_len,
                            supports_reasoning=m.get("supports_reasoning"),
                            supports_image_in=m.get("supports_image_in"),
                            supports_video_in=m.get("supports_video_in"),
                        )
                    )

                return FetchModelsResult(
                    provider_id=provider_id,
                    models=models,
                    success=True,
                )

        except httpx.TimeoutException:
            return FetchModelsResult(
                provider_id=provider_id,
                success=False,
                error_message="连接超时",
            )
        except Exception as e:
            logger.error("Fetch models failed for %s: %s", provider_id, e)
            return FetchModelsResult(
                provider_id=provider_id,
                success=False,
                error_message="获取模型列表失败，请检查服务商配置",
            )

    def batch_create_models(
        self,
        user_id: str,
        provider_id: str,
        models: List[RemoteModelInfo],
    ) -> List[LLMModelConfig]:
        """批量创建模型（幂等，已存在的跳过）

        优先使用从 /v1/models 获取的上下文长度和能力信息，
        如果厂商不返回则 fallback 到接口类型默认值。
        """
        provider = self._storage.get_provider(user_id, provider_id)
        if not provider:
            raise ValueError(f"Provider '{provider_id}' not found")

        provider_type = provider.get("type", "openai_chat_completions")
        type_defaults = self._infer_model_defaults(provider_type)
        created = []

        for rm in models:
            model_name = rm.model_name
            model_id = f"{provider_id}-{model_name}"

            # 跳过已存在的
            existing = self._storage.get_model(user_id, model_id)
            if existing:
                created.append(self._dict_to_model_config(existing))
                continue

            # 优先使用 /v1/models 返回的上下文长度
            max_context = (
                rm.context_length
                if rm.context_length is not None
                else type_defaults["max_context_size"]
            )

            # 根据 /v1/models 返回的能力标记构建 capabilities
            capabilities = list(type_defaults["capabilities"])
            if rm.supports_reasoning is not None:
                if rm.supports_reasoning and "thinking" not in capabilities:
                    capabilities.append("thinking")
                elif not rm.supports_reasoning and "thinking" in capabilities:
                    capabilities.remove("thinking")
            if rm.supports_image_in is not None:
                if rm.supports_image_in and "image_in" not in capabilities:
                    capabilities.append("image_in")
                elif not rm.supports_image_in and "image_in" in capabilities:
                    capabilities.remove("image_in")

            display = rm.display_name or f"{model_name} ({provider_id})"
            model_data = LLMModelConfig(
                id=model_id,
                name=display,
                provider=provider_id,
                model=model_name,
                max_context_size=max_context,
                capabilities=capabilities,
                enabled=True,
                is_default=False,
            )
            try:
                result = self.create_model(user_id, model_data)
                created.append(result)
            except Exception as e:
                logger.warning("批量创建模型 '%s' 失败: %s", model_id, e)

        return created

    # ========== Embedding 维度探测 ==========

    async def probe_embedding_dimension(
        self,
        user_id: str,
        provider_id: str,
        model: str,
    ) -> int:
        """通过发送真实 embedding 请求探测向量维度

        使用 input="test" 发送一次请求，从返回的向量长度获取 dimension。
        """
        import httpx

        provider = self.get_provider_with_key(user_id, provider_id)
        if not provider:
            raise ValueError(f"Provider '{provider_id}' 不存在")

        api_key = provider.api_key.get_secret_value()
        if not api_key:
            raise ValueError(f"Provider '{provider_id}' 的 API Key 未设置")

        base_url = provider.base_url
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": model, "input": "test"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{base_url}/embeddings",
                    json=payload,
                    headers=headers,
                )
                if resp.status_code != 200:
                    body = resp.text[:500]
                    raise ValueError(f"探测请求失败 ({resp.status_code}): {body}")

                data = resp.json()
                embeddings = data.get("data", [])
                if not embeddings:
                    raise ValueError("探测响应中无 embedding 数据")

                dimension = len(embeddings[0].get("embedding", []))
                if dimension <= 0:
                    raise ValueError("探测返回的维度无效")

                logger.info("Embedding 维度探测成功: %s/%s = %s", provider_id, model, dimension)
                return dimension
        except httpx.TimeoutException:
            raise ValueError("探测请求超时，请检查网络连接或手动填写维度")
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"维度探测失败: {e}")

    # ========== 内部工具方法 ==========

    def _select_default_model_id(
        self,
        data: Dict[str, Any],
        *,
        model_type: str = "chat",
    ) -> Optional[str]:
        enabled_provider_ids = []
        default_provider_id = None

        for provider in data.get("providers", []):
            if not provider.get("enabled", True):
                continue

            provider_id = provider.get("id")
            if not provider_id:
                continue

            enabled_provider_ids.append(provider_id)
            if provider.get("is_default") and default_provider_id is None:
                default_provider_id = provider_id

        explicit_default = (
            data.get("default_embedding_model")
            if model_type == "embedding"
            else data.get("default_chat_model") or data.get("default_model")
        )

        enabled_models = [
            model
            for model in data.get("models", [])
            if model.get("enabled", True)
            and model.get("id")
            and model.get("provider") in enabled_provider_ids
            and str(model.get("model_type") or "chat") == model_type
        ]

        enabled_model_ids = {str(model.get("id")) for model in enabled_models if model.get("id")}

        if explicit_default in enabled_model_ids:
            return str(explicit_default)

        for model in enabled_models:
            if model.get("is_default"):
                return model["id"]

        if default_provider_id:
            for model in enabled_models:
                if model.get("provider") == default_provider_id:
                    return model["id"]

        if enabled_models:
            return enabled_models[0]["id"]

        return None

    def _validate_default_model_id(
        self,
        data: Dict[str, Any],
        model_id: Optional[str],
        *,
        expected_model_type: str,
    ) -> Optional[str]:
        if model_id is None:
            return None
        normalized = str(model_id).strip()
        if not normalized:
            return None

        for model in data.get("models", []):
            if (
                model.get("id") == normalized
                and model.get("enabled", True)
                and str(model.get("model_type") or "chat") == expected_model_type
            ):
                return normalized

        raise ValueError(f"模型不存在、未启用，或不属于 {expected_model_type} 类型: {normalized}")

    def _coerce_configured_default_model_id(
        self,
        data: Dict[str, Any],
        model_id: Optional[str],
        *,
        expected_model_type: str,
    ) -> Optional[str]:
        try:
            return self._validate_default_model_id(
                data,
                model_id,
                expected_model_type=expected_model_type,
            )
        except ValueError:
            return None

    def _dict_to_provider_config(self, data: Dict[str, Any]) -> LLMProviderConfig:
        """字典转换为 Provider Pydantic 模型"""
        api_key = data.get("api_key", "")

        # 如果 api_key 是明文，需要脱敏
        if api_key and not api_key.startswith("***"):
            api_key = mask_api_key(api_key)

        kwargs: Dict[str, Any] = {
            "id": data["id"],
            "name": data["name"],
            "type": data["type"],
            "base_url": data["base_url"],
            "api_key": SecretStr(api_key),
            "custom_headers": data.get("custom_headers", {}),
            "reasoning_key": data.get("reasoning_key"),
            "reasoning_format": data.get("reasoning_format"),
            "enabled": data.get("enabled", True),
            "is_default": data.get("is_default", False),
            "description": data.get("description"),
        }
        created_at = self._parse_datetime(data.get("created_at"))
        if created_at is not None:
            kwargs["created_at"] = created_at
        updated_at = self._parse_datetime(data.get("updated_at"))
        if updated_at is not None:
            kwargs["updated_at"] = updated_at
        return LLMProviderConfig(**kwargs)

    def _dict_to_model_config(self, data: Dict[str, Any]) -> LLMModelConfig:
        """字典转换为 Model Pydantic 模型"""
        # 处理 capabilities 字段（可能是字符串、列表或集合）
        capabilities = data.get("capabilities", [])
        if isinstance(capabilities, str):
            # 如果是字符串（如数据库返回的集合字符串表示），解析为集合
            try:
                # 处理形如 "{'image_in', 'video_in'}" 或 "['image_in', 'video_in']" 的字符串
                import ast

                capabilities = ast.literal_eval(capabilities)
                if isinstance(capabilities, (list, set)):
                    capabilities = list(capabilities)
                else:
                    capabilities = [capabilities]
            except (ValueError, SyntaxError):
                capabilities = []
        elif isinstance(capabilities, set):
            capabilities = list(capabilities)
        elif not isinstance(capabilities, list):
            capabilities = []

        kwargs: Dict[str, Any] = {
            "id": data["id"],
            "name": data["name"],
            "provider": data["provider"],
            "model": data["model"],
            "model_type": data.get("model_type", "chat"),
            "dimension": data.get("dimension"),
            "max_context_size": data.get("max_context_size", 128000),
            "capabilities": capabilities,
            "enabled": data.get("enabled", True),
            "is_default": data.get("is_default", False),
            "description": data.get("description"),
        }
        created_at = self._parse_datetime(data.get("created_at"))
        if created_at is not None:
            kwargs["created_at"] = created_at
        updated_at = self._parse_datetime(data.get("updated_at"))
        if updated_at is not None:
            kwargs["updated_at"] = updated_at
        return LLMModelConfig(**kwargs)

    def _parse_datetime(self, value: Any) -> Any:
        """解析时间字符串，失败或空值返回 None"""
        if not value:
            return None

        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None

        return value


# 全局服务实例
llm_config_service = LLMConfigService()


def get_llm_config_service() -> LLMConfigService:
    """获取 LLM 配置服务实例"""
    return llm_config_service
