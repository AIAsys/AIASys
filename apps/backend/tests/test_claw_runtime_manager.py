from __future__ import annotations

import asyncio
import contextlib
import sys
from collections import defaultdict
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.claw import SessionClawBindingRequest
from app.services.channel import ChannelEntry, get_channel_config
from app.services.claw_runtime import (
    ClawFeishuRuntime,
    ClawPendingBinding,
    ClawRuntimeBinding,
    ClawRuntimeManager,
    ClawWeixinRuntime,
)
from app.services.claw import ClawService
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


def _install_fake_feishu_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_lark_oapi_module = ModuleType("lark_oapi")
    fake_lark_ws_module = ModuleType("lark_oapi.ws")
    fake_lark_ws_client_module = ModuleType("lark_oapi.ws.client")
    fake_lark_core_module = ModuleType("lark_oapi.core")
    fake_lark_enum_module = ModuleType("lark_oapi.core.enum")

    class _FakeClient:
        def __init__(self, **_kwargs) -> None:
            self._conn = object()

        async def _connect(self) -> None:
            return None

        async def _disconnect(self) -> None:
            self._conn = None

        async def _ping_loop(self) -> None:
            await asyncio.sleep(0)

    fake_lark_ws_client_module.Client = _FakeClient
    fake_lark_ws_client_module.loop = None
    fake_lark_enum_module.LogLevel = SimpleNamespace(INFO="INFO")

    monkeypatch.setitem(sys.modules, "lark_oapi", fake_lark_oapi_module)
    monkeypatch.setitem(sys.modules, "lark_oapi.ws", fake_lark_ws_module)
    monkeypatch.setitem(sys.modules, "lark_oapi.ws.client", fake_lark_ws_client_module)
    monkeypatch.setitem(sys.modules, "lark_oapi.core", fake_lark_core_module)
    monkeypatch.setitem(sys.modules, "lark_oapi.core.enum", fake_lark_enum_module)


def _install_fake_feishu_gateway(
    monkeypatch: pytest.MonkeyPatch,
    *,
    text: str,
) -> None:
    fake_gateway_module = ModuleType("gateway")
    fake_platforms_module = ModuleType("gateway.platforms")
    fake_feishu_module = ModuleType("gateway.platforms.feishu")
    fake_feishu_module.normalize_feishu_message = lambda **_kwargs: SimpleNamespace(text=text)

    monkeypatch.setitem(sys.modules, "gateway", fake_gateway_module)
    monkeypatch.setitem(sys.modules, "gateway.platforms", fake_platforms_module)
    monkeypatch.setitem(sys.modules, "gateway.platforms.feishu", fake_feishu_module)


def test_claw_running_bindings_can_be_grouped_by_connector(tmp_path: Path) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"

    channel_a = _create_test_channel(
        service,
        user_id,
        platform="weixin",
        name="我的微信 A",
        account_id="wx_account_a",
        token="secret-token-a",
    )
    channel_b = _create_test_channel(
        service,
        user_id,
        platform="weixin",
        name="我的微信 B",
        account_id="wx_account_b",
        token="secret-token-b",
    )

    session_a1 = "claw-session-a1"
    session_a2 = "claw-session-a2"
    session_b1 = "claw-session-b1"
    session_idle = "claw-session-idle"
    for session_id in (session_a1, session_a2, session_b1, session_idle):
        _create_session(session_manager, user_id=user_id, session_id=session_id)

    for session_id in (session_a1, session_a2):
        service.save_session_binding(
            user_id,
            session_id,
            SessionClawBindingRequest(
                connector_id=channel_a,
                chat_id=f"wx-chat-{session_id}",
            ),
        )
        service.start_session_link(user_id, session_id)

    service.save_session_binding(
        user_id,
        session_b1,
        SessionClawBindingRequest(
            connector_id=channel_b,
            chat_id=f"wx-chat-{session_b1}",
        ),
    )
    service.start_session_link(user_id, session_b1)

    service.save_session_binding(
        user_id,
        session_idle,
        SessionClawBindingRequest(
            connector_id=channel_a,
            chat_id="wx-chat-idle",
        ),
    )

    grouped: dict[str, list[str]] = defaultdict(list)
    for binding in service.list_running_bindings(user_id):
        grouped[binding.connector_id or ""].append(binding.session_id)

    assert sorted(grouped[channel_a]) == [session_a1, session_a2]
    assert grouped[channel_b] == [session_b1]
    assert session_idle not in grouped[channel_a]


