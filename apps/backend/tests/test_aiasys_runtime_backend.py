from __future__ import annotations

import pytest
import tomli_w
from pathlib import Path

from app.core.workspace_path import WorkspacePath

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.models.session import SessionBudget, SessionMetadata, SessionPlanState
from app.services.agent.models.llm_config import AiasysLlmConfig, LlmModelConfig, LlmProviderConfig
from app.services.agent.runtime_backends import AiasysRuntimeBackend, RuntimeSessionCreateSpec, get_backend
from app.services.agent.runtime_backends.aiasys.backend import (
    _instantiate_tool,
    _resolve_model_id,
)
from app.services.agent.runtime_backends.aiasys.llm_clients.base import (
    LlmChunk,
    LlmDelta,
    LlmRequestOptions,
)
from app.services.agent.runtime_backends.aiasys.session import AiasysRuntimeSession
from app.services.agent.runtime_backends.aiasys.tool_registry import ToolRegistry


class _IndexRejectingMapping(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            raise KeyError(key)
        return super().__getitem__(key)


class _FakeStreamingClient:
    def __init__(self) -> None:
        self.calls: list[list[dict]] = []
        self.request_options: list[LlmRequestOptions | None] = []
        self.usages: list[dict[str, int]] = []
        self.closed = False

    async def chat_stream(self, messages, tools, temperature, max_tokens, request_options=None):
        del tools, temperature, max_tokens
        self.calls.append([dict(message) for message in messages])
        self.request_options.append(request_options)
        if len(self.calls) == 1:
            yield LlmChunk(
                delta=LlmDelta(content="分析中。"),
                finish_reason=None,
                usage=None,
            )
            usage = {"prompt_tokens": 3, "completion_tokens": 5}
            self.usages.append(usage)
            yield LlmChunk(
                delta=LlmDelta(
                    reasoning_content="先整理问题，再调用工具。",
                    tool_calls=[
                        {
                            "index": 0,
                            "id": "call-1",
                            "function": {
                                "name": "EchoTool",
                                "arguments": '{"text":"hello"}',
                            },
                        }
                    ],
                ),
                finish_reason="tool_calls",
                usage=usage,
            )
            return

        usage = {"prompt_tokens": 2, "completion_tokens": 4}
        self.usages.append(usage)
        yield LlmChunk(
            delta=LlmDelta(content="最终答案"),
            finish_reason="stop",
            usage=usage,
        )

    async def aclose(self) -> None:
        self.closed = True


class _SingleTurnClient:
    def __init__(self) -> None:
        self.calls: list[list[dict]] = []
        self.request_options: list[LlmRequestOptions | None] = []

    async def chat_stream(self, messages, tools, temperature, max_tokens, request_options=None):
        del tools, temperature, max_tokens
        self.calls.append([dict(message) for message in messages])
        self.request_options.append(request_options)
        yield LlmChunk(
            delta=LlmDelta(content="ok"),
            finish_reason="stop",
            usage={"prompt_tokens": 2, "completion_tokens": 1},
        )

    async def aclose(self) -> None:
        return None


class _CaptureToolsClient:
    def __init__(self) -> None:
        self.tool_names: list[str] = []

    async def chat_stream(self, messages, tools, temperature, max_tokens, request_options=None):
        del messages, temperature, max_tokens, request_options
        self.tool_names = [
            tool.get("function", {}).get("name")
            for tool in tools
            if tool.get("function", {}).get("name")
        ]
        yield LlmChunk(
            delta=LlmDelta(content="ok"),
            finish_reason="stop",
            usage={"prompt_tokens": 2, "completion_tokens": 1},
        )

    async def aclose(self) -> None:
        return None


class _EchoTool(AiasysTool):
    name = "EchoTool"
    description = "Echo tool"
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
        "required": ["text"],
    }

    async def invoke(self, ctx=None, **kwargs):
        del ctx
        return ToolResult(content=f"echo: {kwargs['text']}")


class _ImageTool(AiasysTool):
    name = "ImageTool"
    description = "Return an image"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def invoke(self, ctx=None, **kwargs):
        del ctx, kwargs
        return ToolResult(
            content=[
                {"type": "text", "text": "[image:/workspace/chart.png]"},
                {
                    "type": "image_url",
                    "image_url": {"url": "file:///workspace/chart.png"},
                    "source_path": "/workspace/chart.png",
                },
            ]
        )


