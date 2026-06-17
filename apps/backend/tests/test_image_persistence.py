"""
图片持久化链路端到端测试

验证：
1. build_attachment_content_parts 生成 file:// URI（而非 data URL）
2. hydrate_message_images 把 file:// URI 转成 data URL
3. data URL 格式正确、可解析
"""

from pathlib import Path

import pytest

from app.services.agent.message_content import (
    build_attachment_content_parts,
    hydrate_message_images,
    split_data_url,
)


def test_build_attachment_generates_file_uri(tmp_path: Path) -> None:
    """transport_parts 应该存 file:// URI，不是 data URL。"""
    workspace_dir = tmp_path
    image_path = workspace_dir / "test.png"
    image_path.write_bytes(b"fake-png-data")

    result = build_attachment_content_parts(
        attachments=["/workspace/test.png"],
        workspace_dir=workspace_dir,
    )

    assert len(result.transport_parts) == 1
    part = result.transport_parts[0]
    assert part["type"] == "image_url"

    url = part["image_url"]["url"]
    assert url.startswith("file://"), f"期望 file:// URI，实际: {url[:50]}"
    assert "/workspace/test.png" in url

    # display_parts 仍保留 workspace 路径
    assert len(result.display_parts) == 1
    disp = result.display_parts[0]
    assert disp["image_url"]["url"] == "/workspace/test.png"


def test_hydrate_message_images_converts_file_to_data_url(tmp_path: Path) -> None:
    """hydrate_message_images 把 file:// URI 转成 data URL。"""
    image_path = tmp_path / "workspace" / "test.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"fake-png-data")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "请看这张图"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"file://{image_path}"},
                },
            ],
        }
    ]

    hydrated = hydrate_message_images(messages)

    # 不修改原消息
    assert messages[0]["content"][1]["image_url"]["url"].startswith("file://")

    # hydrated 后是 data URL
    assert len(hydrated) == 1
    parts = hydrated[0]["content"]
    assert parts[0]["type"] == "text"

    img_part = parts[1]
    assert img_part["type"] == "image_url"
    url = img_part["image_url"]["url"]
    assert url.startswith("data:image/png;base64,"), f"期望 data URL，实际: {url[:50]}"

    mime_type, encoded = split_data_url(url)
    assert mime_type == "image/png"
    assert encoded is not None
    assert len(encoded) > 10


def test_hydrate_message_images_resolves_workspace_file_uri(tmp_path: Path) -> None:
    """hydrate_message_images 能把 file:///workspace/... 映射到当前工作区。"""
    image_path = tmp_path / "test.png"
    image_path.write_bytes(b"fake-png-data")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "请看这张图"},
                {
                    "type": "image_url",
                    "image_url": {"url": "file:///workspace/test.png"},
                    "source_path": "/workspace/test.png",
                },
            ],
        }
    ]

    hydrated = hydrate_message_images(messages, workspace_dir=tmp_path)

    url = hydrated[0]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,"), f"期望 data URL，实际: {url[:50]}"


def test_hydrate_message_images_keeps_workspace_file_uri_without_workspace_dir() -> None:
    """缺少工作区上下文时，文件无法解析，降级为文字占位符。"""
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "file:///workspace/test.png"},
                    "source_path": "/workspace/test.png",
                },
            ],
        }
    ]

    hydrated = hydrate_message_images(messages)
    # 无 workspace_dir 时无法解析路径，降级为文字占位符
    assert hydrated[0]["content"][0]["type"] == "text"
    assert "[图片文件无法解析:" in hydrated[0]["content"][0]["text"]


def test_hydrate_message_images_uses_source_path_fallback(tmp_path: Path) -> None:
    """传输 URL 失效时，可以用 source_path 找回当前工作区文件。"""
    image_path = tmp_path / "test.png"
    image_path.write_bytes(b"fake-png-data")

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "file:///tmp/not-exist.png"},
                    "source_path": "/workspace/test.png",
                },
            ],
        }
    ]

    hydrated = hydrate_message_images(messages, workspace_dir=tmp_path)

    url = hydrated[0]["content"][0]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,"), f"期望 data URL，实际: {url[:50]}"


def test_hydrate_preserves_non_image_messages() -> None:
    """不含图片的消息应该原样返回。"""
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
    ]
    hydrated = hydrate_message_images(messages)
    assert hydrated == messages


def test_hydrate_skips_missing_files(tmp_path: Path) -> None:
    """file:// 指向不存在的文件时，降级为文字占位符。"""
    missing_path = tmp_path / "not_exist.png"
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"file://{missing_path}"},
                },
            ],
        }
    ]
    hydrated = hydrate_message_images(messages)
    # 文件不存在时降级为文字占位符
    assert hydrated[0]["content"][0]["type"] == "text"
    assert "[图片文件" in hydrated[0]["content"][0]["text"]
