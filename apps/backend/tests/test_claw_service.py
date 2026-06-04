from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.models.claw import SessionClawBindingRequest
from app.services.channel import ChannelEntry, get_channel_config
from app.services.claw import ClawService
from app.services.memory import SessionDB
from app.services.session import SessionManager



def _build_service(tmp_path: Path) -> tuple[ClawService, SessionManager]:
    session_manager = SessionManager(tmp_path)
    service = ClawService(tmp_path, session_manager=session_manager)
    return service, session_manager


def _create_session(session_manager: SessionManager, *, user_id: str, session_id: str) -> None:
    session_manager.create_session(session_id=session_id, user_id=user_id, title="Claw 测试会话")


def _create_test_channel(service: ClawService, user_id: str, **kwargs) -> str:
    channel_id = kwargs.pop("channel_id", f"test_{uuid4().hex[:12]}")
    entry = ChannelEntry(channel_id=channel_id, enabled=True, **kwargs)
    get_channel_config(user_id, workspace_root=service.workspace_root).set_channel(entry)
    return channel_id




def test_claw_connector_and_binding_lifecycle(tmp_path: Path) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_id = "claw-session"
    _create_session(session_manager, user_id=user_id, session_id=session_id)

    channel_id = _create_test_channel(
        service,
        user_id,
        platform="weixin",
        name="我的微信 A",
        account_id="wx_account_a",
        token="secret-token-a",
    )

    binding = service.save_session_binding(
        user_id,
        session_id,
        SessionClawBindingRequest(
            connector_id=channel_id,
            chat_id="wx-chat-alpha",
            chat_label="客户群",
        ),
    )
    assert binding.connector_id == channel_id
    assert binding.chat_id == "wx-chat-alpha"
    assert binding.link_status == "stopped"

    running = service.start_session_link(user_id, session_id)
    assert running.link_status == "running"
    assert running.auto_sync_enabled is True

    rebound = service.save_session_binding(
        user_id,
        session_id,
        SessionClawBindingRequest(
            connector_id=channel_id,
            chat_id="wx-chat-beta",
            chat_label="另一个群",
        ),
    )
    assert rebound.chat_id == "wx-chat-beta"
    assert rebound.link_status == "stopped"
    assert rebound.auto_sync_enabled is False


def test_claw_platform_catalog_has_three_ready_platforms(tmp_path: Path) -> None:
    service, _session_manager = _build_service(tmp_path)

    platforms = service.list_platforms()

    assert len(platforms) == 3
    assert platforms[0].platform == "weixin"
    assert platforms[0].runtime_enabled is True
    assert platforms[0].supports_typing is True
    assert any(
        item.platform == "feishu"
        and item.support_status == "ready"
        and item.runtime_enabled is True
        for item in platforms
    )
    assert any(
        item.platform == "dingtalk"
        and item.support_status == "ready"
        and item.runtime_enabled is True
        for item in platforms
    )


def test_save_session_binding_rejects_conflict_when_same_chat_bound_to_other_session(
    tmp_path: Path,
) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_a = "claw-session-a"
    session_b = "claw-session-b"
    _create_session(session_manager, user_id=user_id, session_id=session_a)
    _create_session(session_manager, user_id=user_id, session_id=session_b)

    channel_id = _create_test_channel(
        service,
        user_id,
        platform="weixin",
        name="我的微信 A",
        account_id="wx_account_a",
        token="secret-token-a",
    )

    # Session A 先绑定并启动
    service.save_session_binding(
        user_id,
        session_a,
        SessionClawBindingRequest(
            connector_id=channel_id,
            chat_id="wx-chat-alpha",
            chat_label="客户群",
        ),
    )
    service.start_session_link(user_id, session_a)

    # Session B 尝试绑定同一个 running chat，应被拒绝
    with pytest.raises(ValueError, match="已被会话"):
        service.save_session_binding(
            user_id,
            session_b,
            SessionClawBindingRequest(
                connector_id=channel_id,
                chat_id="wx-chat-alpha",
                chat_label="客户群",
            ),
        )

    # Session B 绑定不同的 chat，应成功
    binding_b = service.save_session_binding(
        user_id,
        session_b,
        SessionClawBindingRequest(
            connector_id=channel_id,
            chat_id="wx-chat-beta",
            chat_label="另一个群",
        ),
    )
    assert binding_b.chat_id == "wx-chat-beta"