class _ImageToolClient:
    """第一轮调用 ImageTool，第二轮 stop。"""

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    async def chat_stream(self, messages, tools, temperature, max_tokens, request_options=None):
        del tools, temperature, max_tokens, request_options
        self.calls.append([dict(message) for message in messages])
        if len(self.calls) == 1:
            yield LlmChunk(
                delta=LlmDelta(content="让我看看这张图"),
                finish_reason=None,
                usage=None,
            )
            yield LlmChunk(
                delta=LlmDelta(
                    tool_calls=[
                        {
                            "index": 0,
                            "id": "call-img",
                            "function": {"name": "ImageTool", "arguments": "{}"},
                        }
                    ]
                ),
                finish_reason="tool_calls",
                usage={"prompt_tokens": 3, "completion_tokens": 5},
            )
            return
        yield LlmChunk(
            delta=LlmDelta(content="看到了"),
            finish_reason="stop",
            usage={"prompt_tokens": 2, "completion_tokens": 1},
        )

    async def aclose(self) -> None:
        return None


class _McpEchoTool(AiasysTool):
    """模拟 MCP 工具，用于冲突检测测试。"""

    name = "EchoTool"
    description = "MCP echo tool"
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
        "required": ["text"],
    }
    is_mcp = True

    async def invoke(self, ctx=None, **kwargs):
        del ctx
        return ToolResult(content=f"mcp echo: {kwargs['text']}")


def _write_agent_files(tmp_path: Path) -> Path:
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("system prompt", encoding="utf-8")

    agent_file = tmp_path / "agent.toml"
    agent_file.write_text(
        tomli_w.dumps(
            {
                "version": 1,
                "agent": {
                    "name": "test-agent",
                    "model": "test-model",
                    "tools": ["tests.fake:IgnoredByRegistry"],
                    "system_prompt_path": "./prompt.md",
                },
            }
        ),
        encoding="utf-8",
    )
    return agent_file


def _write_agent_files_with_model(tmp_path: Path, model: str) -> Path:
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("system prompt", encoding="utf-8")

    agent_file = tmp_path / "agent.toml"
    agent_file.write_text(
        tomli_w.dumps(
            {
                "version": 1,
                "agent": {
                    "name": "test-agent",
                    "model": model,
                    "tools": ["tests.fake:IgnoredByRegistry"],
                    "system_prompt_path": "./prompt.md",
                },
            }
        ),
        encoding="utf-8",
    )
    return agent_file


def _contains_data_image(value) -> bool:
    if isinstance(value, str):
        return "data:image" in value
    if isinstance(value, dict):
        return any(_contains_data_image(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_data_image(item) for item in value)
    return False


def test_backend_model_resolution_falls_back_when_manifest_model_is_not_configured(
    tmp_path,
):
    agent_file = _write_agent_files_with_model(tmp_path, "krill-gpt-5.4")
    spec = RuntimeSessionCreateSpec(
        work_dir=WorkspacePath(str(tmp_path)),
        session_id="session-model-fallback",
        config=AiasysLlmConfig(
            default_model="kimi-kimi-for-coding",
            providers={
                "provider-1": LlmProviderConfig(
                    api_key="secret",
                    base_url="https://example.com/v1",
                )
            },
            models={
                "kimi-kimi-for-coding": LlmModelConfig(
                    provider="provider-1",
                    model="kimi-for-coding",
                    capabilities=["thinking"],
                )
            },
        ),
        agent_file=agent_file,
        skills_dir=None,
        mcp_configs=None,
        yolo=True,
    )

    assert _resolve_model_id(spec, {"model": "krill-gpt-5.4"}) == "kimi-kimi-for-coding"


async def test_runtime_session_model_resolution_uses_configured_default_for_request_options(
    tmp_path,
):
    agent_file = _write_agent_files_with_model(tmp_path, "krill-gpt-5.4")
    registry = ToolRegistry()
    client = _SingleTurnClient()

    session = AiasysRuntimeSession(
        RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id="session-model-fallback",
            config=AiasysLlmConfig(
                default_model="kimi-kimi-for-coding",
                providers={
                    "provider-1": LlmProviderConfig(
                        api_key="secret",
                        base_url="https://example.com/v1",
                    )
                },
                models={
                    "kimi-kimi-for-coding": LlmModelConfig(
                        provider="provider-1",
                        model="kimi-for-coding",
                        capabilities=["thinking"],
                    )
                },
            ),
            agent_file=agent_file,
            skills_dir=None,
            mcp_configs=None,
            yolo=True,
        ),
        client,
        registry,
    )

    events = [event async for event in session.prompt("hello")]

    assert [event.kind for event in events] == ["content", "token_usage"]
    assert session._resolve_model_id() == "kimi-kimi-for-coding"
    assert client.request_options[0] is not None
    assert client.request_options[0].thinking_enabled is True
    await session.close()


