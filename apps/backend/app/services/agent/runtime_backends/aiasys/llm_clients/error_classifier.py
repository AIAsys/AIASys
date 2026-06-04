from __future__ import annotations

import enum
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Error taxonomy ──────────────────────────────────────────────────────


class FailoverReason(enum.Enum):
    """Why an API call failed — determines recovery strategy."""

    auth = "auth"  # Transient auth (401/403) — refresh/rotate
    auth_permanent = "auth_permanent"  # Auth failed after refresh — abort
    billing = "billing"  # 402 or confirmed credit exhaustion — rotate immediately
    rate_limit = "rate_limit"  # 429 or quota-based throttling — backoff then rotate
    overloaded = "overloaded"  # 503/529 — provider overloaded, backoff
    server_error = "server_error"  # 500/502 — internal server error, retry
    timeout = "timeout"  # Connection/read timeout — rebuild client + retry
    context_overflow = "context_overflow"  # Context too large — compress, not failover
    payload_too_large = "payload_too_large"  # 413 — compress payload
    model_not_found = "model_not_found"  # 404 or invalid model — fallback to different model
    format_error = "format_error"  # 400 bad request — abort or strip + retry
    thinking_signature = "thinking_signature"  # Anthropic thinking block sig invalid
    long_context_tier = "long_context_tier"  # Anthropic "extra usage" tier gate
    unknown = "unknown"  # Unclassifiable — retry with backoff


# ── Classification result ───────────────────────────────────────────────


@dataclass
class ClassifiedError:
    """Structured classification of an API error with recovery hints."""

    reason: FailoverReason
    status_code: Optional[int] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    message: str = ""
    error_context: dict[str, Any] = field(default_factory=dict)

    retryable: bool = True
    should_compress: bool = False
    should_rotate_credential: bool = False
    should_fallback: bool = False

    @property
    def is_auth(self) -> bool:
        return self.reason in (FailoverReason.auth, FailoverReason.auth_permanent)


# ── Pattern databases ───────────────────────────────────────────────────

_BILLING_PATTERNS = [
    "insufficient credits",
    "insufficient_quota",
    "credit balance",
    "credits have been exhausted",
    "top up your credits",
    "payment required",
    "billing hard limit",
    "exceeded your current quota",
    "account is deactivated",
    "plan does not include",
]

_RATE_LIMIT_PATTERNS = [
    "rate limit",
    "rate_limit",
    "too many requests",
    "throttled",
    "requests per minute",
    "tokens per minute",
    "requests per day",
    "try again in",
    "please retry after",
    "resource_exhausted",
    "rate increased too quickly",
    "throttlingexception",
    "too many concurrent requests",
    "servicequotaexceededexception",
]

_USAGE_LIMIT_PATTERNS = [
    "usage limit",
    "quota",
    "limit exceeded",
    "key limit exceeded",
]

_USAGE_LIMIT_TRANSIENT_SIGNALS = [
    "try again",
    "retry",
    "resets at",
    "reset in",
    "wait",
    "requests remaining",
    "periodic",
    "window",
]

_PAYLOAD_TOO_LARGE_PATTERNS = [
    "request entity too large",
    "payload too large",
    "error code: 413",
]

_CONTEXT_OVERFLOW_PATTERNS = [
    "context length",
    "context size",
    "maximum context",
    "token limit",
    "too many tokens",
    "reduce the length",
    "exceeds the limit",
    "context window",
    "prompt is too long",
    "prompt exceeds max length",
    "max_tokens",
    "maximum number of tokens",
    "exceeds the max_model_len",
    "max_model_len",
    "prompt length",
    "input is too long",
    "maximum model length",
    "context length exceeded",
    "truncating input",
    "slot context",
    "n_ctx_slot",
    "超过最大长度",
    "上下文长度",
    "max input token",
    "input token",
    "exceeds the maximum number of input tokens",
]

_MODEL_NOT_FOUND_PATTERNS = [
    "is not a valid model",
    "invalid model",
    "model not found",
    "model_not_found",
    "does not exist",
    "no such model",
    "unknown model",
    "unsupported model",
]

_AUTH_PATTERNS = [
    "invalid api key",
    "invalid_api_key",
    "authentication",
    "unauthorized",
    "forbidden",
    "invalid token",
    "token expired",
    "token revoked",
    "access denied",
]

