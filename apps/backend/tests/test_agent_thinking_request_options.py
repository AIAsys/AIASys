from __future__ import annotations

import pytest

from app.core.workspace_path import WorkspacePath
from app.services.agent.mixins import session as session_module
from app.services.agent.mixins.execution import ExecutionMixin
from app.services.agent.runtime_backends import RuntimeSessionCreateSpec
from app.services.agent.runtime_backends.aiasys.llm_clients.base import (
    LlmChunk,
    LlmDelta,
    LlmRequestOptions,
)
from app.services.agent.runtime_backends.aiasys.session import AiasysRuntimeSession
from app.services.agent.runtime_backends.aiasys.tool_registry import ToolRegistry
from app.services.agent_config.models import AgentMode


class _StopAfterConfig(Exception):
    pass


class _SingleTurnCaptureClient:
    def __init__(self) -> None:
        self.request_options: list[LlmRequestOptions | None] = []

    async def chat_stream(self, messages, tools, temperature, max_tokens, request_options=None):
        del messages, tools, temperature, max_tokens
        self.request_options.append(request_options)
        yield LlmChunk(
            delta=LlmDelta(content="ok"),
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
        )

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_execute_stream_passes_request_thinking_overrides_to_config() -> None:
    captured: dict[str, object] = {}

    class DummyService(ExecutionMixin):
        def _get_config(
            self,
            model,
            user_id,
            model_id=None,
            session_id=None,
            thinking_enabled=None,
            thinking_effort=None,
        ):
            captured.update(
                {
                    "model": model,
                    "user_id": user_id,
                    "model_id": model_id,
                    "session_id": session_id,
                    "thinking_enabled": thinking_enabled,
                    "thinking_effort": thinking_effort,
                }
            )
            raise _StopAfterConfig

    service = DummyService()

    with pytest.raises(_StopAfterConfig):
        async for _ in service.execute_stream(
            prompt="hello",
            user_id="user-1",
            session_id="session-1",
            model="model-name",
            model_id="model-1",
            thinking_enabled=True,
            thinking_effort="medium",
        ):
            pass

    assert captured == {
        "model": "model-name",
        "user_id": "user-1",
        "model_id": "model-1",
        "session_id": "session-1",
        "thinking_enabled": True,
        "thinking_effort": "medium",
    }


@pytest.mark.asyncio
async def test_request_thinking_override_reaches_runtime_request_options(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    class StubLLMConfigService:
        def get_full_config(self, _user_id: str):
            return {
                "providers": {
                    "provider-1": {
                        "type": "openai_chat_completions",
                        "base_url": "https://api.example.com/v1",
                        "api_key": "test-key",
                    }
                },
                "models": {
                    "model-1": {
                        "provider": "provider-1",
                        "model": "test-model",
                        "capabilities": [],
                    }
                },
                "default_model": "model-1",
            }

    class StubAgentConfigService:
        def get_effective_runtime_config(self, mode, user_id, session_id=None):
            assert mode == AgentMode.ANALYSIS
            assert user_id == "user-1"
            assert session_id == "session-1"

            class RuntimeConfig:
                def model_dump(self):
                    return {}

            return RuntimeConfig()

    class DummyService(session_module.SessionMixin):
        pass

    agent_file = tmp_path / "agent.toml"
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("system prompt", encoding="utf-8")
    agent_file.write_text(
        """
[agent]
name = "test-agent"
model = "model-1"
tools = []
system_prompt_path = "./prompt.md"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(session_module, "get_llm_config_service", lambda: StubLLMConfigService())
    monkeypatch.setattr(
        session_module,
        "get_agent_config_service",
        lambda: StubAgentConfigService(),
    )

    config = DummyService()._get_config(
        model=None,
        user_id="user-1",
        model_id="model-1",
        session_id="session-1",
        thinking_enabled=True,
        thinking_effort="medium",
    )
    client = _SingleTurnCaptureClient()
    session = AiasysRuntimeSession(
        RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id="session-1",
            user_id="user-1",
            config=config,
            agent_file=agent_file,
            skills_dir=None,
            mcp_configs=None,
            yolo=True,
        ),
        client,
        ToolRegistry(),
    )

    try:
        events = [event async for event in session.prompt("hello")]
    finally:
        await session.close()

    assert [event.kind for event in events if event.kind != "turn_begin"] == [
        "content",
        "token_usage",
    ]
    assert client.request_options[0] is not None
    assert client.request_options[0].thinking_enabled is True
    assert client.request_options[0].thinking_effort == "medium"
    assert client.request_options[0].thinking_budget_tokens == 4096


@pytest.mark.asyncio
async def test_request_thinking_disable_reaches_runtime_request_options(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    class StubLLMConfigService:
        def get_full_config(self, _user_id: str):
            return {
                "providers": {
                    "provider-1": {
                        "type": "openai_chat_completions",
                        "base_url": "https://api.example.com/v1",
                        "api_key": "test-key",
                    }
                },
                "models": {
                    "model-1": {
                        "provider": "provider-1",
                        "model": "test-model",
                        "capabilities": ["always_thinking"],
                        "thinking_effort": "high",
                    }
                },
                "default_model": "model-1",
            }

    class StubAgentConfigService:
        def get_effective_runtime_config(self, mode, user_id, session_id=None):
            assert mode == AgentMode.ANALYSIS
            assert user_id == "user-1"
            assert session_id == "session-1"

            class RuntimeConfig:
                def model_dump(self):
                    return {}

            return RuntimeConfig()

    class DummyService(session_module.SessionMixin):
        pass

    agent_file = tmp_path / "agent.toml"
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("system prompt", encoding="utf-8")
    agent_file.write_text(
        """
[agent]
name = "test-agent"
model = "model-1"
tools = []
system_prompt_path = "./prompt.md"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(session_module, "get_llm_config_service", lambda: StubLLMConfigService())
    monkeypatch.setattr(
        session_module,
        "get_agent_config_service",
        lambda: StubAgentConfigService(),
    )

    config = DummyService()._get_config(
        model=None,
        user_id="user-1",
        model_id="model-1",
        session_id="session-1",
        thinking_enabled=False,
        thinking_effort=None,
    )
    client = _SingleTurnCaptureClient()
    session = AiasysRuntimeSession(
        RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id="session-1",
            user_id="user-1",
            config=config,
            agent_file=agent_file,
            skills_dir=None,
            mcp_configs=None,
            yolo=True,
        ),
        client,
        ToolRegistry(),
    )

    try:
        events = [event async for event in session.prompt("hello")]
    finally:
        await session.close()

    assert [event.kind for event in events if event.kind != "turn_begin"] == [
        "content",
        "token_usage",
    ]
    assert client.request_options[0] is not None
    assert client.request_options[0].thinking_enabled is False
    assert client.request_options[0].thinking_disabled is True
    assert client.request_options[0].thinking_effort is None
    assert client.request_options[0].thinking_budget_tokens is None