async def test_runtime_session_blocks_prompt_when_session_budget_exhausted(tmp_path):
    agent_file = _write_agent_files(tmp_path)
    session_id = "session-budget-blocked"
    (tmp_path / ".aiasys" / "session" / session_id).mkdir(parents=True)
    (tmp_path / "metadata.json").write_text(
        SessionMetadata(
            session_id=session_id,
            user_id="local_default",
            budget=SessionBudget(
                token_budget=10,
                tokens_used=10,
                status="budget_limited",
            ),
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    registry = ToolRegistry()
    client = _SingleTurnClient()

    session = AiasysRuntimeSession(
        RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id=session_id,
            config=AiasysLlmConfig(
                default_model="test-model",
                providers={
                    "provider-1": LlmProviderConfig(
                        api_key="secret",
                        base_url="https://example.com/v1",
                    )
                },
                models={
                    "test-model": LlmModelConfig(
                        provider="provider-1",
                        model="test-model-remote",
                    )
                },
            ),
            agent_file=agent_file,
            skills_dir=None,
            mcp_configs=None,
            yolo=True,
        ),
        client,
        registry,
    )

    events = [event async for event in session.prompt("hello")]

    assert client.calls == []
    assert [event.kind for event in events] == ["budget_limited", "budget_updated"]
    assert "已用 10 / 10 tokens" in (events[0].text or "")
    await session.close()


async def test_runtime_session_filters_tools_in_plan_mode(tmp_path, monkeypatch):
    agent_file = _write_agent_files(tmp_path)
    manifest = agent_file.read_text(encoding="utf-8")
    agent_file.write_text(
        manifest + "\ntool_strategy = \"passthrough\"\n",
        encoding="utf-8",
    )
    session_id = "session-plan-mode"
    (tmp_path / ".aiasys" / "session" / session_id).mkdir(parents=True)
    (tmp_path / "metadata.json").write_text(
        SessionMetadata(
            session_id=session_id,
            user_id="local_default",
            plan_state=SessionPlanState(mode="active"),
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    registry = ToolRegistry()
    registry.register(_EchoTool())
    from app.agents.tools.task_plan_tools import TaskListTool

    registry.register(TaskListTool())
    client = _CaptureToolsClient()

    session = AiasysRuntimeSession(
        RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id=session_id,
            config=AiasysLlmConfig(
                default_model="test-model",
                providers={
                    "provider-1": LlmProviderConfig(
                        api_key="secret",
                        base_url="https://example.com/v1",
                    )
                },
                models={
                    "test-model": LlmModelConfig(
                        provider="provider-1",
                        model="test-model-remote",
                    )
                },
            ),
            agent_file=agent_file,
            skills_dir=None,
            mcp_configs=None,
            yolo=True,
        ),
        client,
        registry,
    )

    _ = [event async for event in session.prompt("hello")]

    assert "task_list" in client.tool_names
    assert "EchoTool" not in client.tool_names
    await session.close()


async def test_aiasys_runtime_session_runs_react_loop(tmp_path):
    agent_file = _write_agent_files(tmp_path)
    registry = ToolRegistry()
    registry.register(_EchoTool())
    client = _FakeStreamingClient()

    session = AiasysRuntimeSession(
        RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id="session-1",
            config=AiasysLlmConfig(
                default_model="test-model",
                providers={
                    "provider-1": LlmProviderConfig(
                        api_key="secret",
                        base_url="https://example.com/v1",
                    )
                },
                models={
                    "test-model": LlmModelConfig(
                        provider="provider-1",
                        model="test-model-remote",
                    )
                },
            ),
            agent_file=agent_file,
            skills_dir=None,
            mcp_configs=None,
            yolo=True,
        ),
        client,
        registry,
    )

    events = [event async for event in session.prompt("hello")]

    assert [event.kind for event in events] == [
        "content",
        "content",
        "tool_call",
        "tool_result",
        "content",
        "token_usage",
    ]
    assert events[0].text == "分析中。"
    assert events[1].content_type == "think"
    assert events[1].think == "先整理问题，再调用工具。"
    assert events[2].tool_name == "EchoTool"
    assert events[2].arguments == {"text": "hello"}
    assert events[3].content == "echo: hello"
    assert events[4].text == "最终答案"
    # input_tokens 是多轮 prompt_tokens 的累加
    assert events[5].input_tokens == sum(u["prompt_tokens"] for u in client.usages)
    # output_tokens 是多轮 completion_tokens 的累加
    assert events[5].output_tokens == sum(u["completion_tokens"] for u in client.usages)

    await session.close()
    assert client.closed is True
    assert len(client.calls) == 2
    assistant_tool_call_message = next(
        message
        for message in client.calls[1]
        if message["role"] == "assistant" and "tool_calls" in message
    )
    assert assistant_tool_call_message["reasoning_content"] == "先整理问题，再调用工具。"
    assert client.calls[1][-1]["role"] == "tool"
    assert client.calls[1][-1]["content"] == "echo: hello"


def test_loop_detection_normalizes_mapping_arguments_before_similarity_check(
    tmp_path,
):
    agent_file = _write_agent_files(tmp_path)
    registry = ToolRegistry()
    client = _SingleTurnClient()
    session = AiasysRuntimeSession(
        RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id="session-loop",
            config=AiasysLlmConfig(
                default_model="test-model",
                providers={
                    "provider-1": LlmProviderConfig(
                        api_key="secret",
                        base_url="https://example.com/v1",
                    )
                },
                models={
                    "test-model": LlmModelConfig(
                        provider="provider-1",
                        model="test-model-remote",
                    )
                },
            ),
            agent_file=agent_file,
            skills_dir=None,
            mcp_configs=None,
            yolo=True,
        ),
        client,
        registry,
    )

    arguments = _IndexRejectingMapping({"query": "hello"})

    assert session._check_loop_detection("Search", arguments) is None
    assert session._check_loop_detection("Search", arguments) is None
    assert session._previous_tool_args["Search"] == '{"query": "hello"}'