_TRANSPORT_ERROR_TYPES = frozenset(
    {
        "ReadTimeout",
        "ConnectTimeout",
        "PoolTimeout",
        "ConnectError",
        "RemoteProtocolError",
        "ConnectionError",
        "ConnectionResetError",
        "ConnectionAbortedError",
        "BrokenPipeError",
        "TimeoutError",
        "ReadError",
        "ServerDisconnectedError",
        "APIConnectionError",
        "APITimeoutError",
    }
)

_SERVER_DISCONNECT_PATTERNS = [
    "server disconnected",
    "peer closed connection",
    "connection reset by peer",
    "connection was closed",
    "network connection lost",
    "unexpected eof",
    "incomplete chunked read",
]


# ── Helpers ─────────────────────────────────────────────────────────────


def _extract_status_code(error: Exception) -> Optional[int]:
    """尝试从异常对象中提取 HTTP 状态码。"""
    # OpenAI SDK errors
    if hasattr(error, "status_code"):
        sc = getattr(error, "status_code", None)
        if isinstance(sc, int):
            return sc
    # HTTPX / generic HTTP errors
    if hasattr(error, "response"):
        resp = getattr(error, "response", None)
        if resp is not None and hasattr(resp, "status_code"):
            sc = getattr(resp, "status_code", None)
            if isinstance(sc, int):
                return sc
    # Anthropic SDK
    if hasattr(error, "status_code"):
        sc = getattr(error, "status_code", None)
        if isinstance(sc, int):
            return sc
    # Message-based fallback
    msg = str(error).lower()
    for code in (401, 402, 403, 404, 413, 429, 500, 502, 503, 529):
        if f"{code}" in msg:
            return code
    return None


def _extract_error_body(error: Exception) -> dict[str, Any]:
    """尝试从异常对象中提取结构化错误体。"""
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        return body
    # OpenAI SDK
    if hasattr(error, "json_body"):
        jb = getattr(error, "json_body", None)
        if isinstance(jb, dict):
            return jb
    # Try to parse from message
    msg = str(error)
    try:
        parsed = json.loads(msg)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return {}


def _extract_error_code(body: dict[str, Any]) -> str:
    """从错误体中提取错误码字符串。"""
    if not isinstance(body, dict):
        return ""
    err = body.get("error", {})
    if isinstance(err, dict):
        code = err.get("code") or err.get("type") or ""
        if isinstance(code, str):
            return code.lower()
    code = body.get("code") or body.get("error_code") or ""
    if isinstance(code, str):
        return code.lower()
    return ""


def _extract_message(error: Exception, body: dict[str, Any]) -> str:
    """提取最佳可读错误消息。"""
    msg = str(error)
    if isinstance(body, dict):
        err = body.get("error", {})
        if isinstance(err, dict):
            body_msg = err.get("message", "")
            if body_msg and len(body_msg) > len(msg):
                return body_msg
        body_msg = body.get("message", "")
        if body_msg and len(body_msg) > len(msg):
            return body_msg
    return msg


# ── Status-code classification ──────────────────────────────────────────


