from __future__ import annotations

import pytest

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.core.workspace_path import WorkspacePath
from app.services.agent.models.llm_config import AiasysLlmConfig, LlmModelConfig, LlmProviderConfig
from app.services.agent.runtime_backends import RuntimeSessionCreateSpec
from app.services.agent.runtime_backends.aiasys.llm_clients.base import LlmChunk, LlmDelta
from app.services.agent.runtime_backends.aiasys.session import AiasysRuntimeSession
from app.services.agent.runtime_backends.aiasys.tool_registry import ToolRegistry


class _EchoTool(AiasysTool):
    name = "EchoTool"
    description = "Echo text"
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


class _MalformedToolArgumentsClient:
    def __init__(self, arguments: str) -> None:
        self.arguments = arguments
        self.calls = 0

    async def chat_stream(self, messages, tools, temperature, max_tokens, request_options=None):
        del messages, tools, temperature, max_tokens, request_options
        self.calls += 1
        if self.calls == 1:
            yield LlmChunk(
                delta=LlmDelta(
                    tool_calls=[
                        {
                            "index": 0,
                            "id": "call-echo",
                            "function": {
                                "name": "EchoTool",
                                "arguments": self.arguments,
                            },
                        }
                    ]
                ),
                finish_reason="tool_calls",
                usage={"prompt_tokens": 1, "completion_tokens": 1},
            )
            return
        yield LlmChunk(
            delta=LlmDelta(content="done"),
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
        )

    async def aclose(self) -> None:
        return None


def _write_agent_file(tmp_path):
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("system prompt", encoding="utf-8")
    agent_file = tmp_path / "agent.toml"
    agent_file.write_text(
        """
version = 1

[agent]
name = "test-agent"
model = "test-model"
system_prompt_path = "./prompt.md"
tool_strategy = "passthrough"
""".strip(),
        encoding="utf-8",
    )
    return agent_file


def _session(tmp_path, client):
    registry = ToolRegistry()
    registry.register(_EchoTool())
    return AiasysRuntimeSession(
        RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id="session-tool-json-repair",
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
            agent_file=_write_agent_file(tmp_path),
            skills_dir=None,
            mcp_configs=None,
            yolo=True,
        ),
        client,
        registry,
    )


@pytest.mark.parametrize(
    ("raw_arguments", "expected_arguments"),
    [
        ('{"text":"hello",}', {"text": "hello"}),
        ("{'text': 'hello'}", {"text": "hello"}),
        ('{"text":"hello"', {"text": "hello"}),
    ],
)
async def test_recoverable_tool_argument_json_is_repaired_before_invocation(
    tmp_path,
    raw_arguments,
    expected_arguments,
):
    client = _MalformedToolArgumentsClient(raw_arguments)
    session = _session(tmp_path, client)

    events = [event async for event in session.prompt("call the echo tool")]

    tool_calls = [event for event in events if event.kind == "tool_call"]
    tool_results = [event for event in events if event.kind == "tool_result"]

    assert tool_calls
    assert tool_calls[0].arguments == expected_arguments
    assert tool_results
    assert tool_results[0].is_error is False
    assert tool_results[0].content == "echo: hello"
    await session.close()


async def test_irrecoverable_tool_argument_text_remains_parse_error(tmp_path):
    client = _MalformedToolArgumentsClient("not json at all")
    session = _session(tmp_path, client)

    events = [event async for event in session.prompt("call the echo tool")]

    tool_calls = [event for event in events if event.kind == "tool_call"]
    tool_results = [event for event in events if event.kind == "tool_result"]

    assert tool_calls
    assert tool_calls[0].arguments == {}
    assert tool_results
    assert tool_results[0].is_error is True
    assert "Invalid JSON arguments" in str(tool_results[0].content)
    await session.close()
