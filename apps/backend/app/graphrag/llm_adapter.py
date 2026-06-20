"""
GraphRAG LLM 客户端适配器
使用系统自有的 llm_clients 体系，不再依赖 kosong
"""

import logging
from typing import Any, Dict, List, Optional, Sequence

from app.services.agent.models.llm_config import LlmProviderConfig
from app.services.agent.runtime_backends.aiasys.llm_clients import (
    BaseLlmClient,
    create_llm_client,
)

logger = logging.getLogger(__name__)

_CODING_PROVIDER_MARKERS: tuple[str, ...] = (
    "kimi.com/coding",
    "/coding/",
)
_UNSUITABLE_MODEL_MARKERS: tuple[str, ...] = (
    "coding",
    "coder",
    "image",
    "speech",
    "audio",
    "asr",
    "tts",
    "whisper",
    "embedding",
    "rerank",
    "moderation",
)
_DEPRIORITIZED_MODEL_MARKERS: tuple[str, ...] = (
    "deep-research",
    "research",
    "character",
)
_PREFERRED_MODEL_MARKERS: tuple[str, ...] = (
    "qwen-max",
    "qwen-plus",
    "qwen-turbo",
    "qwen3",
    "deepseek",
    "glm",
    "gpt",
    "claude",
    "gemini",
    "moonshot",
    "chat",
    "instruct",
)


class GraphRAGLLMClient:
    """
    GraphRAG 的 LLM 客户端适配器

    适配 EntityExtractor 的接口要求:
    - achat(prompt: str) -> str
    - achat_messages(messages: List[Dict]) -> str
    """

    def __init__(self, client: BaseLlmClient, model: str):
        self.client = client
        self.model = model

    async def achat(self, prompt: str) -> str:
        """单次对话调用"""
        return await self._run_chat([{"role": "user", "content": prompt}])

    async def achat_messages(self, messages: List[Dict[str, str]]) -> str:
        """带历史记录的调用"""
        return await self._run_chat(messages)

    async def _run_chat(self, messages: List[Dict[str, Any]]) -> str:
        """统一调用 chat_stream 并收集文本响应。"""
        chunks: list[str] = []
        async for chunk in self.client.chat_stream(
            messages=messages,
            tools=None,
            temperature=None,
            max_tokens=None,
        ):
            if chunk.delta.content:
                chunks.append(chunk.delta.content)
        return "".join(chunks)

    async def aclose(self) -> None:
        await self.client.aclose()


# ==================== 从系统配置创建 ====================


def _normalize_model_identity(model: Any) -> str:
    values = [
        getattr(model, "id", ""),
        getattr(model, "name", ""),
        getattr(model, "model", ""),
        getattr(model, "description", "") or "",
    ]
    return " ".join(str(value).strip().lower() for value in values if str(value).strip())


def _provider_is_coding_only(provider: Any) -> bool:
    base_url = str(getattr(provider, "base_url", "") or "").lower()
    return any(marker in base_url for marker in _CODING_PROVIDER_MARKERS)


def _model_is_unsuitable_for_graphrag(model: Any) -> bool:
    identity = _normalize_model_identity(model)
    return any(marker in identity for marker in _UNSUITABLE_MODEL_MARKERS)


def _score_graphrag_model(model: Any) -> int:
    identity = _normalize_model_identity(model)
    score = 0
    if getattr(model, "is_default", False):
        score += 50
    if any(marker in identity for marker in _PREFERRED_MODEL_MARKERS):
        score += 20
    if any(marker in identity for marker in _DEPRIORITIZED_MODEL_MARKERS):
        score -= 10
    return score


def _pick_graphrag_model(models: Sequence[Any]) -> Any | None:
    suitable_models = [
        model
        for model in models
        if getattr(model, "enabled", True) and not _model_is_unsuitable_for_graphrag(model)
    ]
    if not suitable_models:
        return None
    return max(suitable_models, key=_score_graphrag_model)


async def create_llm_client_from_config(
    config_service=None, user_id: Optional[str] = None
) -> Optional[GraphRAGLLMClient]:
    """
    从系统 llm_config.json 创建客户端

    读取 config.toml 默认配置或 workspaces/{user_id}/global_workspace/.aiasys/llm_config.json
    """
    from app.services.llm import LLMConfigService

    if config_service is None:
        config_service = LLMConfigService()

    providers = config_service.list_providers(user_id, enabled_only=True)
    if not providers:
        return None

    provider_order = sorted(
        providers,
        key=lambda item: (
            0 if _provider_is_coding_only(item) else 1,
            1 if getattr(item, "is_default", False) else 0,
        ),
        reverse=True,
    )

    for provider in provider_order:
        if _provider_is_coding_only(provider):
            logger.info(
                "GraphRAG 跳过 coding-only provider: %s (%s)",
                getattr(provider, "id", "<unknown>"),
                getattr(provider, "base_url", ""),
            )
            continue

        models = config_service.list_models(
            user_id,
            enabled_only=True,
            provider_id=provider.id,
        )
        selected_model = _pick_graphrag_model(models)
        if selected_model is None:
            logger.info(
                "GraphRAG provider %s 没有找到适合文档抽取的 enabled 模型",
                provider.id,
            )
            continue

        provider_with_key = config_service.get_provider_with_key(user_id, provider.id)
        if not provider_with_key:
            logger.warning("GraphRAG provider %s 缺少可解密 API Key，已跳过", provider.id)
            continue

        api_key = provider_with_key.api_key.get_secret_value()
        if not api_key:
            logger.warning("GraphRAG provider %s API Key 为空，已跳过", provider.id)
            continue

        try:
            # 构造运行时 provider 配置
            runtime_provider = LlmProviderConfig(
                protocol=provider.type,
                base_url=provider.base_url,
                api_key=api_key,
            )
            client = create_llm_client(runtime_provider, selected_model.model)
        except Exception as e:
            logger.warning(
                "GraphRAG provider %s 创建 LLM client 失败: %s",
                provider.id,
                e,
            )
            continue

        return GraphRAGLLMClient(client, selected_model.model)

    logger.warning(
        "GraphRAG 没有找到可用的通用文本模型；请至少启用一个非 coding / 非 image / 非 speech 的 LLM 模型"
    )
    return None


# ==================== 快速测试配置 ====================


def create_llm_client_direct(
    provider_type: str, model: str, base_url: str, api_key: str
) -> Optional[GraphRAGLLMClient]:
    """直接创建客户端（用于测试，绕过系统配置）"""
    try:
        runtime_provider = LlmProviderConfig(
            protocol=provider_type,
            base_url=base_url,
            api_key=api_key,
        )
        client = create_llm_client(runtime_provider, model)
        return GraphRAGLLMClient(client, model)
    except Exception as e:
        logger.warning("Failed to create GraphRAG LLM client: %s", e, exc_info=True)
        return None
