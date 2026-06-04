from __future__ import annotations

from pathlib import Path

import pytest

from app.models.claw import SessionClawBindingRequest
from app.services.channel import ChannelEntry, ChannelConfig, get_channel_config
from app.services.claw import ClawService
from app.services.session import SessionManager


def _build_service(tmp_path: Path) -> tuple[ClawService, SessionManager]:
    session_manager = SessionManager(tmp_path)
    service = ClawService(tmp_path, session_manager=session_manager)
    return service, session_manager


def _create_session(session_manager: SessionManager, *, user_id: str, session_id: str) -> None:
    session_manager.create_session(session_id=session_id, user_id=user_id, title="频道测试会话")


def _save_channel(tmp_path: Path, user_id: str, entry: ChannelEntry) -> None:
    config = ChannelConfig(user_id, workspace_root=tmp_path)
    config.set_channel(entry)


def test_channel_platform_catalog_exposes_ready_and_future_platforms(tmp_path: Path) -> None:
    service, _session_manager = _build_service(tmp_path)

    platforms = service.list_platforms()
    by_platform = {item.platform: item for item in platforms}

    assert len(platforms) == 3
    assert platforms[0].platform == "weixin"
    assert by_platform["weixin"].support_status == "ready"
    assert by_platform["weixin"].runtime_enabled is True
    assert by_platform["feishu"].support_status == "ready"
    assert by_platform["feishu"].runtime_enabled is True
    assert by_platform["dingtalk"].support_status == "ready"
    assert by_platform["dingtalk"].runtime_enabled is True


def test_channel_yaml_can_drive_session_binding_and_runtime_secret(tmp_path: Path) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "channel-user"
    session_id = "channel-session"
    channel_id = "weixin_test"
    _create_session(session_manager, user_id=user_id, session_id=session_id)
    _save_channel(
        tmp_path,
        user_id,
        ChannelEntry(
            channel_id=channel_id,
            platform="weixin",
            enabled=True,
            name="测试微信",
            account_id="wx_account_channel",
            token="channel-token",
            base_url="https://ilinkai.weixin.qq.com",
        ),
    )

    binding = service.save_session_binding(
        user_id,
        session_id,
        SessionClawBindingRequest(
            channel_id=channel_id,
            chat_id="wx-chat-alpha",
            chat_label="客户群",
        ),
    )

    assert binding.channel_id == channel_id
    assert binding.connector_id == channel_id
    assert binding.connector is not None
    assert binding.connector.channel_id == channel_id
    assert binding.connector.name == "测试微信"

    running = service.start_session_link(user_id, session_id)
    assert running.link_status == "running"
    assert running.auto_sync_enabled is True

    secret = service.resolve_connector_secret(user_id, channel_id)
    assert secret == {
        "connector_id": channel_id,
        "channel_id": channel_id,
        "platform": "weixin",
        "account_id": "wx_account_channel",
        "token": "channel-token",
        "base_url": "https://ilinkai.weixin.qq.com",
    }

    running_bindings = service.list_running_bindings(user_id)
    assert [item.channel_id for item in running_bindings] == [channel_id]


def test_channel_config_cache_reloads_external_yaml_edits(tmp_path: Path) -> None:
    user_id = "channel-user"
    config = get_channel_config(user_id, workspace_root=tmp_path)
    config.set_channel(
        ChannelEntry(
            channel_id="weixin_original",
            platform="weixin",
            enabled=True,
            name="原频道",
            account_id="wx_original",
            token="original-token",
        )
    )

    config_path = tmp_path / user_id / "global_workspace" / ".aiasys" / "channels.toml"
    config_path.write_text(
        '''[channels.weixin_external]
platform = "weixin"
enabled = true
name = "外部编辑频道"
account_id = "wx_external"
token = "external-token"
''',
        encoding="utf-8",
    )

    reloaded = get_channel_config(user_id, workspace_root=tmp_path)

    assert reloaded.get_channel("weixin_original") is None
    external = reloaded.get_channel("weixin_external")
    assert external is not None
    assert external.name == "外部编辑频道"
    assert external.resolve_token() == "external-token"


@pytest.mark.asyncio
async def test_channel_yaml_credentials_are_used_for_dispatch(tmp_path: Path, monkeypatch) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "channel-user"
    session_id = "channel-session"
    channel_id = "feishu_test"
    _create_session(session_manager, user_id=user_id, session_id=session_id)
    _save_channel(
        tmp_path,
        user_id,
        ChannelEntry(
            channel_id=channel_id,
            platform="feishu",
            enabled=True,
            name="测试飞书",
            app_id="cli_channel",
            app_secret="channel-secret",
            base_url="https://open.feishu.cn",
        ),
    )
    service.save_session_binding(
        user_id,
        session_id,
        SessionClawBindingRequest(
            channel_id=channel_id,
            chat_id="oc_chat_alpha",
        ),
    )
    service.start_session_link(user_id, session_id)
    session_manager.add_message(
        session_id,
        user_id,
        {
            "role": "assistant",
            "content": "频道消息出站。",
            "timestamp": "2026-05-21T12:00:00+00:00",
        },
    )

    sent: list[tuple[str, str, str, str]] = []

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
        sent.append((app_id, app_secret, base_url, chat_id))
        assert session_id == "channel-session"
        assert message == "频道消息出站。"
        assert attachments == []

    monkeypatch.setattr(service, "_send_feishu_message", _fake_send_feishu_message)

    result = await service.dispatch_last_reply(user_id, session_id)

    assert result.dispatched is True
    assert result.binding.channel_id == channel_id
    assert result.preview.channel_id == channel_id
    assert sent == [("cli_channel", "channel-secret", "https://open.feishu.cn", "oc_chat_alpha")]


@pytest.mark.asyncio
async def test_weixin_qr_login_confirmed_creates_channel(tmp_path: Path, monkeypatch) -> None:
    service, _session_manager = _build_service(tmp_path)
    user_id = "channel-user"

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
                "ilink_bot_id": "wx_account_channel",
                "bot_token": "channel-token",
                "baseurl": "https://redirect.ilink.example",
            }
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(service, "_weixin_qr_api_get", _fake_qr_api_get)

    started = await service.start_weixin_qr_login(user_id)
    polled = await service.poll_weixin_qr_login(user_id, started.flow_id)

    assert polled.status == "confirmed"
    assert polled.connector is not None
    assert polled.connector.channel_id
    assert polled.connector.connector_id == polled.connector.channel_id
    assert polled.connector.account_id == "wx_account_channel"

    channels = ChannelConfig(user_id, workspace_root=tmp_path).list_channels()
    assert len(channels) == 1
    assert channels[0].platform == "weixin"
    assert channels[0].enabled is True
    assert channels[0].account_id == "wx_account_channel"
    assert channels[0].resolve_token() == "channel-token"