async def test_aiasys_runtime_session_downgrades_old_inline_images_before_next_turn(
    tmp_path,
):
    agent_file = _write_agent_files(tmp_path)
    registry = ToolRegistry()
    client = _SingleTurnClient()

    session = AiasysRuntimeSession(
        RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id="session-2",
            config=AiasysLlmConfig(
                default_model="test-model",
                providers={
                    "provider-1": LlmProviderConfig(
                        api_key="secret",
                        base_url="https://example.com/v1",
                    )
                },
                models={
                    "test-model": LlmModelConfig(
                        provider="provider-1",
                        model="test-model-remote",
                        capabilities=["image_in"],
                    )
                },
            ),
            agent_file=agent_file,
            skills_dir=None,
            mcp_configs=None,
            yolo=True,
        ),
        client,
        registry,
    )

    first_turn = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "看看这张图"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,ZmFrZQ=="},
                    "source_path": "/workspace/chart.png",
                },
            ],
        }
    ]

    _ = [event async for event in session.prompt(first_turn)]
    _ = [event async for event in session.prompt("第二轮问题")]

    # Prefix Cache 改造后，messages 列表中多了 contextual user message（memory + AGENTS.md），
    # 需要明确找 content 为数组（含 image）的 user message，而不是第一个 user message。
    image_user_messages = [
        m for m in client.calls[0]
        if m["role"] == "user" and isinstance(m.get("content"), list)
    ]
    assert len(image_user_messages) == 1
    assert image_user_messages[0]["content"][1]["type"] == "image_url"

    previous_image_user_messages = [
        m for m in client.calls[1]
        if m["role"] == "user" and isinstance(m.get("content"), list)
    ]
    assert len(previous_image_user_messages) == 1
    assert previous_image_user_messages[0]["content"] == [
        {"type": "text", "text": "看看这张图"},
        {
            "type": "image_reference",
            "source_path": "/workspace/chart.png",
        },
    ]


