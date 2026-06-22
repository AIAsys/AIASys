"""ACP Client runtime backend — 让 AIASys 通过 ACP 协议调用外部 Agent。"""

from __future__ import annotations

import logging
from typing import Any

from app.utils.path_utils import as_system_path

from ..base import RuntimeSessionCreateSpec
from .session import AcpClientRuntimeSession

logger = logging.getLogger(__name__)


def _resolve_acp_command(agent_manifest: dict[str, Any]) -> str:
    """从 agent manifest 解析 ACP 启动命令。"""
    raw = agent_manifest.get("acp_command")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    # 默认尝试常见 ACP adapter 命令
    return "codex-acp"


def _resolve_acp_args(agent_manifest: dict[str, Any]) -> list[str]:
    """从 agent manifest 解析 ACP 启动参数。"""
    raw = agent_manifest.get("acp_args")
    if isinstance(raw, list):
        return [str(a) for a in raw]
    if isinstance(raw, str) and raw.strip():
        return raw.strip().split()
    return []


class AcpClientRuntimeBackend:
    """通过 ACP 协议驱动外部 Agent 的 runtime backend。"""

    async def create_session(
        self,
        spec: RuntimeSessionCreateSpec,
    ) -> AcpClientRuntimeSession:
        agent_manifest = _load_agent_manifest(spec.agent_file)
        command = _resolve_acp_command(agent_manifest)
        args = _resolve_acp_args(agent_manifest)
        logger.info(
            "Creating ACP client session %s with command=%s args=%s",
            spec.session_id,
            command,
            args,
        )
        return AcpClientRuntimeSession(
            spec=spec,
            acp_command=command,
            acp_args=args,
        )


def _load_agent_manifest(agent_file: Any) -> dict[str, Any]:
    import tomllib

    if hasattr(agent_file, "read_text"):
        data = tomllib.loads(agent_file.read_text(encoding="utf-8")) or {}
    elif isinstance(agent_file, str):
        from pathlib import Path

        data = tomllib.loads(Path(as_system_path(agent_file)).read_text(encoding="utf-8")) or {}
    else:
        data = {}
    return data.get("agent") or {}
