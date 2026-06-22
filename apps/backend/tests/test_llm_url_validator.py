"""Tests for app.utils.llm_url_validator."""

from __future__ import annotations

import pytest

from app.utils.llm_url_validator import validate_llm_base_url


@pytest.mark.parametrize(
    "url",
    [
        # 公网地址
        "https://api.stepfun.com/v1",
        "https://api.kimi.com/coding/v1",
        "https://api.openai.com/v1",
        "http://public.example.com/v1",
        # 本地/私有地址（AIASys 是本地部署桌面应用，允许本地 LLM 如 Ollama）
        "http://localhost:13001/",
        "http://127.0.0.1:13001/",
        "http://[::1]/",
        "http://0.0.0.0/",
        "http://192.168.1.1/",
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://foo.local/",
        "http://foo.localhost/",
        "http://127.0.0.1:11434/v1",
    ],
)
def test_validate_llm_base_url_allows_public_and_local_urls(url: str) -> None:
    validate_llm_base_url(url)


@pytest.mark.parametrize(
    "url",
    [
        # 云厂商 metadata 地址
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
        "http://metadata.oracle.internal/",
        # 云内部域名
        "http://foo.internal/",
        # 非法协议与格式
        "ftp://example.com/",
        "",
        "not-a-url",
    ],
)
def test_validate_llm_base_url_rejects_cloud_metadata_and_malformed_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_llm_base_url(url)
