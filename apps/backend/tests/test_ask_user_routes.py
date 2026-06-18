from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.agents.tools.ask_user.models import AskUserRequest, AskUserStore, AskUserType
from app.api.routes.ask_user import (
    AskUserDevCreateRequest,
    AskUserResolveRequest,
    create_dev_pending_request,
    get_pending_requests,
    resolve_ask_user,
)
from app.api.routes import ask_user as ask_user_routes
from app.models.user import UserInfo


OWNER_USER = UserInfo(user_id="ask-user-owner", role="user", auth_provider="none")
OTHER_USER = UserInfo(user_id="ask-user-other", role="user", auth_provider="none")
ADMIN_USER = UserInfo(user_id="ask-user-admin", role="admin", auth_provider="none")


def _create_pending_request(*, user_id: str, session_id: str) -> tuple[AskUserStore, str]:
    store = AskUserStore()
    request_id = f"req-{uuid.uuid4()}"
    store.create_request(
        request=AskUserRequest(
            request_id=request_id,
            type=AskUserType.CONFIRM,
            title="测试确认",
            message="请确认是否继续",
            timeout=300,
        ),
        session_id=session_id,
        user_id=user_id,
    )
    return store, request_id


@pytest.mark.asyncio
async def test_resolve_ask_user_rejects_other_user() -> None:
    store, request_id = _create_pending_request(
        user_id=OWNER_USER.user_id,
        session_id="session-1",
    )

    try:
        with pytest.raises(HTTPException) as exc_info:
            await resolve_ask_user(
                AskUserResolveRequest(
                    request_id=request_id,
                    approved=True,
                    value="ok",
                ),
                current_user=OTHER_USER,
            )

        assert exc_info.value.status_code == 403
    finally:
        store.remove_request(request_id)


@pytest.mark.asyncio
async def test_resolve_ask_user_accepts_owner() -> None:
    store, request_id = _create_pending_request(
        user_id=OWNER_USER.user_id,
        session_id="session-2",
    )

    try:
        response = await resolve_ask_user(
            AskUserResolveRequest(
                request_id=request_id,
                approved=True,
                value="confirmed",
            ),
            current_user=OWNER_USER,
        )

        assert response.success is True
        pending = store.get_request(request_id)
        assert pending is not None
        assert pending.future.done() is True
        result = pending.future.result()
        assert result.approved is True
        assert result.value == "confirmed"
    finally:
        store.remove_request(request_id)


@pytest.mark.asyncio
async def test_get_pending_requests_defaults_to_current_user() -> None:
    store, owner_request_id = _create_pending_request(
        user_id=OWNER_USER.user_id,
        session_id="session-3",
    )
    _, other_request_id = _create_pending_request(
        user_id=OTHER_USER.user_id,
        session_id="session-4",
    )

    try:
        response = await get_pending_requests(
            session_id=None,
            user_id=None,
            current_user=OWNER_USER,
        )

        assert response["pending_count"] == 1
        assert response["request_ids"] == [owner_request_id]
        assert response["requests"][0]["request"]["request_id"] == owner_request_id
        assert response["requests"][0]["request"]["title"] == "测试确认"

        admin_response = await get_pending_requests(
            session_id=None,
            user_id=None,
            current_user=ADMIN_USER,
        )
        assert set(admin_response["request_ids"]) >= {
            owner_request_id,
            other_request_id,
        }
    finally:
        store.remove_request(owner_request_id)
        store.remove_request(other_request_id)


@pytest.mark.asyncio
async def test_create_dev_pending_request_creates_visible_pending_item() -> None:
    store = AskUserStore()
    response = await create_dev_pending_request(
        AskUserDevCreateRequest(
            session_id="session-dev-route",
            title="浏览器回归测试",
            message="请确认键盘保护是否生效",
            timeout=120,
        ),
        current_user=OWNER_USER,
    )

    request_id = response["request_id"]

    try:
        assert response["success"] is True
        assert response["session_id"] == "session-dev-route"
        assert response["request"]["title"] == "浏览器回归测试"

        pending = store.get_request(request_id)
        assert pending is not None
        assert pending.user_id == OWNER_USER.user_id
        assert pending.session_id == "session-dev-route"
        assert pending.request.title == "浏览器回归测试"
    finally:
        store.remove_request(request_id)


@pytest.mark.asyncio
async def test_create_dev_pending_request_hidden_outside_local_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ask_user_routes, "AUTH_MODE", "sso")

    with pytest.raises(HTTPException) as exc_info:
        await create_dev_pending_request(
            AskUserDevCreateRequest(session_id="session-dev-disabled"),
            current_user=OWNER_USER,
        )

    assert exc_info.value.status_code == 404