def test_save_session_binding_allows_rebind_after_other_session_cleared(
    tmp_path: Path,
) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_a = "claw-session-a"
    session_b = "claw-session-b"
    _create_session(session_manager, user_id=user_id, session_id=session_a)
    _create_session(session_manager, user_id=user_id, session_id=session_b)

    channel_id = _create_test_channel(
        service,
        user_id,
        platform="weixin",
        name="我的微信 A",
        account_id="wx_account_a",
        token="secret-token-a",
    )

    # Session A 绑定并启动
    service.save_session_binding(
        user_id,
        session_a,
        SessionClawBindingRequest(
            connector_id=channel_id,
            chat_id="wx-chat-alpha",
        ),
    )
    service.start_session_link(user_id, session_a)

    # Session A 解绑
    service.clear_session_binding(user_id, session_a)

    # Session B 现在可以绑定同一个 chat
    binding_b = service.save_session_binding(
        user_id,
        session_b,
        SessionClawBindingRequest(
            connector_id=channel_id,
            chat_id="wx-chat-alpha",
        ),
    )
    assert binding_b.chat_id == "wx-chat-alpha"



def test_claw_outbound_preview_ignores_think_content(tmp_path: Path) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_id = "claw-session"
    _create_session(session_manager, user_id=user_id, session_id=session_id)

    channel_id = _create_test_channel(
        service,
        user_id,
        platform="weixin",
        name="我的微信 A",
        account_id="wx_account_a",
        token="secret-token-a",
    )
    service.save_session_binding(
        user_id,
        session_id,
        SessionClawBindingRequest(
            connector_id=channel_id,
            chat_id="wx-chat-alpha",
        ),
    )
    session_manager.add_message(
        session_id,
        user_id,
        {
            "role": "assistant",
            "content": [
                {"type": "think", "think": "内部推理"},
                {"type": "text", "text": "这是同步给微信的最终回复。"},
            ],
            "timestamp": "2026-04-19T23:00:00+00:00",
        },
    )

    preview = service.get_outbound_preview(user_id, session_id)
    assert preview.has_candidate is True
    assert preview.raw_text == "这是同步给微信的最终回复。"
    assert "内部推理" not in preview.formatted_text
    assert preview.source_timestamp == "2026-04-19T23:00:00+00:00"


def test_claw_outbound_preview_prefers_session_db_over_session_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_id = "claw-session"
    _create_session(session_manager, user_id=user_id, session_id=session_id)

    channel_id = _create_test_channel(
        service,
        user_id,
        platform="weixin",
        name="我的微信 A",
        account_id="wx_account_a",
        token="secret-token-a",
    )
    service.save_session_binding(
        user_id,
        session_id,
        SessionClawBindingRequest(
            connector_id=channel_id,
            chat_id="wx-chat-alpha",
        ),
    )

    SessionDB(service._get_session_memory_db_path(user_id, session_id)).add_message(
        session_id,
        user_id,
        "assistant",
        "SessionDB 里的最终回复。",
    )

    def _unexpected_history(*_args, **_kwargs) -> list[dict[str, object]]:
        raise AssertionError(
            "SessionManager history should not be consulted when SessionDB has messages"
        )

    monkeypatch.setattr(service.session_manager, "get_history", _unexpected_history)
    monkeypatch.setattr(
        service,
        "_format_for_weixin",
        lambda *_args, text, **_kwargs: (text, [text]),
    )

    preview = service.get_outbound_preview(user_id, session_id)
    assert preview.has_candidate is True
    assert preview.raw_text == "SessionDB 里的最终回复。"
    assert preview.formatted_text == "SessionDB 里的最终回复。"
    assert preview.source_timestamp is not None


