"""
Claw 常驻 runtime 管理
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.agent import agent_service
from app.services.claw import ClawService

logger = logging.getLogger(__name__)

_TYPING_TICKET_TTL_SECONDS = 600


@dataclass(frozen=True, slots=True)
class ClawRuntimeBinding:
    session_id: str
    chat_id: str
    chat_label: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class ClawPendingBinding:
    session_id: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ClawRuntimeSnapshot:
    connector_id: str
    active: bool
    bound_session_ids: tuple[str, ...]
    bound_chat_ids: tuple[str, ...]
    last_inbound_at: str | None
    last_outbound_at: str | None
    last_error: str | None


class ClawWeixinRuntime:
    """单个微信 connector 的常驻轮询 runtime。"""

    def __init__(
        self,
        *,
        user_id: str,
        connector_id: str,
        claw_service: ClawService,
        account_id: str,
        token: str,
        base_url: str,
        bindings: dict[str, ClawRuntimeBinding],
        pending_bindings: tuple[ClawPendingBinding, ...] = (),
    ) -> None:
        self.user_id = user_id
        self.connector_id = connector_id
        self._claw_service = claw_service
        self._account_id = account_id
        self._token = token
        self._base_url = base_url
        self._bindings_by_chat_id = dict(bindings)
        self._pending_bindings = {binding.session_id: binding for binding in pending_bindings}
        self._running = False
        self._poll_task: asyncio.Task[None] | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._session: Any = None
        self._last_inbound_at: str | None = None
        self._last_outbound_at: str | None = None
        self._last_error: str | None = None

        with self._claw_service._hermes_import_scope(user_id):
            import importlib

            self._weixin_module = importlib.import_module("gateway.platforms.weixin")
            self._aiohttp = getattr(self._weixin_module, "aiohttp", None)

        self._hermes_home = str(self._claw_service._get_user_hermes_home(user_id))
        self._token_store = self._weixin_module.ContextTokenStore(self._hermes_home)
        self._dedup = self._weixin_module.MessageDeduplicator(
            ttl_seconds=getattr(self._weixin_module, "MESSAGE_DEDUP_TTL_SECONDS", 300)
        )
        self._typing_ticket_by_chat_id: dict[str, tuple[str, datetime]] = {}
        self._msg_semaphore = asyncio.Semaphore(10)

    @property
    def is_running(self) -> bool:
        return self._running and self._poll_task is not None and not self._poll_task.done()

    def update_runtime(
        self,
        *,
        account_id: str,
        token: str,
        base_url: str,
        bindings: dict[str, ClawRuntimeBinding],
        pending_bindings: tuple[ClawPendingBinding, ...] = (),
    ) -> None:
        self._account_id = account_id
        self._token = token
        self._base_url = base_url
        self._bindings_by_chat_id = dict(bindings)
        self._pending_bindings = {binding.session_id: binding for binding in pending_bindings}

    def snapshot(self) -> ClawRuntimeSnapshot:
        session_ids = sorted(
            {
                *(binding.session_id for binding in self._bindings_by_chat_id.values()),
                *self._pending_bindings.keys(),
            }
        )
        chat_ids = sorted(self._bindings_by_chat_id.keys())
        return ClawRuntimeSnapshot(
            connector_id=self.connector_id,
            active=self.is_running,
            bound_session_ids=tuple(session_ids),
            bound_chat_ids=tuple(chat_ids),
            last_inbound_at=self._last_inbound_at,
            last_outbound_at=self._last_outbound_at,
            last_error=self._last_error,
        )

    async def start(self) -> None:
        if self.is_running:
            return
        if self._aiohttp is None or not getattr(self._weixin_module, "AIOHTTP_AVAILABLE", False):
            raise RuntimeError("微信运行时缺少 aiohttp 依赖")

        self._running = True
        self._token_store.restore(self._account_id)
        self._session = self._aiohttp.ClientSession(trust_env=True)
        self._poll_task = asyncio.create_task(
            self._poll_loop(),
            name=f"claw-weixin:{self.user_id}:{self.connector_id}",
        )
        logger.info(
            "Claw runtime 启动: user=%s connector=%s account=%s bindings=%s",
            self.user_id,
            self.connector_id,
            self._account_id,
            sorted(self._bindings_by_chat_id.keys()),
        )

    async def stop(self) -> None:
        self._running = False
        poll_task = self._poll_task
        self._poll_task = None
        if poll_task is not None:
            poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await poll_task

        if self._background_tasks:
            tasks = list(self._background_tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._background_tasks.clear()

        if self._session is not None:
            await self._session.close()
            self._session = None
        logger.info(
            "Claw runtime 已停止: user=%s connector=%s account=%s",
            self.user_id,
            self.connector_id,
            self._account_id,
        )

    def note_outbound(self) -> None:
        self._last_outbound_at = self._claw_service._build_runtime_timestamp()
        self._last_error = None

    def note_error(self, error: str) -> None:
        self._last_error = str(error).strip() or None

    def _get_typing_ticket(self, chat_id: str) -> str | None:
        entry = self._typing_ticket_by_chat_id.get(chat_id)
        if entry is None:
            return None
        ticket, fetched_at = entry
        if datetime.now(timezone.utc) - fetched_at > timedelta(seconds=_TYPING_TICKET_TTL_SECONDS):
            self._typing_ticket_by_chat_id.pop(chat_id, None)
            return None
        return ticket

    async def _maybe_fetch_typing_ticket(
        self,
        chat_id: str,
        *,
        lookup_user_id: str,
        context_token: str | None,
    ) -> None:
        if self._session is None or not chat_id or not lookup_user_id:
            return
        if self._get_typing_ticket(chat_id) is not None:
            return
        try:
            response = await self._weixin_module._get_config(
                self._session,
                base_url=self._base_url,
                token=self._token,
                user_id=lookup_user_id,
                context_token=context_token,
            )
        except Exception as exc:
            logger.warning(
                "Claw runtime 获取 typing ticket 失败: user=%s connector=%s chat=%s error=%s",
                self.user_id,
                self.connector_id,
                chat_id,
                exc,
            )
            return

        typing_ticket = str(response.get("typing_ticket") or "").strip()
        if typing_ticket:
            self._typing_ticket_by_chat_id[chat_id] = (typing_ticket, datetime.now(timezone.utc))

    async def _send_typing_status(self, chat_id: str, *, status: int) -> None:
        if self._session is None:
            return
        typing_ticket = self._get_typing_ticket(chat_id)
        if not typing_ticket:
            return
        try:
            await self._weixin_module._send_typing(
                self._session,
                base_url=self._base_url,
                token=self._token,
                to_user_id=chat_id,
                typing_ticket=typing_ticket,
                status=status,
            )
        except Exception as exc:
            logger.warning(
                "Claw runtime 发送 typing 状态失败: user=%s connector=%s chat=%s status=%s error=%s",
                self.user_id,
                self.connector_id,
                chat_id,
                status,
                exc,
            )

    async def _keep_typing(self, chat_id: str) -> None:
        while True:
            await asyncio.sleep(2.0)
            typing_start = int(getattr(self._weixin_module, "TYPING_START", 1))
            await self._send_typing_status(chat_id, status=typing_start)

    async def _claim_pending_binding(
        self,
        *,
        effective_chat_id: str,
        chat_label: str | None,
    ) -> ClawRuntimeBinding | None:
        if not self._pending_bindings:
            return None
        if len(self._pending_bindings) > 1:
            self.note_error("同一微信 connector 存在多个等待首聊认领的 session，无法自动决定归属。")
            logger.warning(
                "Claw runtime 自动认领失败：存在多个 pending session user=%s connector=%s sessions=%s",
                self.user_id,
                self.connector_id,
                sorted(self._pending_bindings.keys()),
            )
            return None

        pending = next(iter(self._pending_bindings.values()))
        claimed = self._claw_service.claim_runtime_chat_binding(
            self.user_id,
            pending.session_id,
            connector_id=self.connector_id,
            chat_id=effective_chat_id,
            chat_label=chat_label,
        )
        binding = ClawRuntimeBinding(
            session_id=claimed.session_id,
            chat_id=effective_chat_id,
            chat_label=claimed.chat_label,
            updated_at=claimed.updated_at,
        )
        self._bindings_by_chat_id[effective_chat_id] = binding
        self._pending_bindings.pop(pending.session_id, None)
        logger.info(
            "Claw runtime 已自动认领首个微信聊天: user=%s connector=%s session=%s chat=%s",
            self.user_id,
            self.connector_id,
            pending.session_id,
            effective_chat_id,
        )
        return binding

    async def _poll_loop(self) -> None:
        assert self._session is not None
        sync_buf = self._weixin_module._load_sync_buf(self._hermes_home, self._account_id)
        timeout_ms = getattr(self._weixin_module, "LONG_POLL_TIMEOUT_MS", 35_000)
        consecutive_failures = 0
        max_failures = getattr(self._weixin_module, "MAX_CONSECUTIVE_FAILURES", 3)
        retry_delay = float(getattr(self._weixin_module, "RETRY_DELAY_SECONDS", 2))
        backoff_delay = float(getattr(self._weixin_module, "BACKOFF_DELAY_SECONDS", 30))
        session_expired = getattr(self._weixin_module, "SESSION_EXPIRED_ERRCODE", -14)

        while self._running:
            try:
                response = await self._weixin_module._get_updates(
                    self._session,
                    base_url=self._base_url,
                    token=self._token,
                    sync_buf=sync_buf,
                    timeout_ms=timeout_ms,
                )
                suggested_timeout = response.get("longpolling_timeout_ms")
                if isinstance(suggested_timeout, int) and suggested_timeout > 0:
                    timeout_ms = suggested_timeout

                ret = response.get("ret", 0)
                errcode = response.get("errcode", 0)
                if ret not in (0, None) or errcode not in (0, None):
                    if ret == session_expired or errcode == session_expired:
                        logger.error(
                            "Claw runtime 微信会话失效，延迟重试: user=%s connector=%s",
                            self.user_id,
                            self.connector_id,
                        )
                        await asyncio.sleep(600)
                        consecutive_failures = 0
                        continue

                    consecutive_failures += 1
                    logger.warning(
                        "Claw runtime getUpdates 失败: user=%s connector=%s ret=%s errcode=%s errmsg=%s (%s/%s)",
                        self.user_id,
                        self.connector_id,
                        ret,
                        errcode,
                        response.get("errmsg", ""),
                        consecutive_failures,
                        max_failures,
                    )
                    await asyncio.sleep(
                        backoff_delay if consecutive_failures >= max_failures else retry_delay
                    )
                    continue

                consecutive_failures = 0
                new_sync_buf = str(response.get("get_updates_buf") or "")
                if new_sync_buf:
                    sync_buf = new_sync_buf
                    self._weixin_module._save_sync_buf(
                        self._hermes_home,
                        self._account_id,
                        sync_buf,
                    )

                for message in response.get("msgs") or []:
                    self._track_task(
                        asyncio.create_task(
                            self._run_with_timeout(
                                self._process_inbound_message(message),
                                timeout=60,
                            ),
                            name=f"claw-weixin-msg:{self.connector_id}",
                        )
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                consecutive_failures += 1
                logger.error(
                    "Claw runtime poll 异常: user=%s connector=%s (%s/%s) error=%s",
                    self.user_id,
                    self.connector_id,
                    consecutive_failures,
                    max_failures,
                    exc,
                    exc_info=True,
                )
                await asyncio.sleep(
                    backoff_delay if consecutive_failures >= max_failures else retry_delay
                )

    async def _run_with_timeout(self, coro, timeout: float = 60) -> None:
        try:
            await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "Claw runtime 后台任务超时: user=%s connector=%s timeout=%ss",
                self.user_id,
                self.connector_id,
                timeout,
            )

    def _track_task(self, task: asyncio.Task[Any]) -> None:
        self._background_tasks.add(task)
        task.add_done_callback(self._on_background_task_done)

    def _on_background_task_done(self, task: asyncio.Task[Any]) -> None:
        self._background_tasks.discard(task)
        with contextlib.suppress(asyncio.CancelledError):
            exc = task.exception()
            if exc is not None:
                logger.warning(
                    "Claw runtime 后台任务失败: user=%s connector=%s error=%s",
                    self.user_id,
                    self.connector_id,
                    exc,
                )

    def _build_weixin_media_adapter(self) -> Any:
        if self._session is None:
            raise RuntimeError("Weixin runtime session is not ready")
        with self._claw_service._hermes_import_scope(self.user_id):
            import importlib

            config_module = importlib.import_module("gateway.config")
            adapter = self._weixin_module.WeixinAdapter(
                config_module.PlatformConfig(
                    enabled=True,
                    token=self._token,
                    extra={
                        "account_id": self._account_id,
                        "base_url": self._base_url,
                    },
                )
            )
        adapter._session = self._session
        adapter._token = self._token
        adapter._account_id = self._account_id
        adapter._base_url = self._base_url
        adapter._cdn_base_url = getattr(self._weixin_module, "WEIXIN_CDN_BASE_URL", "")
        adapter._token_store = self._token_store
        return adapter

    def _infer_weixin_attachment_name(self, item: dict[str, Any], index: int) -> str:
        item_type = item.get("type")
        if item_type == getattr(self._weixin_module, "ITEM_FILE", None):
            return str(
                ((item.get("file_item") or {}).get("file_name")) or f"document_{index + 1}.bin"
            )
        if item_type == getattr(self._weixin_module, "ITEM_IMAGE", None):
            return f"image_{index + 1}.jpg"
        if item_type == getattr(self._weixin_module, "ITEM_VIDEO", None):
            return f"video_{index + 1}.mp4"
        if item_type == getattr(self._weixin_module, "ITEM_VOICE", None):
            return f"voice_{index + 1}.silk"
        return f"attachment_{index + 1}.bin"

    async def _extract_inbound_payload(
        self,
        message: dict[str, Any],
    ) -> tuple[str, list[str], list[str], list[str]]:
        item_list = message.get("item_list") or []
        text = str(self._weixin_module._extract_text(item_list) or "").strip()
        if not item_list:
            return text, [], [], []

        media_item_types = {
            getattr(self._weixin_module, "ITEM_IMAGE", object()),
            getattr(self._weixin_module, "ITEM_VIDEO", object()),
            getattr(self._weixin_module, "ITEM_FILE", object()),
            getattr(self._weixin_module, "ITEM_VOICE", object()),
        }

        def _contains_media(items: list[Any]) -> bool:
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("type") in media_item_types:
                    return True
                ref_item = item.get("refermsgitem")
                if isinstance(ref_item, dict) and ref_item.get("type") in media_item_types:
                    return True
            return False

        if not _contains_media(item_list):
            return text, [], [], []

        media_paths: list[str] = []
        media_types: list[str] = []
        preferred_names: list[str] = []
        try:
            adapter = self._build_weixin_media_adapter()
        except Exception:
            logger.warning(
                "Claw runtime 构建微信媒体适配器失败，回退为纯文本入站: user=%s connector=%s",
                self.user_id,
                self.connector_id,
                exc_info=True,
            )
            return text, [], [], []

        async def _collect_item(item: dict[str, Any], index: int) -> None:
            before = len(media_paths)
            await adapter._collect_media(item, media_paths, media_types)
            added = len(media_paths) - before
            if added <= 0:
                return
            preferred_name = self._infer_weixin_attachment_name(item, index)
            for _ in range(added):
                preferred_names.append(preferred_name)

        for index, item in enumerate(item_list):
            if not isinstance(item, dict):
                continue
            await _collect_item(item, index)

            ref_item = item.get("refermsgitem")
            if isinstance(ref_item, dict):
                await _collect_item(ref_item, index)

        return text, media_paths, media_types, preferred_names

    async def _process_inbound_message(self, message: dict[str, Any]) -> None:
        async with self._msg_semaphore:
            await self._do_process_inbound_message(message)

    async def _do_process_inbound_message(self, message: dict[str, Any]) -> None:
        sender_id = str(message.get("from_user_id") or "").strip()
        if not sender_id or sender_id == self._account_id:
            return

        message_id = str(message.get("message_id") or "").strip()
        if message_id and self._dedup.is_duplicate(message_id):
            return

        chat_type, effective_chat_id = self._weixin_module._guess_chat_type(
            message,
            self._account_id,
        )
        binding = self._bindings_by_chat_id.get(effective_chat_id)
        if binding is None and sender_id != effective_chat_id:
            binding = self._bindings_by_chat_id.get(sender_id)
        if binding is None:
            binding = await self._claim_pending_binding(
                effective_chat_id=effective_chat_id,
                chat_label=effective_chat_id,
            )
        if binding is None:
            logger.debug(
                "Claw runtime 忽略未绑定入站: user=%s connector=%s chat_type=%s sender=%s chat=%s",
                self.user_id,
                self.connector_id,
                chat_type,
                sender_id,
                effective_chat_id,
            )
            return

        context_token = str(message.get("context_token") or "").strip()
        if context_token:
            self._token_store.set(self._account_id, effective_chat_id, context_token)
            if sender_id != effective_chat_id:
                self._token_store.set(self._account_id, sender_id, context_token)
        await self._maybe_fetch_typing_ticket(
            effective_chat_id,
            lookup_user_id=sender_id,
            context_token=context_token or None,
        )

        text, media_urls, media_types, preferred_names = await self._extract_inbound_payload(
            message
        )
        if not text and not media_urls:
            return

        # 按 binding 中记录的真实 session_id 执行（废弃 claw-global 硬编码）
        target_session_id = binding.session_id
        logger.info(
            "Claw runtime 收到入站文本: user=%s connector=%s session=%s chat=%s message_id=%s",
            self.user_id,
            self.connector_id,
            target_session_id,
            binding.chat_id,
            message_id or "?",
        )
        self._last_inbound_at = self._claw_service._build_runtime_timestamp()
        self._last_error = None
        typing_start = int(getattr(self._weixin_module, "TYPING_START", 1))
        await self._send_typing_status(effective_chat_id, status=typing_start)
        typing_task = asyncio.create_task(
            self._run_with_timeout(
                self._keep_typing(effective_chat_id),
                timeout=120,
            ),
            name=f"claw-weixin-typing:{self.connector_id}:{effective_chat_id}",
        )
        try:
            prompt, attachments, _summaries = self._claw_service.prepare_runtime_inbound_message(
                self.user_id,
                target_session_id,
                platform="weixin",
                message_id=message_id or f"wx-{int(time.time() * 1000)}",
                text=text,
                media_urls=media_urls,
                media_types=media_types,
                preferred_names=preferred_names,
            )
            execute_kwargs = {
                "prompt": prompt,
                "user_id": self.user_id,
                "session_id": target_session_id,
                "suppress_claw_outbound_sync": True,
            }
            if attachments:
                execute_kwargs["attachments"] = attachments
            await agent_service.execute(**execute_kwargs)

            # 自动出站：把主控回复同步到微信
            try:
                session_binding = self._claw_service.get_session_binding(
                    self.user_id, target_session_id
                )
                if session_binding.auto_sync_enabled and session_binding.chat_id:
                    dispatch_result = await self._claw_service.dispatch_last_reply(
                        self.user_id, target_session_id, force=False
                    )
                    if dispatch_result.dispatched:
                        self.note_outbound()
                        logger.info(
                            "Claw runtime 自动出站成功: user=%s session=%s chat=%s",
                            self.user_id,
                            target_session_id,
                            session_binding.chat_id,
                        )
            except Exception as exc:
                logger.warning(
                    "Claw runtime 自动出站失败: user=%s session=%s error=%s",
                    self.user_id,
                    target_session_id,
                    exc,
                )
        except Exception as exc:
            self.note_error(str(exc))
            raise
        finally:
            await asyncio.sleep(0)
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning(
                    "Claw runtime 停止 typing 状态时出错: user=%s connector=%s error=%s",
                    self.user_id,
                    self.connector_id,
                    exc,
                )
            typing_stop = int(getattr(self._weixin_module, "TYPING_STOP", 2))
            await self._send_typing_status(effective_chat_id, status=typing_stop)


class _ClawFeishuEventHandler:
    def __init__(self, runtime: "ClawFeishuRuntime") -> None:
        self._runtime = runtime

    def do_without_validation(self, payload: bytes) -> None:
        self._runtime.handle_raw_payload(payload)
        return None


class ClawFeishuRuntime:
    """单个飞书 connector 的常驻长连接 runtime。"""

    _DEDUP_TTL_SECONDS = 24 * 60 * 60
    _DEDUP_MAX_SIZE = 2048

    def __init__(
        self,
        *,
        user_id: str,
        connector_id: str,
        claw_service: ClawService,
        account_id: str,
        token: str,
        base_url: str,
        bindings: dict[str, ClawRuntimeBinding],
        pending_bindings: tuple[ClawPendingBinding, ...] = (),
    ) -> None:
        self.user_id = user_id
        self.connector_id = connector_id
        self._claw_service = claw_service
        self._app_id = account_id
        self._app_secret = token
        self._base_url = base_url
        self._bindings_by_chat_id = dict(bindings)
        self._pending_bindings = {binding.session_id: binding for binding in pending_bindings}
        self._running = False
        self._runtime_task: asyncio.Task[None] | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._ws_client: Any = None
        self._ping_task: asyncio.Task[Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_inbound_at: str | None = None
        self._last_outbound_at: str | None = None
        self._last_error: str | None = None
        self._seen_message_ids: dict[str, float] = {}
        self._msg_semaphore = asyncio.Semaphore(10)

        import importlib

        self._feishu_sdk_module = importlib.import_module("lark_oapi.ws.client")
        self._feishu_log_level = importlib.import_module("lark_oapi.core.enum").LogLevel
        with self._claw_service._hermes_import_scope(user_id):
            self._feishu_module = importlib.import_module("gateway.platforms.feishu")

    @property
    def is_running(self) -> bool:
        return self._running and self._runtime_task is not None and not self._runtime_task.done()

    def update_runtime(
        self,
        *,
        account_id: str,
        token: str,
        base_url: str,
        bindings: dict[str, ClawRuntimeBinding],
        pending_bindings: tuple[ClawPendingBinding, ...] = (),
    ) -> None:
        self._app_id = account_id
        self._app_secret = token
        self._base_url = base_url
        self._bindings_by_chat_id = dict(bindings)
        self._pending_bindings = {binding.session_id: binding for binding in pending_bindings}

    def snapshot(self) -> ClawRuntimeSnapshot:
        session_ids = sorted(
            {
                *(binding.session_id for binding in self._bindings_by_chat_id.values()),
                *self._pending_bindings.keys(),
            }
        )
        chat_ids = sorted(self._bindings_by_chat_id.keys())
        return ClawRuntimeSnapshot(
            connector_id=self.connector_id,
            active=self.is_running,
            bound_session_ids=tuple(session_ids),
            bound_chat_ids=tuple(chat_ids),
            last_inbound_at=self._last_inbound_at,
            last_outbound_at=self._last_outbound_at,
            last_error=self._last_error,
        )

    async def start(self) -> None:
        if self.is_running:
            return
        self._running = True
        self._loop = asyncio.get_running_loop()
        self._runtime_task = asyncio.create_task(
            self._run_loop(),
            name=f"claw-feishu:{self.user_id}:{self.connector_id}",
        )
        logger.info(
            "Claw runtime 启动: user=%s connector=%s app_id=%s bindings=%s",
            self.user_id,
            self.connector_id,
            self._app_id,
            sorted(self._bindings_by_chat_id.keys()),
        )

    async def stop(self) -> None:
        self._running = False
        runtime_task = self._runtime_task
        self._runtime_task = None
        if runtime_task is not None:
            runtime_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await runtime_task

        if self._background_tasks:
            tasks = list(self._background_tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._background_tasks.clear()

        await self._shutdown_client()
        logger.info(
            "Claw runtime 已停止: user=%s connector=%s app_id=%s",
            self.user_id,
            self.connector_id,
            self._app_id,
        )

    def note_outbound(self) -> None:
        self._last_outbound_at = self._claw_service._build_runtime_timestamp()
        self._last_error = None

    def note_error(self, error: str) -> None:
        self._last_error = str(error).strip() or None

    async def _run_loop(self) -> None:
        backoff_seconds = 1.0
        while self._running:
            try:
                loop = self._loop or asyncio.get_running_loop()
                self._feishu_sdk_module.loop = loop
                self._ws_client = self._feishu_sdk_module.Client(
                    app_id=self._app_id,
                    app_secret=self._app_secret,
                    log_level=self._feishu_log_level.INFO,
                    event_handler=_ClawFeishuEventHandler(self),
                    domain=self._base_url,
                    auto_reconnect=False,
                )
                await self._ws_client._connect()
                self._ping_task = asyncio.create_task(
                    self._ws_client._ping_loop(),
                    name=f"claw-feishu-ping:{self.connector_id}",
                )
                self._last_error = None
                backoff_seconds = 1.0
                while self._running:
                    if getattr(self._ws_client, "_conn", None) is None:
                        raise ConnectionError("Feishu long connection closed.")
                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.note_error(str(exc))
                logger.warning(
                    "Claw runtime 飞书连接异常: user=%s connector=%s error=%s",
                    self.user_id,
                    self.connector_id,
                    exc,
                )
                await self._shutdown_client()
                if not self._running:
                    break
                await asyncio.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2.0, 30.0)
            else:
                await self._shutdown_client()

    async def _shutdown_client(self) -> None:
        ping_task = self._ping_task
        self._ping_task = None
        if ping_task is not None:
            ping_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ping_task

        client = self._ws_client
        self._ws_client = None
        if client is not None and getattr(client, "_conn", None) is not None:
            with contextlib.suppress(Exception):
                await client._disconnect()

    async def _run_with_timeout(self, coro, timeout: float = 60) -> None:
        try:
            await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "Claw runtime 后台任务超时: user=%s connector=%s timeout=%ss",
                self.user_id,
                self.connector_id,
                timeout,
            )

    def _track_task(self, task: asyncio.Task[Any]) -> None:
        self._background_tasks.add(task)
        task.add_done_callback(self._on_background_task_done)

    def _on_background_task_done(self, task: asyncio.Task[Any]) -> None:
        self._background_tasks.discard(task)
        with contextlib.suppress(asyncio.CancelledError):
            exc = task.exception()
            if exc is not None:
                logger.warning(
                    "Claw runtime 后台任务失败: user=%s connector=%s error=%s",
                    self.user_id,
                    self.connector_id,
                    exc,
                )

    def handle_raw_payload(self, payload: bytes) -> None:
        try:
            data = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            self.note_error(str(exc))
            logger.warning(
                "Claw runtime 解析飞书事件失败: user=%s connector=%s error=%s",
                self.user_id,
                self.connector_id,
                exc,
            )
            return

        self._track_task(
            asyncio.create_task(
                self._run_with_timeout(
                    self._process_event_payload(data),
                    timeout=60,
                ),
                name=f"claw-feishu-msg:{self.connector_id}",
            )
        )

    def _is_duplicate(self, message_id: str) -> bool:
        now = time.time()
        stale_keys = [
            key
            for key, seen_at in self._seen_message_ids.items()
            if now - seen_at > self._DEDUP_TTL_SECONDS
        ]
        for key in stale_keys:
            self._seen_message_ids.pop(key, None)
        if message_id in self._seen_message_ids:
            return True
        self._seen_message_ids[message_id] = now
        while len(self._seen_message_ids) > self._DEDUP_MAX_SIZE:
            oldest = min(self._seen_message_ids.items(), key=lambda item: item[1])[0]
            self._seen_message_ids.pop(oldest, None)
        return False

    async def _claim_pending_binding(
        self,
        *,
        effective_chat_id: str,
        chat_label: str | None,
    ) -> ClawRuntimeBinding | None:
        if not self._pending_bindings:
            return None
        if len(self._pending_bindings) > 1:
            self.note_error("同一飞书 connector 存在多个等待首聊认领的 session，无法自动决定归属。")
            logger.warning(
                "Claw runtime 自动认领失败：存在多个 pending session user=%s connector=%s sessions=%s",
                self.user_id,
                self.connector_id,
                sorted(self._pending_bindings.keys()),
            )
            return None

        pending = next(iter(self._pending_bindings.values()))
        claimed = self._claw_service.claim_runtime_chat_binding(
            self.user_id,
            pending.session_id,
            connector_id=self.connector_id,
            chat_id=effective_chat_id,
            chat_label=chat_label,
        )
        binding = ClawRuntimeBinding(
            session_id=claimed.session_id,
            chat_id=effective_chat_id,
            chat_label=claimed.chat_label,
            updated_at=claimed.updated_at,
        )
        self._bindings_by_chat_id[effective_chat_id] = binding
        self._pending_bindings.pop(pending.session_id, None)
        logger.info(
            "Claw runtime 已自动认领首个飞书聊天: user=%s connector=%s session=%s chat=%s",
            self.user_id,
            self.connector_id,
            pending.session_id,
            effective_chat_id,
        )
        return binding

    def _build_feishu_media_adapter(self) -> Any:
        with self._claw_service._hermes_import_scope(self.user_id):
            import importlib

            config_module = importlib.import_module("gateway.config")
            adapter = self._feishu_module.FeishuAdapter(
                config_module.PlatformConfig(
                    enabled=True,
                    token=self._app_secret,
                    extra={
                        "app_id": self._app_id,
                        "app_secret": self._app_secret,
                        "domain": self._claw_service._resolve_feishu_domain_name(self._base_url),
                    },
                )
            )
        sdk_domain_name = self._claw_service._resolve_feishu_domain_name(self._base_url)
        sdk_domain = (
            self._feishu_module.LARK_DOMAIN
            if sdk_domain_name == "lark"
            else self._feishu_module.FEISHU_DOMAIN
        )
        if sdk_domain is None:
            raise RuntimeError("飞书运行时缺少 lark_oapi 依赖")
        adapter._client = adapter._build_lark_client(sdk_domain)
        return adapter

    async def _extract_inbound_payload(
        self,
        message: dict[str, Any],
    ) -> tuple[str, list[str], list[str], list[str]]:
        message_type = str(message.get("message_type") or "").strip().lower()
        raw_content = message.get("content")
        if isinstance(raw_content, dict):
            raw_payload = json.dumps(raw_content, ensure_ascii=False)
        else:
            raw_payload = str(raw_content or "")
        normalized = self._feishu_module.normalize_feishu_message(
            message_type=message_type,
            raw_content=raw_payload,
        )
        text = str(
            getattr(normalized, "text_content", None) or getattr(normalized, "text", "") or ""
        ).strip()
        image_keys = list(getattr(normalized, "image_keys", []) or [])
        media_refs = list(getattr(normalized, "media_refs", []) or [])
        if not message.get("message_id") or (not image_keys and not media_refs):
            return text, [], [], []

        adapter = self._build_feishu_media_adapter()
        media_urls, media_types = await adapter._download_feishu_message_resources(
            message_id=str(message.get("message_id") or ""),
            normalized=normalized,
        )
        preferred_names: list[str] = []
        for image_index, image_key in enumerate(image_keys, start=1):
            preferred_names.append(f"{str(image_key).strip() or f'image_{image_index}'}.jpg")
        for media_index, media_ref in enumerate(media_refs, start=1):
            file_name = str(getattr(media_ref, "file_name", "") or "").strip()
            file_key = str(getattr(media_ref, "file_key", "") or "").strip()
            resource_type = str(getattr(media_ref, "resource_type", "") or "").strip() or "file"
            preferred_names.append(file_name or f"{resource_type}_{file_key or media_index}")

        preferred_message_type = str(
            getattr(normalized, "preferred_message_type", "") or ""
        ).strip()
        if len(media_urls) == 1 and preferred_message_type in {"document", "audio"}:
            injected = await adapter._maybe_extract_text_document(
                media_urls[0],
                media_types[0] if media_types else "",
            )
            if injected:
                text = injected
        return text, media_urls, media_types, preferred_names

    async def _process_event_payload(self, data: dict[str, Any]) -> None:
        async with self._msg_semaphore:
            await self._do_process_event_payload(data)

    async def _do_process_event_payload(self, data: dict[str, Any]) -> None:
        event = data.get("event") if isinstance(data.get("event"), dict) else {}
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        sender = event.get("sender") if isinstance(event.get("sender"), dict) else {}
        sender_id_info = (
            sender.get("sender_id") if isinstance(sender.get("sender_id"), dict) else {}
        )

        if not message or not sender_id_info:
            return

        message_id = str(message.get("message_id") or "").strip()
        if not message_id or self._is_duplicate(message_id):
            return

        if str(sender.get("sender_type") or "").strip().lower() == "bot":
            return

        chat_id = str(message.get("chat_id") or "").strip()
        if not chat_id:
            return

        chat_type = str(message.get("chat_type") or "p2p").strip().lower()
        if chat_type != "p2p" and not message.get("mentions"):
            logger.debug(
                "Claw runtime 忽略未提及的飞书群消息: user=%s connector=%s chat=%s message_id=%s",
                self.user_id,
                self.connector_id,
                chat_id,
                message_id,
            )
            return

        binding = self._bindings_by_chat_id.get(chat_id)
        if binding is None:
            binding = await self._claim_pending_binding(
                effective_chat_id=chat_id,
                chat_label=chat_id,
            )
        if binding is None:
            logger.debug(
                "Claw runtime 忽略未绑定飞书入站: user=%s connector=%s chat=%s",
                self.user_id,
                self.connector_id,
                chat_id,
            )
            return

        text, media_urls, media_types, preferred_names = await self._extract_inbound_payload(
            message
        )
        if not text and not media_urls:
            return

        # 按 binding 中记录的真实 session_id 执行（废弃 claw-global 硬编码）
        target_session_id = binding.session_id
        logger.info(
            "Claw runtime 收到飞书入站文本: user=%s connector=%s session=%s chat=%s message_id=%s",
            self.user_id,
            self.connector_id,
            target_session_id,
            chat_id,
            message_id,
        )
        self._last_inbound_at = self._claw_service._build_runtime_timestamp()
        self._last_error = None
        try:
            prompt, attachments, _summaries = self._claw_service.prepare_runtime_inbound_message(
                self.user_id,
                target_session_id,
                platform="feishu",
                message_id=message_id,
                text=text,
                media_urls=media_urls,
                media_types=media_types,
                preferred_names=preferred_names,
            )
            execute_kwargs = {
                "prompt": prompt,
                "user_id": self.user_id,
                "session_id": target_session_id,
                "suppress_claw_outbound_sync": True,
            }
            if attachments:
                execute_kwargs["attachments"] = attachments
            await agent_service.execute(**execute_kwargs)

            # 自动出站：把主控回复同步到飞书
            try:
                session_binding = self._claw_service.get_session_binding(
                    self.user_id, target_session_id
                )
                if session_binding.auto_sync_enabled and session_binding.chat_id:
                    dispatch_result = await self._claw_service.dispatch_last_reply(
                        self.user_id, target_session_id, force=False
                    )
                    if dispatch_result.dispatched:
                        self.note_outbound()
                        logger.info(
                            "Claw runtime 自动出站成功: user=%s session=%s chat=%s",
                            self.user_id,
                            target_session_id,
                            session_binding.chat_id,
                        )
            except Exception as exc:
                logger.warning(
                    "Claw runtime 自动出站失败: user=%s session=%s error=%s",
                    self.user_id,
                    target_session_id,
                    exc,
                )
        except Exception as exc:
            self.note_error(str(exc))
            raise


class ClawRuntimeManager:
    """管理全局 connector 级 Claw runtime。"""

    def __init__(self, claw_service: ClawService | None = None) -> None:
        self._claw_service = claw_service or ClawService()
        self._runtimes: dict[tuple[str, str], Any] = {}
        self._refresh_tasks: dict[str, asyncio.Task[None]] = {}
        self._pending_refresh_users: set[str] = set()
        self._outbound_tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._pending_outbound_sessions: set[tuple[str, str]] = set()
        self._background_tasks: set[asyncio.Task[Any]] = set()

    @staticmethod
    async def _run_with_timeout(coro, timeout: float = 120) -> None:
        try:
            await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Claw runtime 后台任务超时 timeout=%ss", timeout)

    def _track_task(self, task: asyncio.Task[Any]) -> None:
        self._background_tasks.add(task)
        task.add_done_callback(self._on_background_task_done)

    def _on_background_task_done(self, task: asyncio.Task[Any]) -> None:
        self._background_tasks.discard(task)
        with contextlib.suppress(asyncio.CancelledError):
            exc = task.exception()
            if exc is not None:
                logger.warning(
                    "Claw runtime 后台任务失败: task=%s error=%s",
                    task.get_name(),
                    exc,
                )

    def schedule_bootstrap_all_users(self) -> None:
        for user_dir in self._claw_service.workspace_root.iterdir():
            if not user_dir.is_dir() or user_dir.name.startswith("."):
                continue
            self.schedule_refresh_for_user(user_dir.name)

    def schedule_refresh_for_user(self, user_id: str) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("Claw runtime refresh 跳过：当前无运行中的事件循环")
            return

        self._pending_refresh_users.add(user_id)
        existing = self._refresh_tasks.get(user_id)
        if existing is not None and not existing.done():
            return

        async def _runner() -> None:
            try:
                while user_id in self._pending_refresh_users:
                    self._pending_refresh_users.discard(user_id)
                    await self._refresh_user(user_id)
            finally:
                current = self._refresh_tasks.get(user_id)
                if current is task_ref:
                    self._refresh_tasks.pop(user_id, None)

        task_ref = asyncio.create_task(
            self._run_with_timeout(
                _runner(),
                timeout=120,
            ),
            name=f"claw-runtime-refresh:{user_id}",
        )
        self._refresh_tasks[user_id] = task_ref
        self._track_task(task_ref)

    def schedule_session_outbound(self, user_id: str, session_id: str) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("Claw 自动出站跳过：当前无运行中的事件循环")
            return

        outbound_key = (user_id, session_id)
        self._pending_outbound_sessions.add(outbound_key)
        existing = self._outbound_tasks.get(outbound_key)
        if existing is not None and not existing.done():
            return

        async def _runner() -> None:
            try:
                while outbound_key in self._pending_outbound_sessions:
                    self._pending_outbound_sessions.discard(outbound_key)
                    await self._dispatch_session_outbound(user_id, session_id)
            finally:
                current = self._outbound_tasks.get(outbound_key)
                if current is task_ref:
                    self._outbound_tasks.pop(outbound_key, None)

        task_ref = asyncio.create_task(
            self._run_with_timeout(
                _runner(),
                timeout=120,
            ),
            name=f"claw-dispatch:{user_id}:{session_id}",
        )
        self._outbound_tasks[outbound_key] = task_ref
        self._track_task(task_ref)

    def get_runtime_snapshot(
        self,
        user_id: str,
        connector_id: str,
    ) -> ClawRuntimeSnapshot | None:
        runtime = self._runtimes.get((user_id, connector_id))
        if runtime is None:
            return None
        return runtime.snapshot()

    async def _refresh_user(self, user_id: str) -> None:
        # 先清理长期 idle 的 binding
        self._claw_service.expire_idle_bindings(user_id)
        # Claw 对齐普通工作区上下文，不再限定为 gateway session
        running_bindings = self._claw_service.list_running_bindings(user_id)
        # 对 running binding 按 chat_id 去重，防止旁路冲突
        running_bindings = self._claw_service._deduplicate_running_bindings(
            user_id, running_bindings
        )
        grouped: dict[str, dict[str, Any]] = {}

        for binding in running_bindings:
            connector_id = str(binding.connector_id or "").strip()
            if not connector_id or binding.connector is None:
                continue
            secret = self._claw_service.resolve_connector_secret(user_id, connector_id)
            if secret is None:
                logger.warning(
                    "Claw runtime 刷新跳过：connector 缺少有效凭据 user=%s connector=%s",
                    user_id,
                    connector_id,
                )
                continue

            group_payload = grouped.setdefault(
                connector_id,
                {
                    "secret": secret,
                    "bindings": {},
                    "pending_bindings": [],
                },
            )
            if binding.chat_id:
                bindings_by_chat = group_payload["bindings"]
                existing = bindings_by_chat.get(binding.chat_id)
                next_binding = ClawRuntimeBinding(
                    session_id=binding.session_id,
                    chat_id=binding.chat_id,
                    chat_label=binding.chat_label,
                    updated_at=binding.updated_at,
                )
                if existing is None or next_binding.updated_at >= existing.updated_at:
                    bindings_by_chat[binding.chat_id] = next_binding
            else:
                group_payload["pending_bindings"].append(
                    ClawPendingBinding(
                        session_id=binding.session_id,
                        updated_at=binding.updated_at,
                    )
                )

        active_connector_ids = set(grouped.keys())
        for connector_id, payload in grouped.items():
            secret = payload["secret"]
            bindings = payload["bindings"]
            runtime_key = (user_id, connector_id)
            runtime = self._runtimes.get(runtime_key)
            platform = str(secret.get("platform") or "weixin").strip().lower() or "weixin"
            if platform != "weixin":
                if platform != "feishu":
                    if runtime is not None:
                        self._runtimes.pop(runtime_key, None)
                        await runtime.stop()
                    logger.warning(
                        "Claw runtime 暂未实现该平台，跳过启动: user=%s connector=%s platform=%s",
                        user_id,
                        connector_id,
                        platform,
                    )
                    continue
            runtime_cls = ClawWeixinRuntime if platform == "weixin" else ClawFeishuRuntime
            if runtime is not None and not isinstance(runtime, runtime_cls):
                self._runtimes.pop(runtime_key, None)
                await runtime.stop()
                runtime = None
            if runtime is None:
                if platform == "weixin":
                    runtime = ClawWeixinRuntime(
                        user_id=user_id,
                        connector_id=connector_id,
                        claw_service=self._claw_service,
                        account_id=secret["account_id"],
                        token=secret["token"],
                        base_url=secret["base_url"],
                        bindings=bindings,
                        pending_bindings=tuple(payload["pending_bindings"]),
                    )
                else:
                    runtime = ClawFeishuRuntime(
                        user_id=user_id,
                        connector_id=connector_id,
                        claw_service=self._claw_service,
                        account_id=secret["account_id"],
                        token=secret["token"],
                        base_url=secret["base_url"],
                        bindings=bindings,
                        pending_bindings=tuple(payload["pending_bindings"]),
                    )
                self._runtimes[runtime_key] = runtime
            else:
                runtime.update_runtime(
                    account_id=secret["account_id"],
                    token=secret["token"],
                    base_url=secret["base_url"],
                    bindings=bindings,
                    pending_bindings=tuple(payload["pending_bindings"]),
                )
            await runtime.start()

        stale_keys = [
            key
            for key in self._runtimes.keys()
            if key[0] == user_id and key[1] not in active_connector_ids
        ]
        for key in stale_keys:
            runtime = self._runtimes.pop(key, None)
            if runtime is not None:
                await runtime.stop()

    async def _dispatch_session_outbound(self, user_id: str, session_id: str) -> None:
        binding = self._claw_service.get_session_binding(user_id, session_id)
        if (
            not binding.connector_id
            or not binding.chat_id
            or not binding.auto_sync_enabled
            or binding.link_status != "running"
        ):
            return
        try:
            result = await self._claw_service.dispatch_last_reply(user_id, session_id)
            binding = self._claw_service.get_session_binding(user_id, session_id)
            if result.dispatched and binding.connector_id:
                runtime = self._runtimes.get((user_id, binding.connector_id))
                if runtime is not None:
                    runtime.note_outbound()
            logger.info(
                "Claw 自动出站完成: user=%s session=%s dispatched=%s reason=%s",
                user_id,
                session_id,
                result.dispatched,
                result.reason,
            )
        except Exception as exc:
            binding = self._claw_service.get_session_binding(user_id, session_id)
            if binding.connector_id:
                runtime = self._runtimes.get((user_id, binding.connector_id))
                if runtime is not None:
                    runtime.note_error(str(exc))
            logger.warning(
                "Claw 自动出站失败: user=%s session=%s error=%s",
                user_id,
                session_id,
                exc,
            )

    async def shutdown(self) -> None:
        if self._outbound_tasks:
            tasks = list(self._outbound_tasks.values())
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._outbound_tasks.clear()
            self._pending_outbound_sessions.clear()

        for task in list(self._refresh_tasks.values()):
            task.cancel()
        if self._refresh_tasks:
            await asyncio.gather(*self._refresh_tasks.values(), return_exceptions=True)
            self._refresh_tasks.clear()

        for runtime in list(self._runtimes.values()):
            await runtime.stop()
        self._runtimes.clear()


_CLAW_RUNTIME_MANAGER: ClawRuntimeManager | None = None


def get_claw_runtime_manager() -> ClawRuntimeManager:
    global _CLAW_RUNTIME_MANAGER
    if _CLAW_RUNTIME_MANAGER is None:
        _CLAW_RUNTIME_MANAGER = ClawRuntimeManager()
    return _CLAW_RUNTIME_MANAGER


def ensure_claw_runtime_running() -> None:
    get_claw_runtime_manager().schedule_bootstrap_all_users()


async def shutdown_claw_runtime_manager() -> None:
    global _CLAW_RUNTIME_MANAGER
    if _CLAW_RUNTIME_MANAGER is not None:
        await _CLAW_RUNTIME_MANAGER.shutdown()
        _CLAW_RUNTIME_MANAGER = None
