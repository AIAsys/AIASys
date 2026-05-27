"""Claw 会话绑定管理 mixin."""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any, Optional

from app.models.claw import ClawLinkStatus, SessionClawBinding, SessionClawBindingRequest

from ._common import _utcnow_iso

logger = logging.getLogger(__name__)


class ClawBindingsMixin:
    def _load_session_binding_record(
        self,
        user_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        path = self._get_session_binding_path(user_id, session_id)
        default_payload = {
            "version": 1,
            "session_id": session_id,
            "channel_id": None,
            "connector_id": None,
            "chat_id": None,
            "chat_label": None,
            "outbound_policy": "latest_assistant_reply",
            "auto_sync_enabled": False,
            "link_status": "unconfigured",
            "last_error": None,
            "last_started_at": None,
            "last_stopped_at": None,
            "last_dispatched_at": None,
            "last_dispatched_digest": None,
            "last_inbound_at": None,
            "last_inbound_message_id": None,
            "last_inbound_text": None,
            "last_inbound_attachments": [],
            "updated_at": _utcnow_iso(),
        }
        if not path.exists():
            return default_payload
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(
                "加载 Claw session 绑定失败: user=%s session=%s error=%s",
                user_id,
                session_id,
                exc,
            )
            return default_payload
        if not isinstance(raw, dict):
            return default_payload
        return {
            **default_payload,
            **raw,
            "session_id": session_id,
        }

    def _save_session_binding_record(
        self,
        user_id: str,
        session_id: str,
        payload: dict[str, Any],
    ) -> None:
        path = self._get_session_binding_path(user_id, session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _build_session_key(self, platform: str, chat_type: str, chat_id: str) -> str:
        return f"{platform}:{chat_type}:{chat_id}"

    def _find_session_by_key(self, user_id: str, session_key: str) -> Optional[str]:
        mapping = self._load_session_keys(user_id)
        session_id = mapping.get(session_key)
        if not session_id:
            return None
        # 验证 session 是否仍然存在
        session_dir = self._get_user_root(user_id) / session_id
        if not (session_dir / "metadata.json").exists():
            # session 已删除，清理映射
            mapping.pop(session_key, None)
            self._save_session_keys(user_id, mapping)
            return None
        return session_id

    def _check_binding_conflict(
        self,
        user_id: str,
        session_id: str,
        channel_id: Optional[str],
        chat_id: Optional[str],
    ) -> None:
        """检查同一 channel + chat_id 是否已被其他会话绑定。"""
        if not channel_id or not chat_id:
            return
        user_root = self._get_user_root(user_id)
        from ._common import _CLAW_BINDING_FILE

        for path in user_root.glob("*/.aiasys/session/" + _CLAW_BINDING_FILE):
            other_session_id = path.parent.parent.parent.name
            if other_session_id == session_id:
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            other_channel_id = str(raw.get("channel_id") or raw.get("connector_id") or "").strip()
            other_chat_id = str(raw.get("chat_id") or "").strip()
            other_status = str(raw.get("link_status") or "unconfigured")
            if (
                other_channel_id == channel_id
                and other_chat_id == chat_id
                and other_status == "running"
            ):
                raise ValueError(
                    f"该聊天已被会话 {other_session_id} 绑定且正在运行，"
                    f"请先在该会话停止或解绑后再重新绑定。"
                )

    def get_session_binding(self, user_id: str, session_id: str) -> SessionClawBinding:
        payload = self._load_session_binding_record(user_id, session_id)
        channel_id = str(payload.get("channel_id") or payload.get("connector_id") or "").strip()
        connector_id = channel_id
        connector = None
        runtime_snapshot = None
        if connector_id:
            record = self._find_connector_record(user_id, connector_id)
            if record is not None:
                connector = self._to_public_connector(record)
            try:
                from app.services.claw_runtime import get_claw_runtime_manager

                runtime_snapshot = get_claw_runtime_manager().get_runtime_snapshot(
                    user_id,
                    connector_id,
                )
            except Exception:
                runtime_snapshot = None

        link_status = str(payload.get("link_status") or "unconfigured")
        if not connector_id:
            link_status = "unconfigured"
        elif link_status not in {"stopped", "running", "error"}:
            link_status = "stopped"

        return SessionClawBinding(
            session_id=session_id,
            channel_id=channel_id or None,
            connector_id=connector_id or None,
            connector=connector,
            chat_id=str(payload.get("chat_id") or "").strip() or None,
            chat_label=str(payload.get("chat_label") or "").strip() or None,
            outbound_policy="latest_assistant_reply",
            auto_sync_enabled=bool(payload.get("auto_sync_enabled", False)),
            link_status=link_status,  # type: ignore[arg-type]
            last_error=str(payload.get("last_error") or "").strip() or None,
            last_started_at=str(payload.get("last_started_at") or "").strip() or None,
            last_stopped_at=str(payload.get("last_stopped_at") or "").strip() or None,
            last_dispatched_at=str(payload.get("last_dispatched_at") or "").strip() or None,
            last_dispatched_digest=str(payload.get("last_dispatched_digest") or "").strip() or None,
            last_inbound_at=str(payload.get("last_inbound_at") or "").strip() or None,
            last_inbound_message_id=str(payload.get("last_inbound_message_id") or "").strip()
            or None,
            last_inbound_text=str(payload.get("last_inbound_text") or "").strip() or None,
            last_inbound_attachments=self._normalize_attachment_summaries(
                payload.get("last_inbound_attachments")
            ),
            runtime_active=bool(runtime_snapshot.active) if runtime_snapshot else False,
            runtime_bound_session_ids=(
                list(runtime_snapshot.bound_session_ids) if runtime_snapshot else []
            ),
            runtime_bound_chat_ids=(
                list(runtime_snapshot.bound_chat_ids) if runtime_snapshot else []
            ),
            runtime_last_inbound_at=runtime_snapshot.last_inbound_at if runtime_snapshot else None,
            runtime_last_outbound_at=(
                runtime_snapshot.last_outbound_at if runtime_snapshot else None
            ),
            runtime_last_error=runtime_snapshot.last_error if runtime_snapshot else None,
            updated_at=str(payload.get("updated_at") or _utcnow_iso()),
        )

    def save_session_binding(
        self,
        user_id: str,
        session_id: str,
        request: SessionClawBindingRequest,
    ) -> SessionClawBinding:
        existing = self._load_session_binding_record(user_id, session_id)
        channel_id = request.channel_id or request.connector_id
        connector_id = channel_id
        chat_id = request.chat_id
        chat_label = request.chat_label

        if connector_id:
            record = self._find_connector_record(user_id, connector_id)
            if record is None:
                raise ValueError("指定的频道不存在")

        # 冲突检测：同一 channel + chat_id 不能同时绑定到多个会话
        self._check_binding_conflict(user_id, session_id, channel_id, chat_id)

        existing_channel_id = str(
            existing.get("channel_id") or existing.get("connector_id") or ""
        ).strip()
        binding_changed = (
            existing_channel_id != str(channel_id or "").strip()
            or str(existing.get("chat_id") or "").strip() != str(chat_id or "").strip()
            or str(existing.get("chat_label") or "").strip() != str(chat_label or "").strip()
        )

        next_status: ClawLinkStatus
        if connector_id:
            next_status = (
                "stopped"
                if binding_changed
                else (
                    existing.get("link_status")
                    if str(existing.get("link_status") or "") in {"stopped", "running", "error"}
                    else "stopped"
                )
            )
        else:
            next_status = "unconfigured"

        payload = {
            **existing,
            "version": 1,
            "session_id": session_id,
            "channel_id": channel_id,
            "connector_id": connector_id,
            "chat_id": chat_id,
            "chat_label": chat_label,
            "outbound_policy": "latest_assistant_reply",
            "auto_sync_enabled": (
                bool(existing.get("auto_sync_enabled", False))
                if next_status != "unconfigured" and not binding_changed
                else False
            ),
            "link_status": next_status,
            "updated_at": _utcnow_iso(),
        }
        if next_status == "unconfigured":
            payload["last_error"] = None
        self._save_session_binding_record(user_id, session_id, payload)
        binding = self.get_session_binding(user_id, session_id)
        self._schedule_runtime_refresh(user_id)
        return binding

    def clear_session_binding(self, user_id: str, session_id: str) -> SessionClawBinding:
        payload = {
            "version": 1,
            "session_id": session_id,
            "channel_id": None,
            "connector_id": None,
            "chat_id": None,
            "chat_label": None,
            "outbound_policy": "latest_assistant_reply",
            "auto_sync_enabled": False,
            "link_status": "unconfigured",
            "last_error": None,
            "last_started_at": None,
            "last_stopped_at": _utcnow_iso(),
            "last_dispatched_at": None,
            "last_dispatched_digest": None,
            "updated_at": _utcnow_iso(),
        }
        self._save_session_binding_record(user_id, session_id, payload)
        binding = self.get_session_binding(user_id, session_id)
        self._schedule_runtime_refresh(user_id)
        return binding

    def start_session_link(self, user_id: str, session_id: str) -> SessionClawBinding:
        binding = self.get_session_binding(user_id, session_id)
        if not binding.connector_id:
            raise ValueError("请先选择一个频道")
        record = self._find_connector_record(user_id, binding.connector_id)
        if record is None:
            raise ValueError("当前绑定的频道不存在")
        platform = str(record.get("platform") or "weixin").strip().lower() or "weixin"
        if not self.is_runtime_enabled_platform(platform):
            from ._common import _PLATFORM_LABELS

            platform_label = _PLATFORM_LABELS.get(platform, platform)
            raise ValueError(f"{platform_label} 还没有接入当前 Claw runtime。")
        token = self._resolve_connector_record_secret(record)
        if not token:
            raise ValueError("当前频道缺少有效凭据")

        payload = self._load_session_binding_record(user_id, session_id)
        payload.update(
            {
                "auto_sync_enabled": True,
                "link_status": "running",
                "last_error": None,
                "last_started_at": _utcnow_iso(),
                "updated_at": _utcnow_iso(),
            }
        )
        self._save_session_binding_record(user_id, session_id, payload)
        binding = self.get_session_binding(user_id, session_id)
        self._schedule_runtime_refresh(user_id)
        return binding

    def stop_session_link(self, user_id: str, session_id: str) -> SessionClawBinding:
        payload = self._load_session_binding_record(user_id, session_id)
        payload.update(
            {
                "auto_sync_enabled": False,
                "link_status": (
                    "stopped"
                    if payload.get("channel_id") or payload.get("connector_id")
                    else "unconfigured"
                ),
                "last_stopped_at": _utcnow_iso(),
                "updated_at": _utcnow_iso(),
            }
        )
        self._save_session_binding_record(user_id, session_id, payload)
        binding = self.get_session_binding(user_id, session_id)
        self._schedule_runtime_refresh(user_id)
        return binding

    def _deduplicate_running_bindings(
        self, user_id: str, bindings: list[SessionClawBinding]
    ) -> list[SessionClawBinding]:
        """对 running 的 binding 按 chat_id 去重，保留 updated_at 最新的，其余自动 stopped。"""
        by_chat: dict[str, SessionClawBinding] = {}
        duplicates: list[SessionClawBinding] = []

        for binding in bindings:
            if binding.link_status != "running" or not binding.chat_id:
                continue
            key = f"{binding.channel_id or binding.connector_id}:{binding.chat_id}"
            existing = by_chat.get(key)
            if existing is None:
                by_chat[key] = binding
            elif binding.updated_at >= existing.updated_at:
                duplicates.append(existing)
                by_chat[key] = binding
            else:
                duplicates.append(binding)

        for dup in duplicates:
            payload = self._load_session_binding_record(user_id, dup.session_id)
            payload.update(
                {
                    "auto_sync_enabled": False,
                    "link_status": "stopped",
                    "last_stopped_at": _utcnow_iso(),
                    "updated_at": _utcnow_iso(),
                }
            )
            self._save_session_binding_record(user_id, dup.session_id, payload)
            logger.warning(
                "Claw binding 冲突自动停止: user=%s session=%s chat_id=%s (与 session=%s 冲突)",
                user_id,
                dup.session_id,
                dup.chat_id,
                by_chat.get(f"{dup.channel_id or dup.connector_id}:{dup.chat_id}", dup).session_id,
            )

        if duplicates:
            self._schedule_runtime_refresh(user_id)

        return bindings

    def list_channel_bindings(
        self,
        user_id: str,
        channel_id: str,
    ) -> list[ChannelBindingItem]:
        """列出绑定到指定频道的所有会话。"""
        from app.models.claw import ChannelBindingItem

        user_root = self._get_user_root(user_id)
        from ._common import _CLAW_BINDING_FILE

        results: list[ChannelBindingItem] = []
        for path in user_root.glob("*/.aiasys/session/" + _CLAW_BINDING_FILE):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            binding_channel_id = str(raw.get("channel_id") or raw.get("connector_id") or "").strip()
            if binding_channel_id != channel_id:
                continue
            session_id = path.parent.parent.parent.name
            results.append(
                ChannelBindingItem(
                    session_id=session_id,
                    chat_id=str(raw.get("chat_id") or "").strip() or None,
                    chat_label=str(raw.get("chat_label") or "").strip() or None,
                    link_status=str(raw.get("link_status") or "unconfigured"),  # type: ignore[arg-type]
                    last_started_at=str(raw.get("last_started_at") or "").strip() or None,
                    updated_at=str(raw.get("updated_at") or "").strip() or None,
                )
            )
        # 按更新时间倒序
        results.sort(key=lambda x: x.updated_at or "", reverse=True)
        return results

    def expire_idle_bindings(self, user_id: str, idle_timeout_hours: int = 72) -> list[str]:
        """扫描并自动停止超过 idle_timeout_hours 无入站消息的 running binding。

        返回被停止的 session_id 列表。
        """
        from datetime import datetime, timezone

        expired_session_ids: list[str] = []
        user_root = self._get_user_root(user_id)
        from ._common import _CLAW_BINDING_FILE

        cutoff = datetime.now(timezone.utc) - timedelta(hours=idle_timeout_hours)

        for path in user_root.glob("*/.aiasys/session/" + _CLAW_BINDING_FILE):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            if str(raw.get("link_status") or "") != "running":
                continue

            last_inbound_at = str(raw.get("last_inbound_at") or "").strip()
            # 没有 last_inbound_at 记录（从未收到过消息）的 binding，用 last_started_at 判断
            if not last_inbound_at:
                last_started_at = str(raw.get("last_started_at") or "").strip()
                if not last_started_at:
                    continue
                last_inbound_at = last_started_at

            try:
                last_dt = datetime.fromisoformat(last_inbound_at)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

            if last_dt < cutoff:
                session_id = path.parent.parent.parent.name
                payload = {
                    **raw,
                    "auto_sync_enabled": False,
                    "link_status": "stopped",
                    "last_stopped_at": _utcnow_iso(),
                    "updated_at": _utcnow_iso(),
                }
                self._save_session_binding_record(user_id, session_id, payload)
                expired_session_ids.append(session_id)
                logger.info(
                    "Claw binding 自动过期: user=%s session=%s last_inbound_at=%s",
                    user_id,
                    session_id,
                    last_inbound_at,
                )

        if expired_session_ids:
            self._schedule_runtime_refresh(user_id)
        return expired_session_ids
