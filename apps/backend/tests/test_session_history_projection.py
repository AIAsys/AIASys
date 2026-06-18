from app.services.history.session_history_projection import (
    apply_display_content_to_history,
    wrap_user_prompt,
    unwrap_user_prompt,
)


def test_apply_display_content_ignores_older_orphan_entries_after_compact() -> None:
    history = [
        {
            "role": "user",
            "content": "wrapped-latest",
            "timestamp": "2026-04-07T20:53:52.538606",
        },
        {
            "role": "assistant",
            "content": "ok",
            "timestamp": "2026-04-07T20:54:20.000000",
        },
    ]
    display_entries = [
        {
            "role": "user",
            "content": "older-first",
            "transport_content": "older-first-transport",
            "timestamp": "2026-04-07T20:44:59.002443",
        },
        {
            "role": "user",
            "content": "older-second",
            "transport_content": "older-second-transport",
            "timestamp": "2026-04-07T20:45:00.785176",
        },
        {
            "role": "user",
            "content": "latest-visible",
            "transport_content": "wrapped-latest",
            "timestamp": "2026-04-07T20:53:52.538606",
        },
    ]

    hydrated = apply_display_content_to_history(history, display_entries)

    user_contents = [
        item.get("display_content") or item.get("content")
        for item in hydrated
        if item.get("role") == "user"
    ]
    assert user_contents == ["latest-visible"]


def test_apply_display_content_keeps_newer_unmatched_entry_when_sdk_history_lags() -> None:
    history = [
        {
            "role": "user",
            "content": "wrapped-previous",
            "timestamp": "2026-04-07T20:53:52.538606",
        },
        {
            "role": "assistant",
            "content": "ok",
            "timestamp": "2026-04-07T20:54:20.000000",
        },
    ]
    display_entries = [
        {
            "role": "user",
            "content": "previous-visible",
            "transport_content": "wrapped-previous",
            "timestamp": "2026-04-07T20:53:52.538606",
        },
        {
            "role": "user",
            "content": "latest-visible",
            "transport_content": "wrapped-latest",
            "timestamp": "2026-04-07T20:55:00.000000",
        },
    ]

    hydrated = apply_display_content_to_history(history, display_entries)

    user_contents = [
        item.get("display_content") or item.get("content")
        for item in hydrated
        if item.get("role") == "user"
    ]
    assert user_contents == ["previous-visible", "latest-visible"]


def test_apply_display_content_can_backfill_older_entries_for_truncated_sessions() -> None:
    history = [
        {
            "role": "user",
            "content": "wrapped-latest",
            "timestamp": "2026-04-09T19:36:07.657765",
        },
        {
            "role": "assistant",
            "content": "你好！有什么我可以帮你的吗？",
            "timestamp": "2026-04-09T19:36:08.000000",
        },
    ]
    display_entries = [
        {
            "role": "user",
            "content": "older-first",
            "transport_content": "wrapped-first",
            "timestamp": "2026-04-07T20:44:59.002443",
        },
        {
            "role": "user",
            "content": "older-second",
            "transport_content": "wrapped-second",
            "timestamp": "2026-04-07T20:45:00.785176",
        },
        {
            "role": "user",
            "content": "latest-visible",
            "transport_content": "wrapped-latest",
            "timestamp": "2026-04-09T19:36:07.657765",
        },
    ]

    hydrated = apply_display_content_to_history(
        history,
        display_entries,
        allow_older_orphan_entries=True,
    )

    user_contents = [
        item.get("display_content") or item.get("content")
        for item in hydrated
        if item.get("role") == "user"
    ]
    assert user_contents == ["older-first", "older-second", "latest-visible"]


def test_apply_display_content_uses_display_timestamps_to_keep_order_stable() -> None:
    history = [
        {
            "role": "user",
            "content": "wrapped-latest",
            "timestamp": None,
        },
        {
            "role": "assistant",
            "content": "latest-answer",
            "timestamp": None,
        },
    ]
    display_entries = [
        {
            "role": "user",
            "content": "older-visible",
            "transport_content": "wrapped-older",
            "timestamp": "2026-04-07T20:44:59.002443",
        },
        {
            "role": "user",
            "content": "latest-visible",
            "transport_content": "wrapped-latest",
            "timestamp": "2026-04-09T19:36:07.657765",
        },
    ]

    hydrated = apply_display_content_to_history(
        history,
        display_entries,
        allow_older_orphan_entries=True,
    )

    assert [
        (item.get("role"), item.get("display_content") or item.get("content")) for item in hydrated
    ] == [
        ("user", "older-visible"),
        ("user", "latest-visible"),
        ("assistant", "latest-answer"),
    ]


def test_apply_display_content_matches_structured_user_messages() -> None:
    history = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "wrapped-visible"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,ZmFrZQ=="},
                    "source_path": "/workspace/chart.png",
                },
            ],
            "timestamp": "2026-04-21T00:00:00.000000",
        },
        {
            "role": "assistant",
            "content": "ok",
            "timestamp": "2026-04-21T00:00:01.000000",
        },
    ]
    display_entries = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "visible"},
                {
                    "type": "image_url",
                    "image_url": {"url": "/workspace/chart.png"},
                    "source_path": "/workspace/chart.png",
                },
            ],
            "transport_content": [
                {"type": "text", "text": "wrapped-visible"},
                {
                    "type": "image_url",
                    "image_url": {"url": "/workspace/chart.png"},
                    "source_path": "/workspace/chart.png",
                },
            ],
            "timestamp": "2026-04-21T00:00:00.000000",
        }
    ]

    hydrated = apply_display_content_to_history(history, display_entries)

    assert hydrated[0]["display_content"] == display_entries[0]["content"]
    assert hydrated[0]["transport_content"] == display_entries[0]["transport_content"]


def test_apply_display_content_matches_downgraded_image_reference_history() -> None:
    history = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "wrapped-visible"},
                {
                    "type": "image_reference",
                    "source_path": "/workspace/chart.png",
                },
            ],
            "timestamp": "2026-04-21T00:00:00.000000",
        }
    ]
    display_entries = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "visible"},
                {
                    "type": "image_url",
                    "image_url": {"url": "/workspace/chart.png"},
                    "source_path": "/workspace/chart.png",
                },
            ],
            "transport_content": [
                {"type": "text", "text": "wrapped-visible"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,ZmFrZQ=="},
                    "source_path": "/workspace/chart.png",
                },
            ],
            "timestamp": "2026-04-21T00:00:00.000000",
        }
    ]

    hydrated = apply_display_content_to_history(history, display_entries)

    assert hydrated[0]["display_content"] == display_entries[0]["content"]


def test_wrap_user_prompt_keeps_source_in_user_task_text() -> None:
    wrapped = wrap_user_prompt("请处理这个请求\n\n（来自微信）")

    assert "[MESSAGE_SOURCE]" not in wrapped
    assert unwrap_user_prompt(wrapped) == "请处理这个请求\n\n（来自微信）"


def test_wrap_user_prompt_contract_does_not_force_review_requests_to_execute() -> None:
    prompt = "你看看这个系统提示词设计怎么样？"

    wrapped = wrap_user_prompt(prompt)

    assert "审查、咨询、评估或复盘请求" in wrapped
    assert "不要默认写文件、安装 Skill、启用运行环境、更新配置或启动长任务" in wrapped
    assert "否则直接执行" not in wrapped
    assert unwrap_user_prompt(wrapped) == prompt
