"""Claw 消息准备 mixin（runtime inbound message）."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

from app.models.claw import ClawAttachmentSummary

from ._common import _PLATFORM_LABELS, _append_platform_source_marker, _utcnow_iso

logger = logging.getLogger(__name__)


class ClawInboundMixin:
    def _normalize_attachment_summaries(self, raw_items: Any) -> list[ClawAttachmentSummary]:
        if not isinstance(raw_items, list):
            return []
        normalized: list[ClawAttachmentSummary] = []
        for item in raw_items:
            if isinstance(item, ClawAttachmentSummary):
                normalized.append(item)
                continue
            if not isinstance(item, dict):
                continue
            try:
                normalized.append(ClawAttachmentSummary(**item))
            except Exception:
                continue
        return normalized

    def _collect_outbound_attachments(
        self,
        user_id: str,
        session_id: str,
        *,
        raw_text: str,
    ) -> list[ClawAttachmentSummary]:
        attachments: list[ClawAttachmentSummary] = []
        for workspace_path in self._extract_workspace_paths_from_text(raw_text):
            resolved = self._resolve_workspace_file(user_id, session_id, workspace_path)
            if resolved is None:
                continue
            import mimetypes

            media_type = mimetypes.guess_type(resolved.name)[0]
            attachments.append(
                ClawAttachmentSummary(
                    display_name=resolved.name,
                    workspace_path=workspace_path,
                    media_type=media_type,
                    size_bytes=resolved.stat().st_size,
                    imported_to_workspace=True,
                    imported_at=None,
                )
            )
        return attachments

    def _build_preview_digest(
        self,
        text: str,
        attachments: list[ClawAttachmentSummary],
    ) -> Optional[str]:
        payload = {
            "text": text.strip(),
            "attachments": [
                {
                    "path": item.workspace_path,
                    "media_type": item.media_type,
                    "size_bytes": item.size_bytes,
                }
                for item in attachments
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).strip()
        if not encoded or encoded == '{"attachments": [], "text": ""}':
            return None
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]

    def prepare_runtime_inbound_message(
        self,
        user_id: str,
        session_id: str,
        *,
        platform: str,
        message_id: str,
        text: str,
        media_urls: list[str],
        media_types: list[str],
        preferred_names: list[str] | None = None,
    ) -> tuple[str, list[str], list[ClawAttachmentSummary]]:
        attachments: list[ClawAttachmentSummary] = []
        relative_paths: list[str] = []
        for index, source_path in enumerate(media_urls):
            summary = self._copy_media_into_session_workspace(
                user_id,
                session_id,
                platform=platform,
                message_id=message_id,
                source_path=source_path,
                media_type=media_types[index] if index < len(media_types) else "",
                preferred_name=(
                    preferred_names[index]
                    if preferred_names and index < len(preferred_names)
                    else None
                ),
                index=index,
            )
            if summary is None:
                continue
            attachments.append(summary)
            relative_paths.append(summary.workspace_path.removeprefix("/workspace/"))

        payload = self._load_session_binding_record(user_id, session_id)
        now = _utcnow_iso()
        payload.update(
            {
                "last_inbound_at": now,
                "last_inbound_message_id": message_id or None,
                "last_inbound_text": text.strip() or None,
                "last_inbound_attachments": [item.model_dump() for item in attachments],
                "updated_at": now,
            }
        )
        self._save_session_binding_record(user_id, session_id, payload)

        platform_label = _PLATFORM_LABELS.get(platform, platform)
        cleaned_text = text.strip()
        if cleaned_text and attachments:
            prompt = (
                f"{cleaned_text}\n\n"
                f"（本轮还从{platform_label}导入了 {len(attachments)} 个附件："
                + "、".join(item.display_name for item in attachments[:5])
                + "。请结合当前轮附件一起处理。）"
            )
        elif cleaned_text:
            prompt = cleaned_text
        elif attachments:
            prompt = (
                f"收到来自{platform_label}的 {len(attachments)} 个附件："
                + "、".join(item.display_name for item in attachments[:5])
                + "。请优先查看当前轮附件并处理。"
            )
        else:
            prompt = ""

        return _append_platform_source_marker(prompt, platform), relative_paths, attachments