def test_claw_runtime_refresh_sees_start_and_stop_seams(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_id = "claw-global"
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

    events: list[tuple[str, tuple[str, ...]]] = []

    class _RecordingRuntimeManager:
        def schedule_refresh_for_user(self, refreshed_user_id: str) -> None:
            running_connector_ids = tuple(
                sorted(
                    {
                        binding.connector_id
                        for binding in service.list_running_bindings(refreshed_user_id)
                        if binding.connector_id
                    }
                )
            )
            if running_connector_ids:
                events.append(("start", running_connector_ids))
            else:
                events.append(("stop", (refreshed_user_id,)))

    fake_runtime_module = ModuleType("app.services.claw_runtime")
    fake_runtime_module.get_claw_runtime_manager = lambda: _RecordingRuntimeManager()
    monkeypatch.setitem(sys.modules, "app.services.claw_runtime", fake_runtime_module)

    service.start_session_link(user_id, session_id)
    service.stop_session_link(user_id, session_id)

    assert events == [
        ("start", (channel_id,)),
        ("stop", (user_id,)),
    ]


@pytest.mark.asyncio
async def test_claw_weixin_runtime_routes_inbound_text_to_bound_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_id = "claw-global"
    _create_session(session_manager, user_id=user_id, session_id=session_id)

    channel_id = _create_test_channel(
        service,
        user_id,
        platform="weixin",
        name="我的微信 A",
        account_id="wx_account_a",
        token="secret-token-a",
    )

    class _FakeTokenStore:
        def __init__(self, _home: str) -> None:
            self.values: dict[tuple[str, str], str] = {}

        def restore(self, _account_id: str) -> None:
            return None

        def set(self, account_id: str, peer_id: str, token: str) -> None:
            self.values[(account_id, peer_id)] = token

    class _FakeDedup:
        def __init__(self, ttl_seconds: int) -> None:
            self.ttl_seconds = ttl_seconds
            self._seen: set[str] = set()

        def is_duplicate(self, message_id: str) -> bool:
            if message_id in self._seen:
                return True
            self._seen.add(message_id)
            return False

    fake_gateway_module = ModuleType("gateway")
    fake_platforms_module = ModuleType("gateway.platforms")
    fake_weixin_module = ModuleType("gateway.platforms.weixin")
    fake_weixin_module.ContextTokenStore = _FakeTokenStore
    fake_weixin_module.MessageDeduplicator = _FakeDedup
    fake_weixin_module.MESSAGE_DEDUP_TTL_SECONDS = 300
    fake_weixin_module.TYPING_START = 1
    fake_weixin_module.TYPING_STOP = 2
    fake_weixin_module.AIOHTTP_AVAILABLE = False
    fake_weixin_module._guess_chat_type = lambda *_args, **_kwargs: ("dm", "wx-chat-alpha")
    fake_weixin_module._extract_text = lambda *_args, **_kwargs: "微信里发来的问题"
    fake_weixin_module._get_config = AsyncMock(return_value={})
    fake_weixin_module._send_typing = AsyncMock()
    monkeypatch.setitem(sys.modules, "gateway", fake_gateway_module)
    monkeypatch.setitem(sys.modules, "gateway.platforms", fake_platforms_module)
    monkeypatch.setitem(sys.modules, "gateway.platforms.weixin", fake_weixin_module)
    monkeypatch.setattr(
        service,
        "_hermes_import_scope",
        lambda _user_id: contextlib.nullcontext(),
    )

    runtime = ClawWeixinRuntime(
        user_id=user_id,
        connector_id=channel_id,
        claw_service=service,
        account_id="wx_account_a",
        token="secret-token-a",
        base_url="https://ilinkai.weixin.qq.com",
        bindings={
            "wx-chat-alpha": ClawRuntimeBinding(
                session_id=session_id,
                chat_id="wx-chat-alpha",
                chat_label="客户群",
                updated_at="2026-04-20T01:30:00+00:00",
            )
        },
    )

    execute_mock = AsyncMock(return_value="done")
    monkeypatch.setattr("app.services.claw_runtime.agent_service.execute", execute_mock)

    await runtime._process_inbound_message(
        {
            "from_user_id": "wx-chat-alpha",
            "message_id": "msg-1",
            "context_token": "ctx-1",
            "item_list": [{"type": 1}],
        }
    )

    execute_mock.assert_awaited_once_with(
        prompt="微信里发来的问题\n\n（来自微信）",
        user_id=user_id,
        session_id="claw-global",
        suppress_claw_outbound_sync=True,
    )


@pytest.mark.asyncio
async def test_claw_weixin_runtime_claims_first_inbound_chat_for_pending_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_id = "claw-global"
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
        SessionClawBindingRequest(connector_id=channel_id),
    )
    service.start_session_link(user_id, session_id)

    class _FakeTokenStore:
        def __init__(self, _home: str) -> None:
            self.values: dict[tuple[str, str], str] = {}

        def restore(self, _account_id: str) -> None:
            return None

        def set(self, account_id: str, peer_id: str, token: str) -> None:
            self.values[(account_id, peer_id)] = token

    class _FakeDedup:
        def __init__(self, ttl_seconds: int) -> None:
            self.ttl_seconds = ttl_seconds
            self._seen: set[str] = set()

        def is_duplicate(self, message_id: str) -> bool:
            if message_id in self._seen:
                return True
            self._seen.add(message_id)
            return False

    fake_gateway_module = ModuleType("gateway")
    fake_platforms_module = ModuleType("gateway.platforms")
    fake_weixin_module = ModuleType("gateway.platforms.weixin")
    fake_weixin_module.ContextTokenStore = _FakeTokenStore
    fake_weixin_module.MessageDeduplicator = _FakeDedup
    fake_weixin_module.MESSAGE_DEDUP_TTL_SECONDS = 300
    fake_weixin_module.TYPING_START = 1
    fake_weixin_module.TYPING_STOP = 2
    fake_weixin_module.AIOHTTP_AVAILABLE = False
    fake_weixin_module._guess_chat_type = lambda *_args, **_kwargs: ("dm", "wx-chat-alpha")
    fake_weixin_module._extract_text = lambda *_args, **_kwargs: "你好"
    fake_weixin_module._get_config = AsyncMock(return_value={})
    fake_weixin_module._send_typing = AsyncMock()
    monkeypatch.setitem(sys.modules, "gateway", fake_gateway_module)
    monkeypatch.setitem(sys.modules, "gateway.platforms", fake_platforms_module)
    monkeypatch.setitem(sys.modules, "gateway.platforms.weixin", fake_weixin_module)
    monkeypatch.setattr(
        service,
        "_hermes_import_scope",
        lambda _user_id: contextlib.nullcontext(),
    )

    runtime = ClawWeixinRuntime(
        user_id=user_id,
        connector_id=channel_id,
        claw_service=service,
        account_id="wx_account_a",
        token="secret-token-a",
        base_url="https://ilinkai.weixin.qq.com",
        bindings={},
        pending_bindings=(
            ClawPendingBinding(
                session_id=session_id,
                updated_at="2026-04-20T01:30:00+00:00",
            ),
        ),
    )

    execute_mock = AsyncMock(return_value="done")
    monkeypatch.setattr("app.services.claw_runtime.agent_service.execute", execute_mock)

    await runtime._process_inbound_message(
        {
            "from_user_id": "wx-chat-alpha",
            "message_id": "msg-claim-1",
            "context_token": "ctx-claim-1",
            "item_list": [{"type": 1}],
        }
    )

    claimed = service.get_session_binding(user_id, session_id)
    assert claimed.chat_id == "wx-chat-alpha"
    assert claimed.link_status == "running"
    execute_mock.assert_awaited_once_with(
        prompt="你好\n\n（来自微信）",
        user_id=user_id,
        session_id="claw-global",
        suppress_claw_outbound_sync=True,
    )