@pytest.mark.asyncio
async def test_claw_outbound_preview_extracts_workspace_attachments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_id = "claw-session"
    _create_session(session_manager, user_id=user_id, session_id=session_id)

    channel_id = _create_test_channel(
        service,
        user_id,
        platform="weixin",
        name="我的微信 A",
        account_id="wx_account_a",
        token="secret-token-a",
    )
    service.save_session_binding(
        user_id,
        session_id,
        SessionClawBindingRequest(
            connector_id=channel_id,
            chat_id="wx-chat-alpha",
        ),
    )
    workspace_root = service._get_session_workspace_root(user_id, session_id)
    chart_dir = workspace_root / "reports"
    chart_dir.mkdir(parents=True, exist_ok=True)
    chart_path = chart_dir / "chart.png"
    chart_path.write_bytes(b"png-bytes")

    session_manager.add_message(
        session_id,
        user_id,
        {
            "role": "assistant",
            "content": "请把这张图同步到远端。\n![趋势图](/workspace/reports/chart.png)",
            "timestamp": "2026-04-20T03:00:00+00:00",
        },
    )
    monkeypatch.setattr(
        service,
        "_format_for_weixin",
        lambda *_args, text, **_kwargs: (text, [text] if text else []),
    )

    preview = service.get_outbound_preview(user_id, session_id)

    assert preview.has_candidate is True
    assert preview.attachments
    assert preview.attachments[0].workspace_path == "/workspace/reports/chart.png"
    assert "/workspace/reports/chart.png" not in preview.formatted_text
    assert "趋势图" in preview.formatted_text

    async def _fake_send(
        _user_id: str,
        *,
        session_id: str,
        account_id: str,
        token: str,
        base_url: str,
        chat_id: str,
        message: str,
        attachments=None,
    ) -> None:
        assert session_id == "claw-session"
        assert account_id == "wx_account_a"
        assert token == "secret-token-a"
        assert chat_id == "wx-chat-alpha"
        assert "趋势图" in message
        assert attachments and attachments[0].workspace_path == "/workspace/reports/chart.png"

    monkeypatch.setattr(service, "_send_weixin_message", _fake_send)

    result = await service.dispatch_last_reply(user_id, session_id)

    assert result.dispatched is True


def test_claw_session_link_can_start_before_chat_id_is_known(tmp_path: Path) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_id = "claw-session"
    _create_session(session_manager, user_id=user_id, session_id=session_id)

    channel_id = _create_test_channel(
        service,
        user_id,
        platform="weixin",
        name="我的微信 A",
        account_id="wx_account_a",
        token="secret-token-a",
    )

    pending_binding = service.save_session_binding(
        user_id,
        session_id,
        SessionClawBindingRequest(
            connector_id=channel_id,
            chat_id=None,
        ),
    )
    assert pending_binding.connector_id == channel_id
    assert pending_binding.chat_id is None
    assert pending_binding.link_status == "stopped"

    running = service.start_session_link(user_id, session_id)
    assert running.link_status == "running"
    assert running.auto_sync_enabled is True
    assert running.chat_id is None


def test_claw_service_resolves_vendored_hermes_runtime_from_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _session_manager = _build_service(tmp_path)
    repo_root = tmp_path / "AIASys"
    runtime_root = repo_root / "apps" / "backend" / "app" / "vendors" / "hermes_agent"
    runtime_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(service, "_get_repo_root", lambda: repo_root)

    resolved = service._get_hermes_runtime_root()
    assert resolved == runtime_root


