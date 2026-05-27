"""
Tool Call Parser Registry

Client-side parsers that extract structured tool_calls from raw model output text.
Used when the model returns raw text without structured tool_calls (e.g. some
local VLLM deployments or non-OpenAI models).

Each parser is a standalone reimplementation of the corresponding VLLM parser's
non-streaming extract_tool_calls() logic. No VLLM dependency.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Type

logger = logging.getLogger(__name__)

# Type alias: (content_without_tool_calls, list_of_tool_call_dicts)
ParseResult = Tuple[Optional[str], Optional[List[Dict[str, Any]]]]


class ToolCallParser(ABC):
    """Base class for tool call parsers."""

    @abstractmethod
    def parse(self, text: str) -> ParseResult:
        """
        Parse raw model output text for tool calls.

        Returns:
            Tuple of (content, tool_calls) where:
            - content: text with tool call markup stripped, or None
            - tool_calls: list of tool call dicts, or None
        """
        raise NotImplementedError


PARSER_REGISTRY: Dict[str, Type[ToolCallParser]] = {}


def register_parser(name: str):
    """Decorator to register a parser class."""

    def decorator(cls: Type[ToolCallParser]) -> Type[ToolCallParser]:
        PARSER_REGISTRY[name] = cls
        return cls

    return decorator


def get_parser(name: str) -> ToolCallParser:
    """Get a parser instance by name."""
    if name not in PARSER_REGISTRY:
        available = sorted(PARSER_REGISTRY.keys())
        raise KeyError(f"Tool call parser '{name}' not found. Available: {available}")
    return PARSER_REGISTRY[name]()


def list_parsers() -> List[str]:
    """Return sorted list of registered parser names."""
    return sorted(PARSER_REGISTRY.keys())


from .deepseek_v3_1_parser import DeepSeekV31ToolCallParser  # noqa: E402, F401
from .deepseek_v3_parser import DeepSeekV3ToolCallParser  # noqa: E402, F401
from .glm45_parser import Glm45ToolCallParser  # noqa: E402, F401
from .glm47_parser import Glm47ToolCallParser  # noqa: E402, F401

# Import all parser modules to trigger registration via @register_parser decorators
from .hermes_parser import HermesToolCallParser  # noqa: E402, F401
from .kimi_k2_parser import KimiK2ToolCallParser  # noqa: E402, F401
from .llama_parser import LlamaToolCallParser  # noqa: E402, F401
from .longcat_parser import LongcatToolCallParser  # noqa: E402, F401
from .mistral_parser import MistralToolCallParser  # noqa: E402, F401
from .qwen3_coder_parser import Qwen3CoderToolCallParser  # noqa: E402, F401
from .qwen_parser import QwenToolCallParser  # noqa: E402, F401
