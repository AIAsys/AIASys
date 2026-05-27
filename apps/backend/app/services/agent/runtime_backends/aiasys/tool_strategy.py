"""动态工具加载策略 —— 根据模型/协议自动选择优化路径。

Anthropic 原生端点 + Claude 4.5+ → DeferredToolStrategy (defer_loading + tool_search)
其他模型 (Kimi/GPT/Gemini/...) → SearchToolStrategy (tool_search 渐进式发现)
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import Any

from .tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

# Claude 4.5+ 模型版本检测
_SUPPORTS_TOOL_SEARCH_VERSION: tuple[int, int] = (4, 5)
_CLAUDE_VERSION_RE = re.compile(r"claude[.-](?:sonnet|opus|haiku)[.-](\d+)[.-](\d{1,2})(?!\d)")


def _is_claude_4_5_plus(model: str) -> bool:
    """检测是否为 Claude 4.5+ 模型（支持 tool_search）。"""
    match = _CLAUDE_VERSION_RE.search(model.lower())
    if not match:
        return False
    major = int(match.group(1))
    minor = int(match.group(2))
    return (major, minor) >= _SUPPORTS_TOOL_SEARCH_VERSION


def _is_native_anthropic_endpoint(base_url: str) -> bool:
    if not base_url:
        return True
    from urllib.parse import urlparse

    netloc = urlparse(base_url.rstrip("/")).netloc.lower()
    return netloc == "api.anthropic.com" or netloc.endswith(".anthropic.com")


def _is_anthropic_client(client: Any) -> bool:
    from .llm_clients.anthropic_client import AnthropicChatClient

    return isinstance(client, AnthropicChatClient)


class ToolStrategy(ABC):
    """工具加载策略抽象基类。"""

    @abstractmethod
    def prepare_tools(self, registry: ToolRegistry) -> list[dict[str, Any]]:
        """返回应发给 LLM 的工具 schema 列表。"""

    def prepare_tools_filtered(
        self,
        registry: ToolRegistry,
        allowed_names: set[str],
    ) -> list[dict[str, Any]]:
        """返回过滤后的工具 schema 列表。"""
        allowed = {str(name or "").strip() for name in allowed_names if str(name or "").strip()}
        return [
            schema
            for schema in self.prepare_tools(registry)
            if schema.get("function", {}).get("name") in allowed
        ]

    def setup_registry(self, registry: ToolRegistry) -> None:
        """在 session 初始化时调用，允许策略向 registry 注册额外工具。"""

    def get_system_prompt_additions(self) -> str:
        """返回应追加到 system prompt 的指令文本。"""
        return ""

    @property
    def strategy_name(self) -> str:
        return self.__class__.__name__


class PassthroughStrategy(ToolStrategy):
    """全量直通策略 —— 当前默认行为，所有工具不加过滤发送。"""

    def prepare_tools(self, registry: ToolRegistry) -> list[dict[str, Any]]:
        return registry.get_openai_schema()

    def prepare_tools_filtered(
        self,
        registry: ToolRegistry,
        allowed_names: set[str],
    ) -> list[dict[str, Any]]:
        return registry.get_openai_schema_filtered(allowed_names)

    @property
    def strategy_name(self) -> str:
        return "passthrough"


def detect_tool_strategy(
    client: Any,
    model_config: Any | None = None,
    explicit_strategy: str | None = None,
) -> ToolStrategy:
    """根据 LLM 客户端和模型配置自动选择工具加载策略。

    优先级：
    1. explicit_strategy 参数（来自动态 agent manifest，非 "auto" 时）
    2. Anthropic + 原生端点 + Claude 4.5+ → deferred
    3. 其他 → search（tool_search 渐进式发现）
    """
    # 1. explicit_strategy（来自动态 agent manifest）
    if explicit_strategy and explicit_strategy not in ("auto", ""):
        strategy = explicit_strategy.strip().lower()
        if strategy == "deferred":
            logger.info("ToolStrategy: explicit strategy → deferred")
            from .tool_strategy_deferred import DeferredToolStrategy

            return DeferredToolStrategy(client)
        if strategy == "search":
            logger.info("ToolStrategy: explicit strategy → search")
            from .tool_strategy_search import SearchToolStrategy

            return SearchToolStrategy()
        if strategy == "passthrough":
            logger.info("ToolStrategy: explicit strategy → passthrough")
            return PassthroughStrategy()
        logger.warning(
            "ToolStrategy: unknown explicit strategy %r, falling through", explicit_strategy
        )

    if _is_anthropic_client(client):
        base_url = getattr(client, "_base_url", "") or ""
        model = getattr(client, "model", "") or ""
        if _is_native_anthropic_endpoint(base_url) and _is_claude_4_5_plus(model):
            logger.info("ToolStrategy: detected Anthropic + Claude 4.5+ → deferred")
            from .tool_strategy_deferred import DeferredToolStrategy

            return DeferredToolStrategy(client)

    # 其他模型（Kimi, GPT, Gemini, Grok...）→ tool_search 渐进式发现
    logger.info("ToolStrategy: non-Anthropic or older model → search")
    from .tool_strategy_search import SearchToolStrategy

    return SearchToolStrategy()