@pytest.mark.asyncio
async def test_claw_dispatch_last_reply_updates_digest_and_dedupes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_id = "claw-session"
    _create_session(session_manager, user_id=user_id, session_id=session_id)

    channel_id = _create_test_channel(
        service,
        user_id,
        platform="weixin",
        name="我的微信 A",
        account_id="wx_account_a",
        token="secret-token-a",
    )
    service.save_session_binding(
        user_id,
        session_id,
        SessionClawBindingRequest(
            connector_id=channel_id,
            chat_id="wx-chat-alpha",
        ),
    )
    service.start_session_link(user_id, session_id)
    session_manager.add_message(
        session_id,
        user_id,
        {
            "role": "assistant",
            "content": "请把这条消息回发到微信。",
            "timestamp": "2026-04-19T23:10:00+00:00",
        },
    )

    sent_payloads: list[tuple[str, str]] = []

    async def _fake_send(
        _user_id: str,
        *,
        session_id: str,
        account_id: str,
        token: str,
        base_url: str,
        chat_id: str,
        message: str,
        attachments=None,
    ) -> None:
        sent_payloads.append((chat_id, message))
        assert session_id == "claw-session"
        assert account_id == "wx_account_a"
        assert token == "secret-token-a"
        assert base_url
        assert attachments == []

    monkeypatch.setattr(service, "_send_weixin_message", _fake_send)
    monkeypatch.setattr(
        service,
        "_format_for_weixin",
        lambda *_args, text, **_kwargs: (text, [text]),
    )

    result = await service.dispatch_last_reply(user_id, session_id)
    assert result.dispatched is True
    assert sent_payloads == [("wx-chat-alpha", "请把这条消息回发到微信。")]
    assert result.binding.last_dispatched_digest

    duplicate = await service.dispatch_last_reply(user_id, session_id)
    assert duplicate.dispatched is False
    assert "无需重复发送" in (duplicate.reason or "")


@pytest.mark.asyncio
async def test_claw_dispatch_last_reply_supports_feishu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_id = "claw-session"
    _create_session(session_manager, user_id=user_id, session_id=session_id)

    channel_id = _create_test_channel(
        service,
        user_id,
        platform="feishu",
        name="我的飞书",
        app_id="cli_test_app",
        app_secret="feishu-app-secret",
        base_url="https://open.feishu.cn",
    )
    service.save_session_binding(
        user_id,
        session_id,
        SessionClawBindingRequest(
            connector_id=channel_id,
            chat_id="oc_chat_alpha",
        ),
    )
    service.start_session_link(user_id, session_id)
    session_manager.add_message(
        session_id,
        user_id,
        {
            "role": "assistant",
            "content": "请把这条消息发到飞书。",
            "timestamp": "2026-04-20T02:20:00+00:00",
        },
    )

    sent_payloads: list[tuple[str, str, str, str]] = []

    async def _fake_send_feishu_message(
        _user_id: str,
        *,
        session_id: str,
        app_id: str,
        app_secret: str,
        base_url: str,
        chat_id: str,
        message: str,
        attachments=None,
    ) -> None:
        sent_payloads.append((app_id, app_secret, base_url, chat_id))
        assert message == "请把这条消息发到飞书。"
        assert session_id == "claw-session"
        assert attachments == []

    monkeypatch.setattr(service, "_send_feishu_message", _fake_send_feishu_message)

    result = await service.dispatch_last_reply(user_id, session_id)

    assert result.dispatched is True
    assert sent_payloads == [
        ("cli_test_app", "feishu-app-secret", "https://open.feishu.cn", "oc_chat_alpha")
    ]