async def test_aiasys_runtime_session_hydrates_workspace_images_once(tmp_path):
    (tmp_path / "chart.png").write_bytes(b"fake-image")
    agent_file = _write_agent_files(tmp_path)
    registry = ToolRegistry()
    client = _SingleTurnClient()

    session = AiasysRuntimeSession(
        RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id="session-workspace-image",
            config=AiasysLlmConfig(
                default_model="test-model",
                providers={
                    "provider-1": LlmProviderConfig(
                        api_key="secret",
                        base_url="https://example.com/v1",
                    )
                },
                models={
                    "test-model": LlmModelConfig(
                        provider="provider-1",
                        model="test-model-remote",
                        capabilities=["image_in"],
                    )
                },
            ),
            agent_file=agent_file,
            skills_dir=None,
            mcp_configs=None,
            yolo=True,
        ),
        client,
        registry,
    )

    first_turn = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "看看这张图"},
                {
                    "type": "image_url",
                    "image_url": {"url": "file:///workspace/chart.png"},
                    "source_path": "/workspace/chart.png",
                },
            ],
        }
    ]

    _ = [event async for event in session.prompt(first_turn)]
    _ = [event async for event in session.prompt("第二轮问题")]

    image_user_messages = [
        message
        for message in client.calls[0]
        if message["role"] == "user" and isinstance(message.get("content"), list)
    ]
    assert len(image_user_messages) == 1
    first_image_url = image_user_messages[0]["content"][1]["image_url"]["url"]
    assert first_image_url.startswith("data:image/png;base64,")

    previous_image_user_messages = [
        message
        for message in client.calls[1]
        if message["role"] == "user" and isinstance(message.get("content"), list)
    ]
    assert len(previous_image_user_messages) == 1
    assert previous_image_user_messages[0]["content"] == [
        {"type": "text", "text": "看看这张图"},
        {
            "type": "image_reference",
            "source_path": "/workspace/chart.png",
        },
    ]
    assert _contains_data_image(client.calls[1]) is False

    await session.close()


async def test_aiasys_runtime_session_downgrades_current_images_for_text_only_model(
    tmp_path,
):
    agent_file = _write_agent_files(tmp_path)
    registry = ToolRegistry()
    client = _SingleTurnClient()

    session = AiasysRuntimeSession(
        RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id="session-text-only-image",
            config=AiasysLlmConfig(
                default_model="test-model",
                providers={
                    "provider-1": LlmProviderConfig(
                        api_key="secret",
                        base_url="https://example.com/v1",
                    )
                },
                models={
                    "test-model": LlmModelConfig(
                        provider="provider-1",
                        model="test-model-remote",
                    )
                },
            ),
            agent_file=agent_file,
            skills_dir=None,
            mcp_configs=None,
            yolo=True,
        ),
        client,
        registry,
    )

    first_turn = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "看看这张图"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,ZmFrZQ=="},
                    "source_path": "/workspace/chart.png",
                },
            ],
        }
    ]

    _ = [event async for event in session.prompt(first_turn)]

    image_user_messages = [
        message
        for message in client.calls[0]
        if message["role"] == "user" and isinstance(message.get("content"), list)
    ]
    assert len(image_user_messages) == 1
    assert image_user_messages[0]["content"] == [
        {"type": "text", "text": "看看这张图"},
        {
            "type": "image_reference",
            "source_path": "/workspace/chart.png",
        },
    ]
    assert _contains_data_image(client.calls[0]) is False

    await session.close()


async def test_aiasys_runtime_session_enables_thinking_for_thinking_model(tmp_path):
    agent_file = _write_agent_files(tmp_path)
    registry = ToolRegistry()
    client = _SingleTurnClient()

    session = AiasysRuntimeSession(
        RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id="session-thinking",
            config=AiasysLlmConfig(
                default_model="test-model",
                providers={
                    "provider-1": LlmProviderConfig(
                        api_key="secret",
                        base_url="https://api.kimi.com/coding/v1",
                        type="anthropic_messages",
                    )
                },
                models={
                    "test-model": LlmModelConfig(
                        provider="provider-1",
                        model="test-model-remote",
                        capabilities=["thinking"],
                    )
                },
            ),
            agent_file=agent_file,
            skills_dir=None,
            mcp_configs=None,
            yolo=True,
        ),
        client,
        registry,
    )

    _ = [event async for event in session.prompt("hello")]

    assert client.request_options
    options = client.request_options[0]
    assert options is not None
    assert options.thinking_enabled is True
    assert options.thinking_effort == "high"
    assert options.thinking_budget_tokens == 8192


