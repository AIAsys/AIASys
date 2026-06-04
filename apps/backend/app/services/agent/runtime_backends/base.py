"""
Agent runtime backend 抽象。

当前目标：
- 让 AIASys 业务层依赖自己的 runtime 接口，而不是直接吃上游 SDK / CLI 的漂移
- 当前已收口 Session 创建链路，并继续把 prompt 事件流规整成 AIASys 自己的 runtime event
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from app.core.tool_result import ToolResult
from app.core.workspace_path import WorkspacePath
from app.services.agent.models.llm_config import AiasysLlmConfig

if TYPE_CHECKING:
    from app.services.agent.runtime_backends.aiasys.tool_registry import ToolRegistry

RuntimeEventKind = Literal[
    "worker_lifecycle",
    "content",
    "tool_call",
    "tool_result",
    "subagent_content",
    "subagent_tool_call",
    "subagent_tool_result",
    "token_usage",
    "task_call_begin",
    "task_call_end",
    "data",
    "budget_limited",
    "budget_updated",
    "ask_user_request",
]

RuntimeContentType = Literal["text", "think"]
RuntimeLifecycleScope = Literal["host", "subagent"]
RuntimeLifecycleStatus = Literal["finished", "cancelled", "interrupted", "failed"]


@dataclass(slots=True, kw_only=True)
class AgentRuntimeEvent:
    """AIASys runtime 层对底层消息流的统一投影。"""

    kind: RuntimeEventKind
    content_type: RuntimeContentType | None = None
    text: str | None = None
    think: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    content: str | None = None
    is_error: bool | None = None
    scope: RuntimeLifecycleScope | None = None
    status: RuntimeLifecycleStatus | None = None
    reason: str | None = None
    task_tool_call_id: str | None = None
    parent_tool_call_id: str | None = None
    agent_id: str | None = None
    subagent_type: str | None = None
    subagent_name: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@runtime_checkable
class AgentRuntimeSession(Protocol):
    """AIASys 业务层需要的最小 runtime session 句柄。"""

    session_id: str
    mcp_configs: list | None

    async def prompt(
        self,
        user_input: str | list[dict],
        *,
        merge_wire_messages: bool = False,
    ) -> AsyncGenerator[AgentRuntimeEvent, None]: ...

    def cancel(self) -> None: ...

    async def close(self) -> None: ...

    async def __aenter__(self) -> "AgentRuntimeSession": ...

    async def __aexit__(self, *args: Any) -> None: ...


@dataclass(slots=True, kw_only=True)
class RuntimeSessionCreateSpec:
    """创建 runtime session 需要的显式参数。"""

    work_dir: WorkspacePath
    session_id: str
    user_id: str = ""  # 用户 ID，用于读取用户级配置
    config: AiasysLlmConfig
    agent_file: Path
    skills_dir: WorkspacePath | None
    mcp_configs: list | None
    yolo: bool
    # 子 Agent 继承模型字段
    is_subagent: bool = False
    parent_registry: "ToolRegistry | None" = None
    tool_policy: str = "inherit"  # inherit | allowlist | denylist
    fork_turns: int | None = None  # None=all, 0=none, N=last N turns
    fork_messages: list[dict[str, Any]] | None = None
    host_session_id: str | None = None
    parent_agent_id: str | None = None
    agent_path: str = "/root"
    agent_max_depth: int = 1
    allow_subagent_spawn: bool = False
    collaboration_policy: dict[str, Any] | None = None
    budget: Any | None = None
    memory_enabled: bool = True  # memory 功能开关，从 config.toml 读取


ToolStreamEventKind = Literal["event", "result"]


@dataclass(slots=True, kw_only=True)
class ToolStreamEvent:
    """流式工具调用过程中的事件或最终结果。

    - kind="event": 子 Agent / 流式工具产生的中间实时事件
    - kind="result": 工具调用的最终结果 (ToolResult)
    """

    kind: ToolStreamEventKind
    # 当 kind="event" 时，携带一个 AgentRuntimeEvent 作为中间事件
    runtime_event: AgentRuntimeEvent | None = None
    # 当 kind="result" 时，携带最终 ToolResult
    tool_result: ToolResult | None = None


class AgentRuntimeBackend(Protocol):
    """Agent runtime backend 协议。"""

    async def create_session(
        self,
        spec: RuntimeSessionCreateSpec,
    ) -> AgentRuntimeSession: ...
