"""Provider 注册中心。

废弃 create_llm_client() 中的 if-else 链，改为显式注册模式。
每个 client 文件在底部自注册，新增 provider 只需新建文件 + 一行 register()。
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseLlmClient
from .capabilities import ProviderCapabilities

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Provider 注册中心。

    使用方式：
        # 在 client 文件中注册
        ProviderRegistry.register("openai_chat_completions", OpenAIChatClient, caps)

        # 创建 client
        client = ProviderRegistry.create("openai_chat_completions", api_key=..., ...)

        # 查询能力
        caps = ProviderRegistry.get_capabilities("openai_chat_completions")
    """

    _clients: dict[str, type[BaseLlmClient]] = {}
    _capabilities: dict[str, ProviderCapabilities] = {}

    @classmethod
    def register(
        cls,
        protocol: str,
        client_cls: type[BaseLlmClient],
        capabilities: ProviderCapabilities,
    ) -> None:
        """注册一个 provider 协议及其 client 类和能力声明。

        Args:
            protocol: 协议标识符，如 "openai_chat_completions"
            client_cls: BaseLlmClient 子类
            capabilities: 该 provider 的能力声明
        """
        protocol = protocol.strip().lower()
        cls._clients[protocol] = client_cls
        cls._capabilities[protocol] = capabilities
        logger.debug("ProviderRegistry: registered protocol %r → %s", protocol, client_cls.__name__)

    @classmethod
    def create(cls, protocol: str, **kwargs: Any) -> BaseLlmClient:
        """根据协议标识符创建对应的 client 实例。

        自动过滤 kwargs，只传递 client 构造函数接受的参数。

        Args:
            protocol: 协议标识符
            **kwargs: 传递给 client 构造函数的参数

        Returns:
            BaseLlmClient 实例

        Raises:
            ValueError: 如果 protocol 未注册
        """
        import inspect

        protocol = protocol.strip().lower()
        client_cls = cls._clients.get(protocol)
        if client_cls is None:
            registered = ", ".join(cls._clients.keys()) or "(none)"
            raise ValueError(
                f"Unsupported LLM protocol: {protocol}. Registered protocols: {registered}"
            )
        # 只传 client 构造函数接受的参数
        sig = inspect.signature(client_cls.__init__)
        valid_params = {k: v for k, v in kwargs.items() if k in sig.parameters}
        return client_cls(**valid_params)

    @classmethod
    def get_capabilities(cls, protocol: str) -> ProviderCapabilities:
        """获取指定协议的能力声明。

        Args:
            protocol: 协议标识符

        Returns:
            ProviderCapabilities 实例。如果 protocol 未注册，返回默认的 ProviderCapabilities。
        """
        protocol = protocol.strip().lower()
        return cls._capabilities.get(protocol, ProviderCapabilities())

    @classmethod
    def is_registered(cls, protocol: str) -> bool:
        """检查指定协议是否已注册。"""
        return protocol.strip().lower() in cls._clients

    @classmethod
    def list_protocols(cls) -> list[str]:
        """列出所有已注册的协议标识符。"""
        return sorted(cls._clients.keys())