@pytest.mark.asyncio
async def test_claw_weixin_runtime_sends_typing_indicator_around_execute(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_id = "claw-global"
    _create_session(session_manager, user_id=user_id, session_id=session_id)

    channel_id = _create_test_channel(
        service,
        user_id,
        platform="weixin",
        name="我的微信 A",
        account_id="wx_account_a",
        token="secret-token-a",
    )

    class _FakeTokenStore:
        def __init__(self, _home: str) -> None:
            self.values: dict[tuple[str, str], str] = {}

        def restore(self, _account_id: str) -> None:
            return None

        def set(self, account_id: str, peer_id: str, token: str) -> None:
            self.values[(account_id, peer_id)] = token

    class _FakeDedup:
        def __init__(self, ttl_seconds: int) -> None:
            self.ttl_seconds = ttl_seconds
            self._seen: set[str] = set()

        def is_duplicate(self, message_id: str) -> bool:
            if message_id in self._seen:
                return True
            self._seen.add(message_id)
            return False

    typing_statuses: list[int] = []

    async def _fake_send_typing(*_args, status: int, **_kwargs) -> None:
        typing_statuses.append(status)

    async def _fake_execute(**_kwargs):
        await asyncio.sleep(0)
        return "done"

    fake_gateway_module = ModuleType("gateway")
    fake_platforms_module = ModuleType("gateway.platforms")
    fake_weixin_module = ModuleType("gateway.platforms.weixin")
    fake_weixin_module.ContextTokenStore = _FakeTokenStore
    fake_weixin_module.MessageDeduplicator = _FakeDedup
    fake_weixin_module.MESSAGE_DEDUP_TTL_SECONDS = 300
    fake_weixin_module.TYPING_START = 1
    fake_weixin_module.TYPING_STOP = 2
    fake_weixin_module.AIOHTTP_AVAILABLE = False
    fake_weixin_module._guess_chat_type = lambda *_args, **_kwargs: ("dm", "wx-chat-alpha")
    fake_weixin_module._extract_text = lambda *_args, **_kwargs: "你好"
    fake_weixin_module._get_config = AsyncMock(return_value={"typing_ticket": "ticket-1"})
    fake_weixin_module._send_typing = _fake_send_typing
    monkeypatch.setitem(sys.modules, "gateway", fake_gateway_module)
    monkeypatch.setitem(sys.modules, "gateway.platforms", fake_platforms_module)
    monkeypatch.setitem(sys.modules, "gateway.platforms.weixin", fake_weixin_module)
    monkeypatch.setattr(
        service,
        "_hermes_import_scope",
        lambda _user_id: contextlib.nullcontext(),
    )

    runtime = ClawWeixinRuntime(
        user_id=user_id,
        connector_id=channel_id,
        claw_service=service,
        account_id="wx_account_a",
        token="secret-token-a",
        base_url="https://ilinkai.weixin.qq.com",
        bindings={
            "wx-chat-alpha": ClawRuntimeBinding(
                session_id=session_id,
                chat_id="wx-chat-alpha",
                chat_label="客户群",
                updated_at="2026-04-20T01:30:00+00:00",
            )
        },
    )
    runtime._session = object()

    monkeypatch.setattr("app.services.claw_runtime.agent_service.execute", _fake_execute)

    await runtime._process_inbound_message(
        {
            "from_user_id": "wx-chat-alpha",
            "message_id": "msg-typing-1",
            "context_token": "ctx-typing-1",
            "item_list": [{"type": 1}],
        }
    )

    assert typing_statuses[0] == 1
    assert typing_statuses[-1] == 2


@pytest.mark.asyncio
async def test_claw_weixin_runtime_imports_inbound_attachment_into_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_id = "claw-global"
    _create_session(session_manager, user_id=user_id, session_id=session_id)

    channel_id = _create_test_channel(
        service,
        user_id,
        platform="weixin",
        name="我的微信 A",
        account_id="wx_account_a",
        token="secret-token-a",
    )

    attachment_source = tmp_path / "weixin-source.pdf"
    attachment_source.write_bytes(b"%PDF-1.4 fake")

    class _FakeTokenStore:
        def __init__(self, _home: str) -> None:
            self.values: dict[tuple[str, str], str] = {}

        def restore(self, _account_id: str) -> None:
            return None

        def set(self, account_id: str, peer_id: str, token: str) -> None:
            self.values[(account_id, peer_id)] = token

    class _FakeDedup:
        def __init__(self, ttl_seconds: int) -> None:
            self.ttl_seconds = ttl_seconds
            self._seen: set[str] = set()

        def is_duplicate(self, message_id: str) -> bool:
            if message_id in self._seen:
                return True
            self._seen.add(message_id)
            return False

    fake_gateway_module = ModuleType("gateway")
    fake_platforms_module = ModuleType("gateway.platforms")
    fake_config_module = ModuleType("gateway.config")
    fake_weixin_module = ModuleType("gateway.platforms.weixin")
    fake_config_module.PlatformConfig = lambda **kwargs: SimpleNamespace(**kwargs)
    fake_weixin_module.ContextTokenStore = _FakeTokenStore
    fake_weixin_module.MessageDeduplicator = _FakeDedup
    fake_weixin_module.MESSAGE_DEDUP_TTL_SECONDS = 300
    fake_weixin_module.TYPING_START = 1
    fake_weixin_module.TYPING_STOP = 2
    fake_weixin_module.AIOHTTP_AVAILABLE = False
    fake_weixin_module.ITEM_IMAGE = 2
    fake_weixin_module.ITEM_VIDEO = 3
    fake_weixin_module.ITEM_FILE = 4
    fake_weixin_module.ITEM_VOICE = 5
    fake_weixin_module.WEIXIN_CDN_BASE_URL = "https://cdn.weixin.example"
    fake_weixin_module._guess_chat_type = lambda *_args, **_kwargs: ("dm", "wx-chat-alpha")
    fake_weixin_module._extract_text = lambda *_args, **_kwargs: ""
    fake_weixin_module._get_config = AsyncMock(return_value={})
    fake_weixin_module._send_typing = AsyncMock()

    class _FakeWeixinAdapter:
        def __init__(self, _config) -> None:
            return None

        async def _collect_media(self, item, media_paths, media_types) -> None:
            assert item["type"] == 4
            media_paths.append(str(attachment_source))
            media_types.append("application/pdf")

    fake_weixin_module.WeixinAdapter = _FakeWeixinAdapter

    monkeypatch.setitem(sys.modules, "gateway", fake_gateway_module)
    monkeypatch.setitem(sys.modules, "gateway.platforms", fake_platforms_module)
    monkeypatch.setitem(sys.modules, "gateway.config", fake_config_module)
    monkeypatch.setitem(sys.modules, "gateway.platforms.weixin", fake_weixin_module)
    monkeypatch.setattr(
        service,
        "_hermes_import_scope",
        lambda _user_id: contextlib.nullcontext(),
    )

    runtime = ClawWeixinRuntime(
        user_id=user_id,
        connector_id=channel_id,
        claw_service=service,
        account_id="wx_account_a",
        token="secret-token-a",
        base_url="https://ilinkai.weixin.qq.com",
        bindings={
            "wx-chat-alpha": ClawRuntimeBinding(
                session_id=session_id,
                chat_id="wx-chat-alpha",
                chat_label="客户群",
                updated_at="2026-04-20T01:30:00+00:00",
            )
        },
    )
    runtime._session = object()

    execute_mock = AsyncMock(return_value="done")
    monkeypatch.setattr("app.services.claw_runtime.agent_service.execute", execute_mock)

    await runtime._process_inbound_message(
        {
            "from_user_id": "wx-chat-alpha",
            "message_id": "msg-file-1",
            "context_token": "ctx-file-1",
            "item_list": [
                {
                    "type": 4,
                    "file_item": {"file_name": "spec.pdf"},
                }
            ],
        }
    )

    execute_mock.assert_awaited_once()
    execute_call = execute_mock.await_args.kwargs
    assert execute_call["prompt"].endswith("\n\n（来自微信）")
    assert "source_platform" not in execute_call
    assert execute_call["suppress_claw_outbound_sync"] is True
    assert execute_call["attachments"]
    imported_relative = execute_call["attachments"][0]
    imported_path = service._get_session_workspace_root(user_id, session_id) / imported_relative
    assert imported_path.exists()
    assert imported_path.read_bytes() == b"%PDF-1.4 fake"
    assert "spec.pdf" in execute_call["prompt"]

    binding = service.get_session_binding(user_id, session_id)
    assert binding.last_inbound_attachments
    assert binding.last_inbound_attachments[0].display_name == "spec.pdf"


@pytest.mark.asyncio
async def test_claw_feishu_runtime_routes_inbound_text_to_bound_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_id = "claw-global"
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

    _install_fake_feishu_sdk(monkeypatch)
    _install_fake_feishu_gateway(monkeypatch, text="飞书里发来的问题")
    monkeypatch.setattr(
        service,
        "_hermes_import_scope",
        lambda _user_id: contextlib.nullcontext(),
    )

    runtime = ClawFeishuRuntime(
        user_id=user_id,
        connector_id=channel_id,
        claw_service=service,
        account_id="cli_test_app",
        token="feishu-app-secret",
        base_url="https://open.feishu.cn",
        bindings={
            "oc_chat_alpha": ClawRuntimeBinding(
                session_id=session_id,
                chat_id="oc_chat_alpha",
                chat_label="飞书会话",
                updated_at="2026-04-20T02:40:00+00:00",
            )
        },
    )

    execute_mock = AsyncMock(return_value="done")
    monkeypatch.setattr("app.services.claw_runtime.agent_service.execute", execute_mock)

    await runtime._process_event_payload(
        {
            "event": {
                "sender": {
                    "sender_type": "user",
                    "sender_id": {"open_id": "ou_sender_alpha"},
                },
                "message": {
                    "message_id": "om_msg_alpha",
                    "message_type": "text",
                    "content": {"text": "你好"},
                    "chat_id": "oc_chat_alpha",
                    "chat_type": "p2p",
                },
            }
        }
    )

    execute_mock.assert_awaited_once_with(
        prompt="飞书里发来的问题\n\n（来自飞书）",
        user_id=user_id,
        session_id=session_id,
        suppress_claw_outbound_sync=True,
    )


@pytest.mark.asyncio
async def test_claw_feishu_runtime_claims_first_inbound_chat_for_pending_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_id = "claw-global"
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
        SessionClawBindingRequest(connector_id=channel_id),
    )
    service.start_session_link(user_id, session_id)

    _install_fake_feishu_sdk(monkeypatch)
    _install_fake_feishu_gateway(monkeypatch, text="飞书第一次打招呼")
    monkeypatch.setattr(
        service,
        "_hermes_import_scope",
        lambda _user_id: contextlib.nullcontext(),
    )

    runtime = ClawFeishuRuntime(
        user_id=user_id,
        connector_id=channel_id,
        claw_service=service,
        account_id="cli_test_app",
        token="feishu-app-secret",
        base_url="https://open.feishu.cn",
        bindings={},
        pending_bindings=(
            ClawPendingBinding(
                session_id=session_id,
                updated_at="2026-04-20T02:50:00+00:00",
            ),
        ),
    )

    execute_mock = AsyncMock(return_value="done")
    monkeypatch.setattr("app.services.claw_runtime.agent_service.execute", execute_mock)

    await runtime._process_event_payload(
        {
            "event": {
                "sender": {
                    "sender_type": "user",
                    "sender_id": {"open_id": "ou_sender_alpha"},
                },
                "message": {
                    "message_id": "om_msg_claim_alpha",
                    "message_type": "text",
                    "content": {"text": "你好"},
                    "chat_id": "oc_chat_first",
                    "chat_type": "p2p",
                },
            }
        }
    )

    claimed = service.get_session_binding(user_id, session_id)
    assert claimed.chat_id == "oc_chat_first"
    assert claimed.link_status == "running"
    execute_mock.assert_awaited_once_with(
        prompt="飞书第一次打招呼\n\n（来自飞书）",
        user_id=user_id,
        session_id=session_id,
        suppress_claw_outbound_sync=True,
    )


