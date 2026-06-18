"""测试 Agent 运行时可独立配置多模态/非多模态模型。

这些测试不依赖 AIASys 系统的 config.toml，而是使用 conftest.py 提供的
`isolated_llm_config` fixture 独立准备模型配置。
"""

from __future__ import annotations

from app.services.agent.message_content import (
    downgrade_message_content_for_history,
    hydrate_message_images,
)


def test_isolated_fixture_creates_text_and_multimodal_models(isolated_llm_config):
    """独立 fixture 应同时创建纯文本和多模态模型，且 capabilities 区分正确。"""
    service = isolated_llm_config["service"]
    user_id = isolated_llm_config["user_id"]

    text_model = service.get_model(user_id, isolated_llm_config["text_model_id"])
    multimodal_model = service.get_model(user_id, isolated_llm_config["multimodal_model_id"])

    assert text_model is not None
    assert text_model.capabilities == set()
    assert text_model.max_context_size == 256000

    assert multimodal_model is not None
    assert multimodal_model.capabilities == {"thinking", "image_in", "video_in"}
    assert multimodal_model.max_context_size == 256000


def test_isolated_fixture_default_model_is_multimodal(isolated_llm_config):
    """独立 fixture 的默认模型应设为多模态模型，便于测试图像输入路径。"""
    service = isolated_llm_config["service"]
    defaults = service.get_model_defaults(isolated_llm_config["user_id"])

    assert defaults.default_chat_model == isolated_llm_config["multimodal_model_id"]


def test_multimodal_message_path_hydrates_image_reference():
    """多模态处理路径：image_url 在文件不存在时降级为文字占位符。

    该函数直接模拟 `SessionStreamMixin._prepare_messages_for_current_model`
    中模型具备 `image_in` 能力时的处理分支。
    """
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "分析图片"},
                {
                    "type": "image_url",
                    "image_url": {"url": "file:///workspace/chart.png"},
                    "source_path": "/workspace/chart.png",
                },
            ],
        }
    ]

    hydrated = hydrate_message_images(messages, workspace_dir=None)

    # 文件不存在时降级为文字占位符（不发无效 URI 给 LLM）
    assert hydrated[0]["content"][1]["type"] == "text"
    assert "[图片文件无法解析:" in hydrated[0]["content"][1]["text"]


def test_non_multimodal_message_path_downgrades_image_url():
    """非多模态处理路径：image_url 应被降级为 image_reference。

    该函数直接模拟 `SessionStreamMixin._prepare_messages_for_current_model`
    中模型不具备 `image_in` 能力时的处理分支。
    """
    content = [
        {"type": "text", "text": "分析图片"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,AAAA"},
            "source_path": "/workspace/chart.png",
        },
    ]

    downgraded = downgrade_message_content_for_history(content)

    assert downgraded[1]["type"] == "image_reference"
    assert downgraded[1]["source_path"] == "/workspace/chart.png"