def test_get_backend_defaults_to_aiasys():
    assert isinstance(get_backend(), AiasysRuntimeBackend)
    assert isinstance(get_backend("aiasys"), AiasysRuntimeBackend)


def test_instantiate_ask_user_tool_wraps_callabletool2_compat():
    tool = _instantiate_tool(
        "app.agents.tools.ask_user.tool:AskUser",
        session_id="session-ask-user",
        model_capabilities=None,
    )

    assert tool is not None
    assert isinstance(tool, AiasysTool)
    assert tool.name == "AskUser"
    registry = ToolRegistry()
    registry.register(tool)
    schema = registry.get_openai_schema()[0]["function"]["parameters"]
    assert schema["type"] == "object"
    assert "title" in schema["properties"]


def test_tool_registry_get_tool_returns_registered_and_missing_tools():
    registry = ToolRegistry()
    registry.register(_EchoTool())

    assert registry.get_tool("EchoTool") is not None
    assert registry.get_tool("echo_tool") is not None
    assert registry.get_tool("missing_tool") is None


def test_tool_registry_mcp_conflict_auto_rename():
    """MCP 工具与内置工具同名时自动加 mcp_ 前缀重命名。"""
    registry = ToolRegistry()
    builtin = _EchoTool()
    mcp = _McpEchoTool()

    registry.register(builtin)
    # MCP 工具与内置工具冲突，应自动重命名
    registry.register(mcp)

    # 重命名后的工具应以 mcp_ 前缀注册
    assert registry.get_tool("mcp_EchoTool") is not None
    assert mcp.name == "mcp_EchoTool"
    # 原内置工具不受影响
    assert registry.get_tool("EchoTool") is not None
    assert registry.get_tool("EchoTool") is builtin


def test_tool_registry_builtin_conflict_still_raises():
    """内置工具与内置工具冲突仍然报错。"""
    registry = ToolRegistry()
    registry.register(_EchoTool())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_EchoTool())


def test_tool_registry_mcp_mcp_conflict_still_raises():
    """MCP 工具与 MCP 工具冲突仍然报错。"""
    registry = ToolRegistry()
    registry.register(_McpEchoTool())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_McpEchoTool())


def test_tool_registry_schema_sorts_builtin_before_mcp():
    """get_openai_schema 返回顺序：内置在前，MCP 在后，各自按名称排序。"""
    registry = ToolRegistry()

    class _ZBuiltin(AiasysTool):
        name = "ZBuiltin"
        description = "z"
        async def invoke(self, ctx=None, **kwargs):
            return ToolResult(content="z")

    class _AMcp(AiasysTool):
        name = "AMcp"
        description = "a"
        is_mcp = True
        async def invoke(self, ctx=None, **kwargs):
            return ToolResult(content="a")

    registry.register(_ZBuiltin())
    registry.register(_AMcp())

    schemas = registry.get_openai_schema()
    names = [s["function"]["name"] for s in schemas]
    # 内置在前，MCP 在后
    assert names == ["ZBuiltin", "AMcp"]


# ── 新增：API 错误重试、截断续写、流中断恢复 ──────────────────────────────


class _429ThenSuccessClient:
    """前两次抛 429 RateLimitError，第三次成功返回 content。"""

    def __init__(self) -> None:
        self.calls = 0
        self.all_calls: list[list[dict]] = []

    async def chat_stream(self, messages, tools, temperature, max_tokens, request_options=None):
        del request_options
        del tools, temperature, max_tokens
        self.calls += 1
        self.all_calls.append([dict(m) for m in messages])
        if self.calls <= 2:
            exc = Exception("rate limit exceeded")
            exc.status_code = 429
            raise exc
        yield LlmChunk(
            delta=LlmDelta(content="ok after retry"),
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
        )

    async def aclose(self) -> None:
        return None