def _classify_by_status(
    status_code: int,
    error_msg: str,
    error_code: str,
    body: dict[str, Any],
    *,
    result_fn,
) -> Optional[ClassifiedError]:
    if status_code == 401:
        return result_fn(
            FailoverReason.auth,
            retryable=False,
            should_rotate_credential=True,
            should_fallback=True,
        )

    if status_code == 403:
        # OpenRouter 403 "key limit exceeded" is actually billing
        if any(p in error_msg for p in _BILLING_PATTERNS):
            return result_fn(
                FailoverReason.billing,
                retryable=False,
                should_fallback=True,
            )
        return result_fn(
            FailoverReason.auth,
            retryable=False,
            should_rotate_credential=True,
            should_fallback=True,
        )

    if status_code == 402:
        return result_fn(
            FailoverReason.billing,
            retryable=False,
            should_fallback=True,
        )

    if status_code == 404:
        if any(p in error_msg for p in _MODEL_NOT_FOUND_PATTERNS):
            return result_fn(
                FailoverReason.model_not_found,
                retryable=False,
                should_fallback=True,
            )
        return result_fn(
            FailoverReason.auth,
            retryable=False,
            should_fallback=True,
        )

    if status_code == 413:
        return result_fn(
            FailoverReason.payload_too_large,
            retryable=True,
            should_compress=True,
        )

    if status_code == 429:
        # Billing vs rate-limit disambiguation
        if any(p in error_msg for p in _BILLING_PATTERNS):
            return result_fn(
                FailoverReason.billing,
                retryable=False,
                should_fallback=True,
            )
        if any(p in error_msg for p in _RATE_LIMIT_PATTERNS):
            return result_fn(
                FailoverReason.rate_limit,
                retryable=True,
                should_fallback=False,
            )
        # Usage-limit ambiguity resolution
        if any(p in error_msg for p in _USAGE_LIMIT_PATTERNS):
            if any(s in error_msg for s in _USAGE_LIMIT_TRANSIENT_SIGNALS):
                return result_fn(
                    FailoverReason.rate_limit,
                    retryable=True,
                    should_fallback=False,
                )
            return result_fn(
                FailoverReason.billing,
                retryable=False,
                should_fallback=True,
            )
        return result_fn(
            FailoverReason.rate_limit,
            retryable=True,
            should_fallback=False,
        )

    if status_code in (500, 502):
        return result_fn(
            FailoverReason.server_error,
            retryable=True,
            should_fallback=False,
        )

    if status_code in (503, 529):
        return result_fn(
            FailoverReason.overloaded,
            retryable=True,
            should_fallback=False,
        )

    return None


# ── Error-code classification ───────────────────────────────────────────


def _classify_by_error_code(
    error_code: str,
    error_msg: str,
    result_fn,
) -> Optional[ClassifiedError]:
    billing_codes = {
        "insufficient_quota",
        "payment_required",
        "billing_error",
        "credits_exhausted",
        "account_deactivated",
    }
    rate_limit_codes = {
        "rate_limit_exceeded",
        "quota_exceeded",
        "too_many_requests",
        "throttling",
        "resource_exhausted",
    }
    auth_codes = {
        "invalid_api_key",
        "authentication_error",
        "unauthorized",
        "forbidden",
        "invalid_token",
        "token_expired",
    }
    context_codes = {
        "context_length_exceeded",
        "max_tokens_exceeded",
        "prompt_too_long",
        "input_too_large",
    }
    model_codes = {
        "model_not_found",
        "invalid_model",
        "model_unavailable",
    }

    if error_code in billing_codes:
        return result_fn(
            FailoverReason.billing,
            retryable=False,
            should_fallback=True,
        )
    if error_code in rate_limit_codes:
        return result_fn(
            FailoverReason.rate_limit,
            retryable=True,
            should_fallback=False,
        )
    if error_code in auth_codes:
        return result_fn(
            FailoverReason.auth,
            retryable=False,
            should_rotate_credential=True,
            should_fallback=True,
        )
    if error_code in context_codes:
        return result_fn(
            FailoverReason.context_overflow,
            retryable=True,
            should_compress=True,
        )
    if error_code in model_codes:
        return result_fn(
            FailoverReason.model_not_found,
            retryable=False,
            should_fallback=True,
        )

    return None


# ── Message-pattern classification ──────────────────────────────────────


def _classify_by_message(
    error_msg: str,
    error_type: str,
    *,
    result_fn,
) -> Optional[ClassifiedError]:
    if any(p in error_msg for p in _BILLING_PATTERNS):
        return result_fn(
            FailoverReason.billing,
            retryable=False,
            should_fallback=True,
        )
    if any(p in error_msg for p in _RATE_LIMIT_PATTERNS):
        return result_fn(
            FailoverReason.rate_limit,
            retryable=True,
            should_fallback=False,
        )
    if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):
        return result_fn(
            FailoverReason.context_overflow,
            retryable=True,
            should_compress=True,
        )
    if any(p in error_msg for p in _PAYLOAD_TOO_LARGE_PATTERNS):
        return result_fn(
            FailoverReason.payload_too_large,
            retryable=True,
            should_compress=True,
        )
    if any(p in error_msg for p in _MODEL_NOT_FOUND_PATTERNS):
        return result_fn(
            FailoverReason.model_not_found,
            retryable=False,
            should_fallback=True,
        )
    if any(p in error_msg for p in _AUTH_PATTERNS):
        return result_fn(
            FailoverReason.auth,
            retryable=False,
            should_rotate_credential=True,
            should_fallback=True,
        )

    return None