@pytest.mark.asyncio
async def test_claw_feishu_runtime_imports_inbound_attachment_into_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session_manager = _build_service(tmp_path)
    user_id = "claw-user"
    session_id = "claw-global"
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

    attachment_source = tmp_path / "feishu-source.txt"
    attachment_source.write_text("hello from feishu", encoding="utf-8")

    _install_fake_feishu_sdk(monkeypatch)
    fake_gateway_module = ModuleType("gateway")
    fake_platforms_module = ModuleType("gateway.platforms")
    fake_config_module = ModuleType("gateway.config")
    fake_feishu_module = ModuleType("gateway.platforms.feishu")
    fake_config_module.PlatformConfig = lambda **kwargs: SimpleNamespace(**kwargs)

    class _FakeFeishuAdapter:
        def __init__(self, _config) -> None:
            self._client = None

        def _build_lark_client(self, _domain):
            return object()

        async def _download_feishu_message_resources(self, *, message_id: str, normalized):
            assert message_id == "om_msg_attachment"
            assert normalized.media_refs
            return [str(attachment_source)], ["text/plain"]

        async def _maybe_extract_text_document(self, cached_path: str, media_type: str) -> str:
            assert cached_path == str(attachment_source)
            assert media_type == "text/plain"
            return "[Content of inbound.txt]:\nhello from feishu"

    fake_feishu_module.normalize_feishu_message = lambda **_kwargs: SimpleNamespace(
        text_content="",
        image_keys=[],
        media_refs=[
            SimpleNamespace(
                file_key="file-key-1",
                file_name="inbound.txt",
                resource_type="file",
            )
        ],
        preferred_message_type="document",
    )
    fake_feishu_module.FeishuAdapter = _FakeFeishuAdapter
    fake_feishu_module.FEISHU_DOMAIN = object()
    fake_feishu_module.LARK_DOMAIN = object()

    monkeypatch.setitem(sys.modules, "gateway", fake_gateway_module)
    monkeypatch.setitem(sys.modules, "gateway.platforms", fake_platforms_module)
    monkeypatch.setitem(sys.modules, "gateway.config", fake_config_module)
    monkeypatch.setitem(sys.modules, "gateway.platforms.feishu", fake_feishu_module)
    monkeypatch.setattr(
        service,
        "_hermes_import_scope",
        lambda _user_id: contextlib.nullcontext(),
    )

    runtime = ClawFeishuRuntime(
        user_id=user_id,
        connector_id=channel_id,
        claw_service=service,
        account_id="cli_test_app",
        token="feishu-app-secret",
        base_url="https://open.feishu.cn",
        bindings={
            "oc_chat_alpha": ClawRuntimeBinding(
                session_id=session_id,
                chat_id="oc_chat_alpha",
                chat_label="飞书会话",
                updated_at="2026-04-20T02:40:00+00:00",
            )
        },
    )

    execute_mock = AsyncMock(return_value="done")
    monkeypatch.setattr("app.services.claw_runtime.agent_service.execute", execute_mock)

    await runtime._process_event_payload(
        {
            "event": {
                "sender": {
                    "sender_type": "user",
                    "sender_id": {"open_id": "ou_sender_alpha"},
                },
                "message": {
                    "message_id": "om_msg_attachment",
                    "message_type": "file",
                    "content": {"file_key": "file-key-1", "file_name": "inbound.txt"},
                    "chat_id": "oc_chat_alpha",
                    "chat_type": "p2p",
                },
            }
        }
    )

    execute_mock.assert_awaited_once()
    execute_call = execute_mock.await_args.kwargs
    assert execute_call["user_id"] == user_id
    assert execute_call["session_id"] == session_id
    assert execute_call["prompt"].endswith("\n\n（来自飞书）")
    assert "source_platform" not in execute_call
    assert execute_call["suppress_claw_outbound_sync"] is True
    assert execute_call["attachments"]
    imported_relative = execute_call["attachments"][0]
    imported_path = service._get_session_workspace_root(user_id, session_id) / imported_relative
    assert imported_path.exists()
    assert imported_path.read_text(encoding="utf-8") == "hello from feishu"
    assert "hello from feishu" in execute_call["prompt"]
    assert "inbound.txt" in execute_call["prompt"]

    binding = service.get_session_binding(user_id, session_id)
    assert binding.last_inbound_attachments
    assert binding.last_inbound_attachments[0].display_name == "inbound.txt"
    assert binding.last_inbound_attachments[0].workspace_path.startswith(
        "/workspace/claw-inbox/feishu/"
    )


