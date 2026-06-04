"""频道管理 API — YAML 配置驱动的 IM 平台连接管理。"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import require_auth
from app.models.user import UserInfo
from app.services.channel import SUPPORTED_PLATFORMS, ChannelEntry, get_channel_config
from app.services.claw import get_claw_service

router = APIRouter(prefix="/channels", tags=["channels"])


def _resolve_user_id(request_user_id: Optional[str], current_user: UserInfo) -> str:
    if request_user_id:
        if not current_user.can_access_user_data(request_user_id):
            raise HTTPException(status_code=403, detail="无权访问该用户数据")
        return request_user_id
    return current_user.user_id


# ── 频道 CRUD ──


# ── 平台目录 ──


@router.get("/platforms")
async def list_platforms() -> list[dict[str, Any]]:
    """列出支持的平台目录。"""
    platforms = get_claw_service().list_platforms()
    return [
        {
            "platform": item.platform,
            "display_name": item.display_name,
            "description": item.description,
            "support_status": item.support_status,
            "runtime_enabled": item.runtime_enabled,
            "auth_fields": item.auth_fields,
            "supports_qr_login": item.supports_qr_login,
            "supports_inbound": item.supports_inbound,
            "supports_outbound": item.supports_outbound,
            "supports_typing": item.supports_typing,
            "supports_inbound_files": item.supports_inbound_files,
            "supports_outbound_files": item.supports_outbound_files,
            "transport": item.transport,
            "entry_hint": item.entry_hint,
            "default_priority": item.default_priority,
            "notes": item.notes,
        }
        for item in platforms
    ]


@router.get("")
async def list_channels(
    user_id: Optional[str] = Query(None),
    current_user: UserInfo = Depends(require_auth()),
) -> list[dict[str, Any]]:
    """列出所有频道。"""
    resolved_user_id = _resolve_user_id(user_id, current_user)
    cfg = get_channel_config(resolved_user_id)
    return [_channel_to_dict(c) for c in cfg.list_channels()]


@router.post("")
async def create_channel(
    payload: dict[str, Any],
    user_id: Optional[str] = Query(None),
    current_user: UserInfo = Depends(require_auth()),
) -> dict[str, Any]:
    """创建频道。"""
    resolved_user_id = _resolve_user_id(user_id, current_user)
    cfg = get_channel_config(resolved_user_id)

    channel_id = str(payload.get("channel_id", "")).strip()
    if not channel_id:
        raise HTTPException(status_code=400, detail="channel_id 不能为空")
    if cfg.get_channel(channel_id):
        raise HTTPException(status_code=409, detail="频道已存在")

    platform = str(payload.get("platform", "")).strip()
    platform_item = get_claw_service().get_platform_catalog_item(platform)
    if platform_item is None:
        raise HTTPException(status_code=400, detail=f"未知的平台: {platform}")
    if not platform_item.runtime_enabled or platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"平台尚未接入 runtime: {platform}")

    entry = ChannelEntry(
        channel_id=channel_id,
        platform=platform,
        enabled=bool(payload.get("enabled", False)),
        name=str(payload.get("name", "")).strip(),
        account_id=str(payload.get("account_id", "")).strip(),
        token=str(payload.get("token", "")).strip(),
        base_url=str(payload.get("base_url", "")).strip(),
        home_chat_id=str(payload.get("home_chat_id", "")).strip(),
        allowed_users=list(payload.get("allowed_users", [])),
        app_id=str(payload.get("app_id", "")).strip(),
        app_secret=str(payload.get("app_secret", "")).strip(),
    )
    cfg.set_channel(entry)
    get_claw_service()._schedule_runtime_refresh(resolved_user_id)
    return _channel_to_dict(entry)


@router.get("/{channel_id}")
async def get_channel(
    channel_id: str,
    user_id: Optional[str] = Query(None),
    current_user: UserInfo = Depends(require_auth()),
) -> dict[str, Any]:
    """获取单个频道。"""
    resolved_user_id = _resolve_user_id(user_id, current_user)
    cfg = get_channel_config(resolved_user_id)
    entry = cfg.get_channel(channel_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="频道不存在")
    return _channel_to_dict(entry)


@router.patch("/{channel_id}")
async def update_channel(
    channel_id: str,
    payload: dict[str, Any],
    user_id: Optional[str] = Query(None),
    current_user: UserInfo = Depends(require_auth()),
) -> dict[str, Any]:
    """更新频道。"""
    resolved_user_id = _resolve_user_id(user_id, current_user)
    cfg = get_channel_config(resolved_user_id)
    entry = cfg.get_channel(channel_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="频道不存在")

    if "name" in payload:
        entry.name = str(payload["name"]).strip()
    if "account_id" in payload:
        entry.account_id = str(payload["account_id"]).strip()
    if "token" in payload:
        entry.token = str(payload["token"]).strip()
    if "base_url" in payload:
        entry.base_url = str(payload["base_url"]).strip()
    if "home_chat_id" in payload:
        entry.home_chat_id = str(payload["home_chat_id"]).strip()
    if "allowed_users" in payload:
        entry.allowed_users = list(payload["allowed_users"])
    if "app_id" in payload:
        entry.app_id = str(payload["app_id"]).strip()
    if "app_secret" in payload:
        entry.app_secret = str(payload["app_secret"]).strip()

    cfg.set_channel(entry)
    get_claw_service()._schedule_runtime_refresh(resolved_user_id)
    return _channel_to_dict(entry)


@router.patch("/{channel_id}/enabled")
async def set_channel_enabled(
    channel_id: str,
    payload: dict[str, Any],
    user_id: Optional[str] = Query(None),
    current_user: UserInfo = Depends(require_auth()),
) -> dict[str, Any]:
    """启用/禁用频道。"""
    resolved_user_id = _resolve_user_id(user_id, current_user)
    cfg = get_channel_config(resolved_user_id)
    enabled = bool(payload.get("enabled", False))
    if not cfg.set_enabled(channel_id, enabled):
        raise HTTPException(status_code=404, detail="频道不存在")
    entry = cfg.get_channel(channel_id)
    assert entry is not None
    get_claw_service()._schedule_runtime_refresh(resolved_user_id)
    return {"ok": True, "channel_id": channel_id, "enabled": entry.enabled}


@router.delete("/{channel_id}")
async def delete_channel(
    channel_id: str,
    user_id: Optional[str] = Query(None),
    current_user: UserInfo = Depends(require_auth()),
) -> dict[str, Any]:
    """删除频道。"""
    resolved_user_id = _resolve_user_id(user_id, current_user)
    cfg = get_channel_config(resolved_user_id)
    if not cfg.remove_channel(channel_id):
        raise HTTPException(status_code=404, detail="频道不存在")
    get_claw_service().remove_connector_from_all_sessions(resolved_user_id, channel_id)
    get_claw_service()._schedule_runtime_refresh(resolved_user_id)
    return {"ok": True, "channel_id": channel_id}


# ── 辅助函数 ──


def _channel_to_dict(entry: ChannelEntry) -> dict[str, Any]:
    """将 ChannelEntry 转为 API 响应字典。"""
    return {
        "channel_id": entry.channel_id,
        "platform": entry.platform,
        "enabled": entry.enabled,
        "name": entry.name,
        "account_id": entry.account_id,
        "token_masked": _mask_token(entry.token or entry.app_secret),
        "base_url": entry.base_url,
        "home_chat_id": entry.home_chat_id,
        "allowed_users": entry.allowed_users,
        "app_id": entry.app_id,
        "app_secret": _mask_token(entry.app_secret) if entry.app_secret else "",
        "is_configured": entry.is_configured(),
    }


def _mask_token(token: str) -> str:
    """脱敏显示 token。"""
    if not token:
        return ""
    if len(token) <= 8:
        return "***"
    return token[:4] + "***" + token[-4:]
