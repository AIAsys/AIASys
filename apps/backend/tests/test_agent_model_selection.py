from app.services.agent import _select_preferred_agent_model_id


def test_agent_prefers_configured_default_model():
    """优先使用用户配置的默认模型，不再硬编码厂商偏好。"""
    providers = {
        "kimi": {"type": "anthropic_messages"},
        "dashscope": {"type": "openai_chat_completions"},
    }
    models = {
        "deepseek-v3-aliyun": {
            "provider": "dashscope",
            "model": "deepseek-v3",
        },
        "kimi-official-coding": {
            "provider": "kimi",
            "model": "kimi-for-coding",
        },
    }

    selected = _select_preferred_agent_model_id(
        models=models,
        providers=providers,
        configured_default_model="deepseek-v3-aliyun",
    )

    assert selected == "deepseek-v3-aliyun"


def test_agent_falls_back_to_first_available_when_configured_default_missing():
    """配置的默认模型不在可用列表中时，fallback 到第一个可用模型。"""
    providers = {
        "kimi": {"type": "anthropic_messages"},
        "responses": {"type": "openai_responses"},
        "dashscope": {"type": "openai_chat_completions"},
    }
    models = {
        "deepseek-v3-aliyun": {
            "provider": "dashscope",
            "model": "deepseek-v3",
        },
        "kimi-official-coding": {
            "provider": "kimi",
            "model": "kimi-for-coding",
        },
        "openai-responses-8317-default": {
            "provider": "responses",
            "model": "gpt-5.4",
        },
    }

    selected = _select_preferred_agent_model_id(
        models=models,
        providers=providers,
        configured_default_model="nonexistent-model",
    )

    assert selected == "deepseek-v3-aliyun"


def test_agent_falls_back_to_configured_default_when_only_one_model():
    """只有一个可用模型时，直接返回该模型（无论 configured_default 是否匹配）。"""
    providers = {
        "dashscope": {"type": "openai_chat_completions"},
    }
    models = {
        "deepseek-v3-aliyun": {
            "provider": "dashscope",
            "model": "deepseek-v3",
        },
    }

    selected = _select_preferred_agent_model_id(
        models=models,
        providers=providers,
        configured_default_model="deepseek-v3-aliyun",
    )

    assert selected == "deepseek-v3-aliyun"


def test_agent_returns_configured_default_when_no_models():
    """没有可用模型时，返回 configured_default_model（由调用方兜底报错）。"""
    selected = _select_preferred_agent_model_id(
        models={},
        providers={},
        configured_default_model="some-model",
    )

    assert selected == "some-model"