class _LengthTruncatedClient:
    """第一次 finish_reason=length，第二次 finish_reason=stop。"""

    def __init__(self) -> None:
        self.calls = 0

    async def chat_stream(self, messages, tools, temperature, max_tokens, request_options=None):
        del request_options
        del tools, temperature, max_tokens
        self.calls += 1
        if self.calls == 1:
            yield LlmChunk(
                delta=LlmDelta(content="第一部分"),
                finish_reason="length",
                usage={"prompt_tokens": 2, "completion_tokens": 2},
            )
        else:
            yield LlmChunk(
                delta=LlmDelta(content="第二部分"),
                finish_reason="stop",
                usage={"prompt_tokens": 2, "completion_tokens": 2},
            )

    async def aclose(self) -> None:
        return None


class _NonRetryableInterruptClient:
    """先传输部分内容，再抛非 retryable 异常（401），触发流中断恢复。"""

    def __init__(self) -> None:
        self.calls = 0

    async def chat_stream(self, messages, tools, temperature, max_tokens, request_options=None):
        del request_options
        del tools, temperature, max_tokens
        self.calls += 1
        yield LlmChunk(
            delta=LlmDelta(content="部分输出"),
            finish_reason=None,
            usage=None,
        )
        exc = Exception("auth failed")
        exc.status_code = 401
        raise exc

    async def aclose(self) -> None:
        return None


async def test_api_error_retry_with_backoff(tmp_path, monkeypatch):
    """任务 1：429 错误应触发重试，最终成功。"""
    monkeypatch.setattr(
        "app.services.agent.runtime_backends.aiasys.session_stream.jittered_backoff",
        lambda *_a, **_k: 0.0,
    )
    agent_file = _write_agent_files(tmp_path)
    registry = ToolRegistry()
    client = _429ThenSuccessClient()

    session = AiasysRuntimeSession(
        RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id="session-retry",
            config=AiasysLlmConfig(
                default_model="test-model",
                providers={
                    "provider-1": LlmProviderConfig(
                        api_key="secret",
                        base_url="https://example.com/v1",
                    )
                },
                models={
                    "test-model": LlmModelConfig(
                        provider="provider-1",
                        model="test-model-remote",
                    )
                },
            ),
            agent_file=agent_file,
            skills_dir=None,
            mcp_configs=None,
            yolo=True,
        ),
        client,
        registry,
    )

    events = [event async for event in session.prompt("hello")]
    kinds = [e.kind for e in events]

    assert client.calls == 3
    assert "content" in kinds
    assert "token_usage" in kinds
    assert events[kinds.index("content")].text == "ok after retry"
    await session.close()


async def test_finish_reason_length_auto_continuation(tmp_path):
    """任务 2：finish_reason=length 应自动续写，最多拼接内容。"""
    agent_file = _write_agent_files(tmp_path)
    registry = ToolRegistry()
    client = _LengthTruncatedClient()

    session = AiasysRuntimeSession(
        RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id="session-length",
            config=AiasysLlmConfig(
                default_model="test-model",
                providers={
                    "provider-1": LlmProviderConfig(
                        api_key="secret",
                        base_url="https://example.com/v1",
                    )
                },
                models={
                    "test-model": LlmModelConfig(
                        provider="provider-1",
                        model="test-model-remote",
                    )
                },
            ),
            agent_file=agent_file,
            skills_dir=None,
            mcp_configs=None,
            yolo=True,
        ),
        client,
        registry,
    )

    events = [event async for event in session.prompt("hello")]
    text_events = [e for e in events if e.kind == "content"]

    assert client.calls == 2
    assert [e.text for e in text_events] == ["第一部分", "第二部分"]

    # 验证历史消息中插入了续写提示
    last_user_msg = next(
        (m for m in reversed(session.messages) if m.get("role") == "user"), None
    )
    assert last_user_msg is not None
    assert "truncated" in str(last_user_msg.get("content", "")).lower()
    await session.close()


