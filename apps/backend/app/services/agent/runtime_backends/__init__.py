"""
Agent runtime backends。
"""

from importlib import import_module

from .base import (
    AgentRuntimeBackend,
    AgentRuntimeEvent,
    AgentRuntimeSession,
    RuntimeSessionCreateSpec,
)

__all__ = [
    "AgentRuntimeBackend",
    "AgentRuntimeEvent",
    "AgentRuntimeSession",
    "RuntimeSessionCreateSpec",
    "AiasysRuntimeBackend",
    "AiasysRuntimeSession",
    "get_backend",
]


_RUNTIME_EXPORTS = {
    "AiasysRuntimeBackend": (f"{__name__}.aiasys.backend", "AiasysRuntimeBackend"),
    "AiasysRuntimeSession": (f"{__name__}.aiasys.session", "AiasysRuntimeSession"),
    "AcpClientRuntimeBackend": (f"{__name__}.acp_client.backend", "AcpClientRuntimeBackend"),
    "AcpClientRuntimeSession": (f"{__name__}.acp_client.session", "AcpClientRuntimeSession"),
}

_BACKEND_CLASS_NAMES = {
    "aiasys": "AiasysRuntimeBackend",
    "acp_client": "AcpClientRuntimeBackend",
}


def __getattr__(name: str):
    export = _RUNTIME_EXPORTS.get(name)
    if export is not None:
        module_name, symbol_name = export
        module = import_module(module_name)
        return getattr(module, symbol_name)
    raise AttributeError(name)


def get_backend(name: str = "aiasys") -> AgentRuntimeBackend:
    normalized_name = str(name or "aiasys").strip().lower()
    backend_class_name = _BACKEND_CLASS_NAMES.get(normalized_name)
    if backend_class_name is None:
        raise ValueError(f"Unknown runtime backend: {name}")

    backend_class = __getattr__(backend_class_name)
    return backend_class()