@pytest.mark.asyncio
async def test_weixin_qr_login_confirmed_creates_connector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _session_manager = _build_service(tmp_path)
    user_id = "claw-user"

    async def _fake_qr_api_get(
        _user_id: str,
        *,
        base_url: str,
        endpoint: str,
    ) -> dict[str, str]:
        assert _user_id == user_id
        if "get_bot_qrcode" in endpoint:
            assert base_url == "https://ilinkai.weixin.qq.com"
            return {
                "qrcode": "qr-token-1",
                "qrcode_img_content": "https://ilinkai.weixin.qq.com/qrcode/qr-token-1",
            }
        if "get_qrcode_status" in endpoint:
            return {
                "status": "confirmed",
                "ilink_bot_id": "wx_account_b",
                "bot_token": "secret-token-b",
                "baseurl": "https://redirect.ilink.example",
                "ilink_user_id": "wx-user-1",
            }
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(service, "_weixin_qr_api_get", _fake_qr_api_get)

    started = await service.start_weixin_qr_login(user_id)
    assert started.flow_id.startswith("wxqr_")
    assert started.status == "wait"
    assert started.qrcode == "qr-token-1"
    assert started.qrcode_url == "https://ilinkai.weixin.qq.com/qrcode/qr-token-1"

    polled = await service.poll_weixin_qr_login(user_id, started.flow_id)
    assert polled.status == "confirmed"
    assert polled.connector is not None
    assert polled.connector.account_id == "wx_account_b"
    assert polled.connector.has_token is True
    assert polled.connector.base_url == "https://redirect.ilink.example"

    connectors = service.list_connectors(user_id)
    assert len(connectors) == 1
    assert connectors[0].account_id == "wx_account_b"

    with pytest.raises(ValueError):
        await service.poll_weixin_qr_login(user_id, started.flow_id)


def test_expire_idle_bindings_stops_running_binding_after_72h(tmp_path: Path) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_id = "claw-session"
    _create_session(session_manager, user_id=user_id, session_id=session_id)

    channel_id = _create_test_channel(
        service,
        user_id,
        platform="weixin",
        name="我的微信 A",
        account_id="wx_account_a",
        token="secret-token-a",
    )
    service.save_session_binding(
        user_id,
        session_id,
        SessionClawBindingRequest(
            connector_id=channel_id,
            chat_id="wx-chat-alpha",
        ),
    )
    service.start_session_link(user_id, session_id)

    # 模拟 73 小时前的入站消息
    from datetime import datetime, timedelta, timezone

    old_time = (datetime.now(timezone.utc) - timedelta(hours=73)).isoformat()
    binding_path = tmp_path / user_id / session_id / ".aiasys" / "session" / "claw-binding.json"
    raw = json.loads(binding_path.read_text(encoding="utf-8"))
    raw["last_inbound_at"] = old_time
    binding_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")

    expired = service.expire_idle_bindings(user_id, idle_timeout_hours=72)
    assert expired == [session_id]

    binding = service.get_session_binding(user_id, session_id)
    assert binding.link_status == "stopped"


def test_expire_idle_bindings_keeps_recent_binding(tmp_path: Path) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_id = "claw-session"
    _create_session(session_manager, user_id=user_id, session_id=session_id)

    channel_id = _create_test_channel(
        service,
        user_id,
        platform="weixin",
        name="我的微信 A",
        account_id="wx_account_a",
        token="secret-token-a",
    )
    service.save_session_binding(
        user_id,
        session_id,
        SessionClawBindingRequest(
            connector_id=channel_id,
            chat_id="wx-chat-alpha",
        ),
    )
    service.start_session_link(user_id, session_id)

    # 模拟 1 小时前的入站消息
    from datetime import datetime, timedelta, timezone

    recent_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    binding_path = tmp_path / user_id / session_id / ".aiasys" / "session" / "claw-binding.json"
    raw = json.loads(binding_path.read_text(encoding="utf-8"))
    raw["last_inbound_at"] = recent_time
    binding_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")

    expired = service.expire_idle_bindings(user_id, idle_timeout_hours=72)
    assert expired == []

    binding = service.get_session_binding(user_id, session_id)
    assert binding.link_status == "running"
