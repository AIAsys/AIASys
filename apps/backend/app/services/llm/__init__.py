"""
LLM 相关服务模块
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.services.llm.llm_config_service import (
    LLMConfigService,
    get_llm_config_service,
)

if TYPE_CHECKING:
    from app.services.llm.mcp_config_service import MCPConfigService
    from app.services.llm.mcp_session_service import MCPSessionService

__all__ = [
    "LLMConfigService",
    "get_llm_config_service",
    "MCPConfigService",
    "get_auto_attach_system_mcps",
    "get_mcp_config_service",
    "get_system_default_mcps",
    "MCPSessionService",
    "get_mcp_session_service",
]


def __getattr__(name: str) -> Any:
    if name in {
        "MCPConfigService",
        "get_auto_attach_system_mcps",
        "get_mcp_config_service",
        "get_system_default_mcps",
    }:
        from . import mcp_config_service as module

        return getattr(module, name)

    if name in {"MCPSessionService", "get_mcp_session_service"}:
        from . import mcp_session_service as module

        return getattr(module, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
