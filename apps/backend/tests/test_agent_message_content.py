from pathlib import Path

import pytest

from app.services.agent.message_content import (
    build_attachment_content_parts,
    build_content_signature,
    downgrade_message_content_for_history,
    extract_image_paths,
    message_content_to_anthropic_input,
    message_content_to_openai_input,
    message_content_to_responses_input,
)
from app.services.agent.mixins.execution import _build_transport_user_input


def _multimodal_content(data_url: str) -> list[dict]:
    return [
        {"type": "text", "text": "看看这张图"},
        {
            "type": "image_url",
            "image_url": {
                "url": data_url,
                "detail": "auto",
            },
            "source_path": "/workspace/chart.png",
        },
    ]


def test_build_attachment_content_parts_converts_workspace_images(tmp_path: Path) -> None:
    (tmp_path / "chart.png").write_bytes(b"fake-image")
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")

    projection = build_attachment_content_parts(
        attachments=["chart.png", "notes.txt"],
        workspace_dir=tmp_path,
    )

    assert projection.image_paths == ["/workspace/chart.png"]
    assert projection.display_parts == [
        {
            "type": "image_url",
            "image_url": {
                "url": "/workspace/chart.png",
                "detail": "auto",
            },
            "source_path": "/workspace/chart.png",
        }
    ]
    assert projection.transport_parts[0]["type"] == "image_url"
    assert projection.transport_parts[0]["source_path"] == "/workspace/chart.png"
    assert projection.transport_parts[0]["image_url"]["url"].startswith(
        "file:///workspace/chart.png"
    )


def test_build_content_signature_ignores_data_url_body_when_source_path_matches() -> None:
    transport = _multimodal_content("data:image/png;base64,ZmFrZQ==")
    display = _multimodal_content("/workspace/chart.png")

    assert build_content_signature(transport) == build_content_signature(display)


def test_downgrade_message_content_for_history_replaces_inline_images() -> None:
    transport = _multimodal_content("data:image/png;base64,ZmFrZQ==")

    downgraded = downgrade_message_content_for_history(transport)

    assert downgraded == [
        {"type": "text", "text": "看看这张图"},
        {
            "type": "image_reference",
            "source_path": "/workspace/chart.png",
        },
    ]
    assert build_content_signature(downgraded) == build_content_signature(transport)


def test_message_content_converters_support_multimodal_inputs() -> None:
    content = _multimodal_content("data:image/png;base64,ZmFrZQ==")

    openai_blocks = message_content_to_openai_input(content)
    assert openai_blocks == [
        {"type": "text", "text": "看看这张图"},
        {
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64,ZmFrZQ==",
                "detail": "auto",
            },
        },
    ]

    anthropic_blocks = message_content_to_anthropic_input(content)
    assert anthropic_blocks == [
        {"type": "text", "text": "看看这张图"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "ZmFrZQ==",
            },
        },
    ]

    responses_blocks = message_content_to_responses_input(content)
    assert responses_blocks == [
        {"type": "input_text", "text": "看看这张图"},
        {"type": "input_image", "image_url": "data:image/png;base64,ZmFrZQ=="},
    ]

    assert extract_image_paths(content) == ["/workspace/chart.png"]

    downgraded_blocks = downgrade_message_content_for_history(content)
    assert message_content_to_openai_input(downgraded_blocks) == [
        {"type": "text", "text": "看看这张图"},
        {
            "type": "text",
            "text": "[历史图片引用已降级，未自动继续携带图片内容：/workspace/chart.png。如果需要重新查看这张图，请让用户重新附带该图片。]",
        },
    ]


def test_build_transport_user_input_persists_file_uri_transport_content(
    tmp_path: Path,
) -> None:
    (tmp_path / "chart.png").write_bytes(b"fake-image")

    user_input, display_content, transport_content = _build_transport_user_input(
        prompt="看看这张图",
        transport_prompt="[USER_TASK]\n看看这张图",
        attachments=["/workspace/chart.png"],
        workspace_path=tmp_path,
        model_capabilities={"image_in"},
    )

    assert user_input == [{"role": "user", "content": transport_content}]
    assert display_content == [
        {"type": "text", "text": "看看这张图"},
        {
            "type": "image_url",
            "image_url": {
                "url": "/workspace/chart.png",
                "detail": "auto",
            },
            "source_path": "/workspace/chart.png",
        },
    ]
    assert transport_content[0] == {"type": "text", "text": "[USER_TASK]\n看看这张图"}
    assert transport_content[1]["source_path"] == "/workspace/chart.png"
    assert transport_content[1]["image_url"]["url"].startswith(
        "file:///workspace/chart.png"
    )


def test_build_transport_user_input_rejects_image_for_text_only_model(
    tmp_path: Path,
) -> None:
    (tmp_path / "chart.png").write_bytes(b"fake-image")

    with pytest.raises(RuntimeError, match="当前模型不支持图片输入"):
        _build_transport_user_input(
            prompt="看看这张图",
            transport_prompt="[USER_TASK]\n看看这张图",
            attachments=["/workspace/chart.png"],
            workspace_path=tmp_path,
            model_capabilities=set(),
        )
