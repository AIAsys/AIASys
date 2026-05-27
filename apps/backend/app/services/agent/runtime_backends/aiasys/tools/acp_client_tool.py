"""ACP Client Tool — 让 AIASys 原生 Agent 在对话中驱动受控的 ACP Agent 预设。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import tomli_w

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.agent.runtime_backends.acp_client.session import AcpClientRuntimeSession

logger = logging.getLogger(__name__)

_COPILOT_ACP_ARGS = ["--acp", "--stdio"]

_PARAMETERS = {
    "type": "object",
    "properties": {
        "agent_command": {
            "type": "string",
            "description": (
                "外部 ACP Agent 预设。目前后端仅收口支持 Codex ACP "
                "('codex' / 'codex-acp') 与 Copilot ACP ('copilot')。"
            ),
        },
        "agent_args": {
            "type": "array",
            "items": {"type": "string"},
            "description": "外部 ACP Agent 的启动参数。当前仅 Copilot ACP 允许默认 ['--acp', '--stdio']。",
        },
        "task": {
            "type": "string",
            "description": "要交给外部 ACP Agent 执行的具体任务描述",
        },
        "working_directory": {
            "type": "string",
            "description": "外部 ACP Agent 的工作目录（可选，默认使用当前任务会话 session_root）",
        },
    },
    "required": ["agent_command", "task"],
}


def _normalize_agent_args(raw_args: Any) -> list[str]:
    if raw_args is None:
        return []
    if isinstance(raw_args, list):
        return [str(item) for item in raw_args]
    if isinstance(raw_args, tuple):
        return [str(item) for item in raw_args]
    if isinstance(raw_args, str) and raw_args.strip():
        return [raw_args.strip()]
    return []


def _resolve_working_directory(
    ctx: dict[str, Any],
    raw_working_directory: Any,
) -> Path:
    candidate = raw_working_directory or ctx.get("session_root") or ctx.get("workspace") or "."
    return Path(str(candidate)).resolve()


def _resolve_acp_launcher(command: str, args: list[str]) -> tuple[str, list[str]]:
    """把 tool 层输入收口到当前确认支持的 ACP adapter。"""
    normalized_command = command.strip()
    command_name = Path(normalized_command).name.lower()

    if command_name in {"codex", "codex-acp"}:
        if args:
            raise ValueError("Codex ACP 预设不支持自定义 agent_args。")
        resolved_command = normalized_command if command_name == "codex-acp" else "codex-acp"
        return resolved_command, []

    if command_name == "copilot":
        if args and args != _COPILOT_ACP_ARGS:
            raise ValueError("Copilot ACP 预设仅支持默认参数 ['--acp', '--stdio']。")
        return normalized_command, list(args or _COPILOT_ACP_ARGS)

    raise ValueError(
        "当前 AIASys ACP 入口仅支持 Codex ACP ('codex' / 'codex-acp') "
        "与 Copilot ACP ('copilot')。"
    )


class AcpClientTool(AiasysTool):
    """通过 ACP 协议调用受控的外部 Agent 预设并返回结果。"""

    name = "CallExternalAgent"
    description = (
        "调用一个受控的外部 ACP Agent 来执行特定任务。"
        "当前后端默认收口支持 Codex ACP，并保持任务级工作目录与 MCP 上下文。"
    )
    parameters = _PARAMETERS
    dangerous = True

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        ctx = ctx or {}
        command = str(kwargs.get("agent_command") or "").strip()
        args = _normalize_agent_args(kwargs.get("agent_args"))
        task = str(kwargs.get("task") or "").strip()
        cwd = _resolve_working_directory(ctx, kwargs.get("working_directory"))

        if not command:
            return ToolResult(content="缺少 agent_command 参数", is_error=True)
        if not task:
            return ToolResult(content="缺少 task 参数", is_error=True)

        try:
            resolved_command, resolved_args = _resolve_acp_launcher(command, args)
        except ValueError as exc:
            return ToolResult(content=str(exc), is_error=True)

        logger.info(
            "CallExternalAgent: command=%s args=%s cwd=%s task=%s...",
            resolved_command,
            resolved_args,
            cwd,
            task[:80],
        )

        # 构造一个最小 spec 来创建 ACP Client session
        from app.core.workspace_path import WorkspacePath
        from app.services.agent.models.llm_config import AiasysLlmConfig, LoopControl
        from app.services.agent.runtime_backends.base import RuntimeSessionCreateSpec

        agent_dir = cwd / ".acp_agent"
        agent_dir.mkdir(parents=True, exist_ok=True)
        agent_file = agent_dir / "agent.toml"
        agent_file.write_text(
            tomli_w.dumps({"version": 1, "agent": {"name": "acp-agent", "tools": []}}),
            encoding="utf-8",
        )

        spec = RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(cwd)),
            session_id=f"acp-client-{id(self)}-{int(asyncio.get_running_loop().time() * 1000)}",
            user_id="",
            config=AiasysLlmConfig(
                default_model="", providers={}, models={}, loop_control=LoopControl()
            ),
            agent_file=agent_file,
            skills_dir=None,
            mcp_configs=ctx.get("mcp_configs"),
            yolo=False,
            memory_enabled=False,  # ACP 外部 Agent 不需要 AIASys memory
        )

        session = AcpClientRuntimeSession(
            spec=spec,
            acp_command=resolved_command,
            acp_args=resolved_args,
        )

        try:
            result_parts: list[str] = []
            async for event in session.prompt(task):
                if event.kind == "content" and event.text:
                    result_parts.append(event.text)
                elif event.kind == "tool_call":
                    result_parts.append(f"\n[External tool call: {event.tool_name}]\n")
                elif event.kind == "tool_result":
                    result_parts.append(f"[External tool result: {event.content[:200]}...]\n")

            result_text = "".join(result_parts)
            if not result_text.strip():
                return ToolResult(content="外部 Agent 未返回有效内容", is_error=True)
            return ToolResult(content=result_text)
        except Exception as exc:
            logger.exception("CallExternalAgent failed")
            return ToolResult(content=f"调用外部 Agent 失败: {exc}", is_error=True)
        finally:
            await session.close()
