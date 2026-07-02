from __future__ import annotations

from typing import Any

from .base import LlmRequestOptions

_OPENAI_REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}
_STEPFUN_REASONING_EFFORTS = {"low", "medium", "high"}
_DEEPSEEK_REASONING_EFFORTS = {"high", "max"}
_RESPONSES_REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}


def apply_openai_chat_thinking_options(
    kwargs: dict[str, Any],
    request_options: LlmRequestOptions | None,
    *,
    base_url: str | None,
    model: str,
    reasoning_format: str | None = None,
) -> None:
    if request_options is None:
        return

    provider = _detect_openai_compatible_provider(base_url, model)
    extra_body = _provider_extra_body(
        request_options,
        provider=provider,
        reasoning_format=reasoning_format,
    )
    if extra_body:
        kwargs.setdefault("extra_body", {}).update(extra_body)

    if request_options.thinking_disabled and provider == "openai":
        kwargs["reasoning_effort"] = "none"
        return
    if not request_options.thinking_enabled:
        return

    effort = _normalized_effort(request_options.thinking_effort)
    if provider == "qwen":
        return
    if provider == "kimi":
        return
    if provider == "deepseek":
        kwargs["reasoning_effort"] = _deepseek_effort(effort)
        return
    if provider == "stepfun":
        kwargs["reasoning_effort"] = _supported_or_default(
            effort,
            supported=_STEPFUN_REASONING_EFFORTS,
            default="high",
        )
        return
    if effort in _OPENAI_REASONING_EFFORTS:
        kwargs["reasoning_effort"] = effort


def apply_responses_thinking_options(
    kwargs: dict[str, Any],
    request_options: LlmRequestOptions | None,
) -> None:
    if request_options is None:
        return
    if request_options.thinking_disabled:
        kwargs["reasoning"] = {"effort": "none", "summary": "auto"}
        return
    if not request_options.thinking_enabled:
        return

    effort = _normalized_effort(request_options.thinking_effort)
    effort = _supported_or_default(effort, supported=_RESPONSES_REASONING_EFFORTS, default="high")
    kwargs["reasoning"] = {"effort": effort, "summary": "auto"}
    kwargs["include"] = ["reasoning.encrypted_content"]


def apply_anthropic_thinking_options(
    kwargs: dict[str, Any],
    request_options: LlmRequestOptions | None,
    *,
    base_url: str | None,
    model: str,
    is_native_anthropic_endpoint: bool,
) -> None:
    if request_options is None:
        return

    if _is_kimi_endpoint(base_url) or _is_kimi_model(model):
        if request_options.thinking_disabled:
            kwargs["thinking"] = {"type": "disabled"}
        elif request_options.thinking_enabled:
            kwargs["thinking"] = {"type": "enabled"}
        return

    if _is_stepfun_endpoint(base_url) or model.lower().startswith("step-"):
        if request_options.thinking_disabled:
            kwargs["output_config"] = {"effort": "none"}
        elif request_options.thinking_enabled:
            effort = _supported_or_default(
                _normalized_effort(request_options.thinking_effort),
                supported=_STEPFUN_REASONING_EFFORTS,
                default="high",
            )
            kwargs["output_config"] = {"effort": effort}
        return

    if request_options.thinking_disabled:
        kwargs.pop("thinking", None)
        kwargs.pop("output_config", None)
        return
    if not request_options.thinking_enabled:
        return

    from .anthropic_client import (
        _clamp_effort,
        _effort_to_budget,
        _supports_adaptive_thinking,
        _supports_effort_param,
    )

    raw_effort = _normalized_effort(request_options.thinking_effort)
    if raw_effort == "minimal":
        raw_effort = "low"
    effort = _clamp_effort(raw_effort, model)

    if _supports_adaptive_thinking(model):
        kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}
        kwargs["output_config"] = {"effort": effort}
        return

    budget = max(
        int(request_options.thinking_budget_tokens or _effort_to_budget(effort)),
        1024,
    )
    kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
    kwargs["max_tokens"] = max(
        int(kwargs.get("max_tokens") or 8192),
        budget + 2048,
    )
    if is_native_anthropic_endpoint:
        kwargs["temperature"] = 1
    if _supports_effort_param(model):
        kwargs["output_config"] = {"effort": effort}


def _provider_extra_body(
    request_options: LlmRequestOptions,
    *,
    provider: str,
    reasoning_format: str | None,
) -> dict[str, Any]:
    extra_body: dict[str, Any] = {}

    if provider == "qwen":
        if request_options.thinking_disabled:
            extra_body["enable_thinking"] = False
        elif request_options.thinking_enabled:
            extra_body["enable_thinking"] = True
            if request_options.thinking_budget_tokens is not None:
                extra_body["thinking_budget"] = request_options.thinking_budget_tokens
        return extra_body

    if provider == "kimi":
        if request_options.thinking_disabled:
            extra_body["thinking"] = {"type": "disabled"}
        elif request_options.thinking_enabled:
            extra_body["thinking"] = {"type": "enabled"}
        return extra_body

    if provider == "deepseek":
        if request_options.thinking_disabled:
            extra_body["thinking"] = {"type": "disabled"}
        elif request_options.thinking_enabled:
            extra_body["thinking"] = {"type": "enabled"}

    if reasoning_format:
        extra_body["reasoning_format"] = reasoning_format
    return extra_body


def _detect_openai_compatible_provider(base_url: str | None, model: str) -> str:
    endpoint = (base_url or "").lower()
    model_name = model.lower()
    if "dashscope.aliyuncs.com" in endpoint or model_name.startswith(("qwen", "qwq")):
        return "qwen"
    if "kimi" in endpoint or "moonshot" in endpoint or _is_kimi_model(model_name):
        return "kimi"
    if "deepseek" in endpoint or model_name.startswith("deepseek"):
        return "deepseek"
    if "stepfun" in endpoint or model_name.startswith("step-"):
        return "stepfun"
    return "openai"


def _is_kimi_endpoint(base_url: str | None) -> bool:
    endpoint = (base_url or "").lower()
    return "kimi" in endpoint or "moonshot" in endpoint


def _is_stepfun_endpoint(base_url: str | None) -> bool:
    return "stepfun" in (base_url or "").lower()


def _is_kimi_model(model: str) -> bool:
    return model.lower().startswith(("kimi", "moonshot"))


def _normalized_effort(effort: str | None) -> str:
    raw = (effort or "high").strip().lower()
    if raw == "max":
        return "xhigh"
    return raw


def _supported_or_default(effort: str, *, supported: set[str], default: str) -> str:
    return effort if effort in supported else default


def _deepseek_effort(effort: str) -> str:
    if effort in {"xhigh", "max"}:
        return "max"
    if effort in _DEEPSEEK_REASONING_EFFORTS:
        return effort
    return "high"