@pytest.mark.asyncio
async def test_claw_runtime_manager_serializes_session_outbound_dispatches() -> None:
    manager = ClawRuntimeManager()
    user_id = "claw-user"
    session_id = "claw-global"
    first_release = asyncio.Event()
    second_started = asyncio.Event()
    second_release = asyncio.Event()
    running = 0
    max_running = 0
    dispatch_calls: list[int] = []

    async def _fake_dispatch(_user_id: str, _session_id: str) -> None:
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        dispatch_calls.append(len(dispatch_calls) + 1)
        if len(dispatch_calls) == 1:
            await first_release.wait()
        else:
            second_started.set()
            await second_release.wait()
        running -= 1

    manager._dispatch_session_outbound = _fake_dispatch  # type: ignore[method-assign]

    manager.schedule_session_outbound(user_id, session_id)
    await asyncio.sleep(0)
    assert dispatch_calls == [1]

    manager.schedule_session_outbound(user_id, session_id)
    await asyncio.sleep(0)
    assert dispatch_calls == [1]
    assert max_running == 1

    first_release.set()
    await asyncio.wait_for(second_started.wait(), timeout=1)
    assert dispatch_calls == [1, 2]
    assert max_running == 1

    second_release.set()
    while manager._outbound_tasks:
        await asyncio.sleep(0)

    assert manager._pending_outbound_sessions == set()
