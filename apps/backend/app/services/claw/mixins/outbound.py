"""Claw 出站消息 mixin."""

from __future__ import annotations

import importlib
import logging
import mimetypes
import os
import re

from app.models.claw import ClawAttachmentSummary, ClawDispatchResult, ClawOutboundPreview

from ._common import (
    _OUTBOUND_AIASYS_FILE_RE,
    _OUTBOUND_MARKDOWN_IMAGE_RE,
    _OUTBOUND_MARKDOWN_LINK_RE,
    _PLATFORM_LABELS,
    _utcnow_iso,
)

logger = logging.getLogger(__name__)


class ClawOutboundMixin:
    def _clean_outbound_text(self, text: str, attachments: list[ClawAttachmentSummary]) -> str:
        cleaned = text
        attachment_paths = {item.workspace_path for item in attachments}

        def _replace_markdown_image(match: re.Match[str]) -> str:
            path = str(match.group("path") or "").strip().removeprefix("file://")
            if path not in attachment_paths:
                return match.group(0)
            label = str(match.group("label") or "").strip()
            return label

        def _replace_markdown_link(match: re.Match[str]) -> str:
            path = str(match.group("path") or "").strip().removeprefix("file://")
            if path not in attachment_paths:
                return match.group(0)
            label = str(match.group("label") or "").strip()
            return label

        def _replace_file_block(match: re.Match[str]) -> str:
            path = str(match.group("path") or "").strip().removeprefix("file://")
            return "" if path in attachment_paths else match.group(0)

        cleaned = _OUTBOUND_AIASYS_FILE_RE.sub(_replace_file_block, cleaned)
        cleaned = _OUTBOUND_MARKDOWN_IMAGE_RE.sub(_replace_markdown_image, cleaned)
        cleaned = _OUTBOUND_MARKDOWN_LINK_RE.sub(_replace_markdown_link, cleaned)
        for workspace_path in attachment_paths:
            cleaned = cleaned.replace(workspace_path, "")
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = "\n".join(line.rstrip() for line in cleaned.splitlines())
        return cleaned.strip()

    def _format_for_weixin(
        self,
        user_id: str,
        *,
        account_id: str,
        base_url: str,
        text: str,
    ) -> tuple[str, list[str]]:
        try:
            with self._hermes_import_scope(user_id):
                config_module = importlib.import_module("gateway.config")
                weixin_module = importlib.import_module("gateway.platforms.weixin")
                adapter = weixin_module.WeixinAdapter(
                    config_module.PlatformConfig(
                        enabled=True,
                        token=os.environ.get("WEIXIN_PREVIEW_TOKEN", "preview-token"),
                        extra={
                            "account_id": account_id,
                            "base_url": base_url or "https://api.weixin.qq.com",
                        },
                    )
                )
                formatted = adapter.format_message(text)
                chunks = [chunk for chunk in adapter._split_text(formatted) if chunk.strip()]
                return formatted, chunks or [formatted]
        except Exception as exc:
            logger.warning("Claw Weixin 格式化回退到原文: %s", exc)
            cleaned = text.strip()
            return cleaned, [cleaned] if cleaned else []

    def _format_for_feishu(self, text: str) -> tuple[str, list[str]]:
        cleaned = text.strip()
        return cleaned, [cleaned] if cleaned else []

    def get_outbound_preview(self, user_id: str, session_id: str) -> ClawOutboundPreview:
        binding = self.get_session_binding(user_id, session_id)
        raw_text, source_timestamp = self._extract_last_assistant_visible_text_from_session_db(
            user_id,
            session_id,
        )
        if not raw_text:
            messages = self.session_manager.get_history(session_id, user_id)
            raw_text, source_timestamp = self._extract_last_assistant_visible_text(messages)
        if not raw_text:
            return ClawOutboundPreview(
                session_id=session_id,
                channel_id=binding.channel_id,
                connector_id=binding.connector_id,
                platform=binding.connector.platform if binding.connector else None,
                has_candidate=False,
                raw_text="",
                formatted_text="",
                chunks=[],
                digest=None,
                duplicate_of_last_dispatch=False,
                source_timestamp=None,
            )

        attachments = self._collect_outbound_attachments(
            user_id,
            session_id,
            raw_text=raw_text,
        )
        cleaned_text = self._clean_outbound_text(raw_text, attachments)
        if binding.connector and binding.connector.platform == "weixin":
            formatted_text, chunks = self._format_for_weixin(
                user_id,
                account_id=binding.connector.account_id,
                base_url=binding.connector.base_url,
                text=cleaned_text,
            )
        elif binding.connector and binding.connector.platform == "feishu":
            formatted_text, chunks = self._format_for_feishu(cleaned_text)
        else:
            formatted_text = cleaned_text.strip()
            chunks = [formatted_text] if formatted_text else []

        digest = self._build_preview_digest(formatted_text, attachments)
        return ClawOutboundPreview(
            session_id=session_id,
            channel_id=binding.channel_id,
            connector_id=binding.connector_id,
            platform=binding.connector.platform if binding.connector else None,
            has_candidate=bool(formatted_text.strip() or attachments),
            raw_text=raw_text,
            formatted_text=formatted_text,
            chunks=chunks,
            attachments=attachments,
            digest=digest,
            duplicate_of_last_dispatch=bool(
                digest
                and binding.last_dispatched_digest
                and digest == binding.last_dispatched_digest
            ),
            source_timestamp=source_timestamp,
        )

    def _resolve_feishu_domain_name(self, base_url: str) -> str:
        normalized = str(base_url or "").strip().lower()
        return "lark" if "larksuite" in normalized or "open.lark" in normalized else "feishu"

    async def _send_weixin_message(
        self,
        user_id: str,
        *,
        session_id: str,
        account_id: str,
        token: str,
        base_url: str,
        chat_id: str,
        message: str,
        attachments: list[ClawAttachmentSummary] | None = None,
    ) -> None:
        media_files: list[tuple[str, bool]] = []
        for item in attachments or []:
            resolved = self._resolve_workspace_file(user_id, session_id, item.workspace_path)
            if resolved is None:
                continue
            media_files.append((str(resolved), bool((item.media_type or "").startswith("audio/"))))
        with self._hermes_import_scope(user_id):
            weixin_module = importlib.import_module("gateway.platforms.weixin")
            result = await weixin_module.send_weixin_direct(
                extra={
                    "account_id": account_id,
                    "base_url": base_url or "https://api.weixin.qq.com",
                },
                token=token,
                chat_id=chat_id,
                message=message,
                media_files=media_files,
            )
        if not result or result.get("error"):
            raise RuntimeError(str((result or {}).get("error") or "微信发送失败"))

    async def _send_feishu_message(
        self,
        user_id: str,
        *,
        session_id: str,
        app_id: str,
        app_secret: str,
        base_url: str,
        chat_id: str,
        message: str,
        attachments: list[ClawAttachmentSummary] | None = None,
    ) -> None:
        with self._hermes_import_scope(user_id):
            config_module = importlib.import_module("gateway.config")
            feishu_module = importlib.import_module("gateway.platforms.feishu")
            adapter = feishu_module.FeishuAdapter(
                config_module.PlatformConfig(
                    enabled=True,
                    token=app_secret,
                    extra={
                        "app_id": app_id,
                        "app_secret": app_secret,
                        "domain": self._resolve_feishu_domain_name(base_url),
                    },
                )
            )
            sdk_domain_name = self._resolve_feishu_domain_name(base_url)
            sdk_domain = (
                feishu_module.LARK_DOMAIN
                if sdk_domain_name == "lark"
                else feishu_module.FEISHU_DOMAIN
            )
            if sdk_domain is None:
                raise RuntimeError("飞书运行时缺少 lark_oapi 依赖")
            adapter._client = adapter._build_lark_client(sdk_domain)

            if message.strip():
                send_result = await adapter.send(chat_id, message)
                if not send_result.success:
                    raise RuntimeError(str(send_result.error or "飞书文本发送失败"))

            for item in attachments or []:
                resolved = self._resolve_workspace_file(user_id, session_id, item.workspace_path)
                if resolved is None:
                    continue
                suffix = resolved.suffix.lower()
                media_type = item.media_type or mimetypes.guess_type(resolved.name)[0] or ""
                if media_type.startswith("image/") or suffix in {
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".gif",
                    ".webp",
                    ".bmp",
                }:
                    send_result = await adapter.send_image_file(chat_id, str(resolved))
                elif media_type.startswith("video/") or suffix in {
                    ".mp4",
                    ".mov",
                    ".m4v",
                    ".avi",
                    ".mkv",
                }:
                    send_result = await adapter.send_video(chat_id, str(resolved))
                elif media_type.startswith("audio/") or suffix in {
                    ".mp3",
                    ".wav",
                    ".ogg",
                    ".m4a",
                    ".aac",
                    ".silk",
                }:
                    send_result = await adapter.send_voice(chat_id, str(resolved))
                else:
                    send_result = await adapter.send_document(chat_id, str(resolved))
                if not send_result.success:
                    raise RuntimeError(str(send_result.error or "飞书附件发送失败"))

    async def dispatch_last_reply(
        self,
        user_id: str,
        session_id: str,
        *,
        force: bool = False,
    ) -> ClawDispatchResult:
        binding = self.get_session_binding(user_id, session_id)
        if not binding.connector_id or not binding.chat_id:
            raise ValueError("当前 session 还没有完成 Claw 绑定")
        connector_record = self._find_connector_record(user_id, binding.connector_id)
        if connector_record is None:
            raise ValueError("当前绑定的频道不存在")

        preview = self.get_outbound_preview(user_id, session_id)
        if not preview.has_candidate or (
            not preview.formatted_text.strip() and not preview.attachments
        ):
            return ClawDispatchResult(
                success=True,
                dispatched=False,
                reason="当前 session 还没有可同步的 assistant 回复。",
                binding=binding,
                preview=preview,
            )
        if preview.duplicate_of_last_dispatch and not force:
            return ClawDispatchResult(
                success=True,
                dispatched=False,
                reason="最近一次可见回复已经同步，无需重复发送。",
                binding=binding,
                preview=preview,
            )

        token = self._resolve_connector_record_secret(connector_record)
        if not token:
            raise ValueError("当前频道缺少有效凭据")
        connector_platform = (
            str(connector_record.get("platform") or "weixin").strip().lower() or "weixin"
        )

        try:
            if connector_platform == "weixin":
                await self._send_weixin_message(
                    user_id,
                    session_id=session_id,
                    account_id=str(connector_record.get("account_id") or ""),
                    token=token,
                    base_url=str(connector_record.get("base_url") or "https://api.weixin.qq.com"),
                    chat_id=binding.chat_id,
                    message=preview.formatted_text,
                    attachments=preview.attachments,
                )
            elif connector_platform == "feishu":
                from app.models.claw import FEISHU_DEFAULT_BASE_URL

                await self._send_feishu_message(
                    user_id,
                    session_id=session_id,
                    app_id=str(connector_record.get("account_id") or ""),
                    app_secret=token,
                    base_url=str(connector_record.get("base_url") or FEISHU_DEFAULT_BASE_URL),
                    chat_id=binding.chat_id,
                    message=preview.formatted_text,
                    attachments=preview.attachments,
                )
            else:
                platform_label = _PLATFORM_LABELS.get(connector_platform, connector_platform)
                raise RuntimeError(f"{platform_label} 还没有接入自动出站。")
        except Exception as exc:
            payload = self._load_session_binding_record(user_id, session_id)
            payload.update(
                {
                    "link_status": "error",
                    "last_error": str(exc),
                    "updated_at": _utcnow_iso(),
                }
            )
            self._save_session_binding_record(user_id, session_id, payload)
            raise

        payload = self._load_session_binding_record(user_id, session_id)
        payload.update(
            {
                "link_status": (
                    "running"
                    if payload.get("auto_sync_enabled")
                    else payload.get("link_status", "stopped")
                ),
                "last_error": None,
                "last_dispatched_at": _utcnow_iso(),
                "last_dispatched_digest": preview.digest,
                "updated_at": _utcnow_iso(),
            }
        )
        self._save_session_binding_record(user_id, session_id, payload)
        return ClawDispatchResult(
            success=True,
            dispatched=True,
            reason=None,
            binding=self.get_session_binding(user_id, session_id),
            preview=self.get_outbound_preview(user_id, session_id),
        )