# ── Public API ──────────────────────────────────────────────────────────


def classify_api_error(
    error: Exception,
    *,
    provider: str = "",
    model: str = "",
    approx_tokens: int = 0,
    context_length: int = 200000,
    num_messages: int = 0,
) -> ClassifiedError:
    """Classify an API error into a structured recovery recommendation.

    Priority-ordered pipeline:
      1. Provider-specific patterns (thinking sigs, tier gates)
      2. HTTP status code + message-aware refinement
      3. Error code classification (from body)
      4. Message pattern matching (billing vs rate_limit vs context vs auth)
      5. Transport error heuristics
      6. Server disconnect + large session → context overflow
      7. Fallback: unknown (retryable with backoff)
    """
    status_code = _extract_status_code(error)
    error_type = type(error).__name__
    body = _extract_error_body(error)
    error_code = _extract_error_code(body)

    # Build comprehensive error message for pattern matching
    _raw_msg = str(error).lower()
    _body_msg = ""
    _metadata_msg = ""
    if isinstance(body, dict):
        _err_obj = body.get("error", {})
        if isinstance(_err_obj, dict):
            _body_msg = (_err_obj.get("message") or "").lower()
            _metadata = _err_obj.get("metadata", {})
            if isinstance(_metadata, dict):
                _raw_json = _metadata.get("raw") or ""
                if isinstance(_raw_json, str) and _raw_json.strip():
                    try:
                        _inner = json.loads(_raw_json)
                        if isinstance(_inner, dict):
                            _inner_err = _inner.get("error", {})
                            if isinstance(_inner_err, dict):
                                _metadata_msg = (_inner_err.get("message") or "").lower()
                    except (json.JSONDecodeError, TypeError):
                        pass
        if not _body_msg:
            _body_msg = (body.get("message") or "").lower()

    parts = [_raw_msg]
    if _body_msg and _body_msg not in _raw_msg:
        parts.append(_body_msg)
    if _metadata_msg and _metadata_msg not in _raw_msg and _metadata_msg not in _body_msg:
        parts.append(_metadata_msg)
    error_msg = " ".join(parts)

    def _result(reason: FailoverReason, **overrides) -> ClassifiedError:
        defaults = {
            "reason": reason,
            "status_code": status_code,
            "provider": provider,
            "model": model,
            "message": _extract_message(error, body),
        }
        defaults.update(overrides)
        return ClassifiedError(**defaults)

    # 1. Provider-specific patterns (highest priority)
    if status_code == 400 and "signature" in error_msg and "thinking" in error_msg:
        return _result(
            FailoverReason.thinking_signature,
            retryable=True,
            should_compress=False,
        )

    if status_code == 429 and "extra usage" in error_msg and "long context" in error_msg:
        return _result(
            FailoverReason.long_context_tier,
            retryable=True,
            should_compress=True,
        )

    # 2. HTTP status code classification
    if status_code is not None:
        classified = _classify_by_status(
            status_code,
            error_msg,
            error_code,
            body,
            result_fn=_result,
        )
        if classified is not None:
            return classified

    # 3. Error code classification
    if error_code:
        classified = _classify_by_error_code(error_code, error_msg, _result)
        if classified is not None:
            return classified

    # 4. Message pattern matching (no status code)
    classified = _classify_by_message(error_msg, error_type, result_fn=_result)
    if classified is not None:
        return classified

    # 5. Server disconnect + large session → context overflow
    is_disconnect = any(p in error_msg for p in _SERVER_DISCONNECT_PATTERNS)
    if is_disconnect and not status_code:
        is_large = (
            approx_tokens > context_length * 0.6 or approx_tokens > 120000 or num_messages > 200
        )
        if is_large:
            return _result(
                FailoverReason.context_overflow,
                retryable=True,
                should_compress=True,
            )
        return _result(FailoverReason.timeout, retryable=True)

    # 6. Transport / timeout heuristics
    if error_type in _TRANSPORT_ERROR_TYPES or isinstance(
        error, (TimeoutError, ConnectionError, OSError)
    ):
        return _result(FailoverReason.timeout, retryable=True)

    # 7. Fallback: unknown
    return _result(FailoverReason.unknown, retryable=True)
