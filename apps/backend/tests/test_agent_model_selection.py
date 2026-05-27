from app.services.agent import _select_preferred_agent_model_id


def test_agent_prefers_kimi_coding_model_over_config_default():
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

    assert selected == "kimi-official-coding"


def test_agent_prefers_kimi_coding_model_over_openai_responses_default():
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
        configured_default_model="openai-responses-8317-default",
    )

    assert selected == "kimi-official-coding"


def test_agent_falls_back_to_config_default_when_no_kimi_model():
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