async def test_stream_interrupt_uses_transmitted_fragment(tmp_path):
    """任务 3：流中断时，已传输的片段应作为最终响应保存到历史。"""
    agent_file = _write_agent_files(tmp_path)
    registry = ToolRegistry()
    client = _NonRetryableInterruptClient()

    session = AiasysRuntimeSession(
        RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id="session-interrupt",
            config=AiasysLlmConfig(
                default_model="test-model",
                providers={
                    "provider-1": LlmProviderConfig(
                        api_key="secret",
                        base_url="https://example.com/v1",
                    )
                },
                models={
                    "test-model": LlmModelConfig(
                        provider="provider-1",
                        model="test-model-remote",
                    )
                },
            ),
            agent_file=agent_file,
            skills_dir=None,
            mcp_configs=None,
            yolo=True,
        ),
        client,
        registry,
    )

    events = [event async for event in session.prompt("hello")]
    kinds = [e.kind for e in events]

    assert client.calls == 1
    # 应 yield 已传输的 content + system_warning
    assert "content" in kinds
    assert "system_warning" in kinds
    content_event = events[kinds.index("content")]
    assert content_event.text == "部分输出"

    # 验证历史消息中保存了 fallback assistant message
    assistant_msgs = [m for m in session.messages if m.get("role") == "assistant"]
    assert len(assistant_msgs) >= 1
    assert assistant_msgs[-1].get("content") == "部分输出"
    await session.close()


async def test_tool_result_image_hydrated_for_multimodal_model(tmp_path):
    """工具返回的图片在多模态模型调用前会被水合成 data URL。"""
    (tmp_path / "chart.png").write_bytes(b"fake-image")
    agent_file = _write_agent_files(tmp_path)
    registry = ToolRegistry()
    registry.register(_ImageTool())
    client = _ImageToolClient()

    session = AiasysRuntimeSession(
        RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id="session-tool-image-hydrate",
            config=AiasysLlmConfig(
                default_model="test-model",
                providers={
                    "provider-1": LlmProviderConfig(
                        api_key="secret",
                        base_url="https://example.com/v1",
                    )
                },
                models={
                    "test-model": LlmModelConfig(
                        provider="provider-1",
                        model="test-model-remote",
                        capabilities=["image_in"],
                    )
                },
            ),
            agent_file=agent_file,
            skills_dir=None,
            mcp_configs=None,
            yolo=True,
        ),
        client,
        registry,
    )

    events = [event async for event in session.prompt("看看这张图")]
    assert any(e.kind == "tool_result" for e in events)

    # 第二轮调用（工具结果后）中，tool message 的图片应被水合
    second_call_messages = client.calls[1]
    tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    tool_content = tool_messages[0].get("content")
    assert isinstance(tool_content, list)
    image_parts = [p for p in tool_content if isinstance(p, dict) and p.get("type") == "image_url"]
    assert len(image_parts) == 1
    assert image_parts[0]["image_url"]["url"].startswith("data:image/png;base64,")
    await session.close()


async def test_tool_result_image_downgraded_for_text_only_model(tmp_path):
    """纯文本模型调用前，工具返回的图片会被降级为 image_reference。"""
    (tmp_path / "chart.png").write_bytes(b"fake-image")
    agent_file = _write_agent_files(tmp_path)
    registry = ToolRegistry()
    registry.register(_ImageTool())
    client = _ImageToolClient()

    session = AiasysRuntimeSession(
        RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id="session-tool-image-text",
            config=AiasysLlmConfig(
                default_model="test-model",
                providers={
                    "provider-1": LlmProviderConfig(
                        api_key="secret",
                        base_url="https://example.com/v1",
                    )
                },
                models={
                    "test-model": LlmModelConfig(
                        provider="provider-1",
                        model="test-model-remote",
                    )
                },
            ),
            agent_file=agent_file,
            skills_dir=None,
            mcp_configs=None,
            yolo=True,
        ),
        client,
        registry,
    )

    events = [event async for event in session.prompt("看看这张图")]
    assert any(e.kind == "tool_result" for e in events)

    second_call_messages = client.calls[1]
    tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    tool_content = tool_messages[0].get("content")
    assert isinstance(tool_content, list)
    assert _contains_data_image(tool_content) is False
    image_ref_parts = [p for p in tool_content if isinstance(p, dict) and p.get("type") == "image_reference"]
    assert len(image_ref_parts) == 1
    assert image_ref_parts[0].get("source_path") == "/workspace/chart.png"
    await session.close()
