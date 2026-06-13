"""测试多模态与非多模态消息内容的转换行为。

核心差异：模型 capabilities 包含 `image_in` 时，系统会把图片引用 hydrate 为
base64 data URL；不包含时，历史消息中的图片会被降级为 `image_reference`，
避免向纯文本模型发送图像内容。
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from app.services.agent.message_content import (
    downgrade_message_content_for_history,
    hydrate_message_images,
    split_data_url,
)

# 1x1 透明 PNG
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """在临时目录创建一张真实 PNG 图片。"""
    path = tmp_path / "test.png"
    path.write_bytes(_PNG_BYTES)
    return path


def test_hydrate_message_images_converts_file_url_to_data_url(sample_image: Path):
    """多模态模型调用前，file:// 图片引用应被 hydrate 为 data URL。"""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "看看这张图"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"file://{sample_image}"},
                    "source_path": str(sample_image),
                },
            ],
        }
    ]

    hydrated = hydrate_message_images(messages, workspace_dir=sample_image.parent)

    assert len(hydrated) == 1
    parts = hydrated[0]["content"]
    assert len(parts) == 2
    assert parts[0]["type"] == "text"

    image_part = parts[1]
    assert image_part["type"] == "image_url"
    url = image_part["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")

    mime_type, encoded = split_data_url(url)
    assert mime_type == "image/png"
    assert base64.b64decode(encoded) == _PNG_BYTES


def test_hydrate_message_images_keeps_non_file_url_unchanged():
    """非 file:// 的 image_url 应原样保留。"""
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.com/image.png"},
                }
            ],
        }
    ]

    hydrated = hydrate_message_images(messages)

    assert hydrated[0]["content"][0]["image_url"]["url"] == "https://example.com/image.png"


def test_downgrade_message_content_for_history_replaces_image_with_reference():
    """非多模态模型的历史消息应把 image_url 降级为 image_reference。"""
    content = [
        {"type": "text", "text": "看看这张图"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,AAAA"},
            "source_path": "/workspace/test.png",
        },
    ]

    downgraded = downgrade_message_content_for_history(content)

    assert isinstance(downgraded, list)
    assert len(downgraded) == 2
    assert downgraded[0]["type"] == "text"

    image_part = downgraded[1]
    assert image_part["type"] == "image_reference"
    assert image_part["source_path"] == "/workspace/test.png"
    assert "image_url" not in image_part


def test_downgrade_message_content_for_history_keeps_text_unchanged():
    """纯文本内容降级后应保持不变。"""
    content = [{"type": "text", "text": "只有文字"}]
    downgraded = downgrade_message_content_for_history(content)
    assert downgraded == content


def test_split_data_url_parses_valid_data_url():
    """data URL 解析应正确提取 mime type 和 base64 内容。"""
    encoded = base64.b64encode(_PNG_BYTES).decode("ascii")
    url = f"data:image/png;base64,{encoded}"

    mime_type, decoded = split_data_url(url)
    assert mime_type == "image/png"
    assert base64.b64decode(decoded) == _PNG_BYTES


def test_split_data_url_returns_none_for_invalid_url():
    """非 data URL 应返回 None。"""
    assert split_data_url("https://example.com/image.png") == (None, None)
    assert split_data_url("data:text/plain,not-base64") == (None, None)
