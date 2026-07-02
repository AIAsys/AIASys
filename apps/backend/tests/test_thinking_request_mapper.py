from __future__ import annotations

from app.services.agent.runtime_backends.aiasys.llm_clients.base import LlmRequestOptions
from app.services.agent.runtime_backends.aiasys.llm_clients.thinking_mapper import (
    apply_anthropic_thinking_options,
    apply_openai_chat_thinking_options,
    apply_responses_thinking_options,
)


def test_stepfun_chat_uses_reasoning_effort() -> None:
    kwargs: dict = {}

    apply_openai_chat_thinking_options(
        kwargs,
        LlmRequestOptions(thinking_enabled=True, thinking_effort="medium"),
        base_url="https://api.stepfun.com/step_plan/v1",
        model="step-3.7-flash",
    )

    assert kwargs["reasoning_effort"] == "medium"
    assert "extra_body" not in kwargs


def test_stepfun_messages_uses_output_config_effort() -> None:
    kwargs: dict = {"temperature": 0.3, "max_tokens": 4096}

    apply_anthropic_thinking_options(
        kwargs,
        LlmRequestOptions(thinking_enabled=True, thinking_effort="low"),
        base_url="https://api.stepfun.com/step_plan",
        model="step-3.7-flash",
        is_native_anthropic_endpoint=False,
    )

    assert kwargs["output_config"] == {"effort": "low"}
    assert kwargs["temperature"] == 0.3
    assert kwargs["max_tokens"] == 4096
    assert "thinking" not in kwargs


def test_openai_chat_disabled_uses_reasoning_effort_none() -> None:
    kwargs: dict = {}

    apply_openai_chat_thinking_options(
        kwargs,
        LlmRequestOptions(thinking_disabled=True),
        base_url="https://api.openai.com/v1",
        model="gpt-5.1",
    )

    assert kwargs["reasoning_effort"] == "none"


def test_qwen_chat_uses_enable_thinking_extra_body() -> None:
    kwargs: dict = {}

    apply_openai_chat_thinking_options(
        kwargs,
        LlmRequestOptions(
            thinking_enabled=True,
            thinking_effort="high",
            thinking_budget_tokens=8192,
        ),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen3-coder-plus",
    )

    assert "reasoning_effort" not in kwargs
    assert kwargs["extra_body"]["enable_thinking"] is True
    assert kwargs["extra_body"]["thinking_budget"] == 8192


def test_kimi_openai_chat_can_disable_thinking() -> None:
    kwargs: dict = {}

    apply_openai_chat_thinking_options(
        kwargs,
        LlmRequestOptions(thinking_disabled=True),
        base_url="https://api.moonshot.cn/v1",
        model="kimi-k2-thinking",
    )

    assert "reasoning_effort" not in kwargs
    assert kwargs["extra_body"]["thinking"] == {"type": "disabled"}


def test_deepseek_reasoning_effort_is_mapped_to_supported_levels() -> None:
    low_kwargs: dict = {}
    max_kwargs: dict = {}

    apply_openai_chat_thinking_options(
        low_kwargs,
        LlmRequestOptions(thinking_enabled=True, thinking_effort="low"),
        base_url="https://api.deepseek.com/v1",
        model="deepseek-reasoner",
    )
    apply_openai_chat_thinking_options(
        max_kwargs,
        LlmRequestOptions(thinking_enabled=True, thinking_effort="xhigh"),
        base_url="https://api.deepseek.com/v1",
        model="deepseek-reasoner",
    )

    assert low_kwargs["reasoning_effort"] == "high"
    assert max_kwargs["reasoning_effort"] == "max"


def test_openai_responses_uses_reasoning_object() -> None:
    kwargs: dict = {}

    apply_responses_thinking_options(
        kwargs,
        LlmRequestOptions(thinking_enabled=True, thinking_effort="xhigh"),
    )

    assert kwargs["reasoning"] == {"effort": "xhigh", "summary": "auto"}
    assert kwargs["include"] == ["reasoning.encrypted_content"]


def test_openai_responses_disabled_uses_reasoning_none() -> None:
    kwargs: dict = {}

    apply_responses_thinking_options(
        kwargs,
        LlmRequestOptions(thinking_disabled=True),
    )

    assert kwargs["reasoning"] == {"effort": "none", "summary": "auto"}


def test_kimi_anthropic_compat_uses_kimi_thinking_shape() -> None:
    kwargs: dict = {"temperature": 0.4, "max_tokens": 4096}

    apply_anthropic_thinking_options(
        kwargs,
        LlmRequestOptions(thinking_enabled=True, thinking_effort="high"),
        base_url="https://api.kimi.com/coding/v1",
        model="kimi-k2",
        is_native_anthropic_endpoint=False,
    )

    assert kwargs["thinking"] == {"type": "enabled"}
    assert kwargs["temperature"] == 0.4
    assert kwargs["max_tokens"] == 4096
    assert "output_config" not in kwargs
