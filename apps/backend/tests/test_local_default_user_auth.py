from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import Response
from starlette.requests import Request

from app.api.routes import auth as auth_route
from app.core import auth as auth_module
from app.core.database import Base, User
from app.core import database as database_module


def _build_test_session_local(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'local-default-auth.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _build_request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
    }
    return Request(scope)


def _apply_local_default_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module.AUTH_CONFIG, "mode", "local")
    monkeypatch.setattr(auth_module.AUTH_CONFIG, "local_default_user_id", "local_default")
    monkeypatch.setattr(
        auth_module.AUTH_CONFIG,
        "local_default_email",
        "local_default@localhost",
    )
    monkeypatch.setattr(auth_module.AUTH_CONFIG, "local_default_name", "Local Default")
    monkeypatch.setattr(auth_module.AUTH_CONFIG, "local_default_role", "admin")


def test_ensure_local_default_user_exists_creates_and_syncs_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_session_local = _build_test_session_local(tmp_path)
    monkeypatch.setattr(database_module, "SessionLocal", test_session_local)
    _apply_local_default_config(monkeypatch)

    user = auth_module.ensure_local_default_user_exists()
    assert user.id == "local_default"
    assert user.email == "local_default@localhost"
    assert user.name == "Local Default"
    assert user.role == "admin"

    # 第二次调用不应重复创建，但会继续保持与配置一致。
    user_again = auth_module.ensure_local_default_user_exists()
    assert user_again.id == "local_default"

    db = test_session_local()
    try:
        rows = db.query(User).filter(User.id == "local_default").all()
        assert len(rows) == 1
        assert rows[0].role == "admin"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_local_auth_provider_without_token_returns_default_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_session_local = _build_test_session_local(tmp_path)
    monkeypatch.setattr(database_module, "SessionLocal", test_session_local)
    _apply_local_default_config(monkeypatch)

    provider = auth_module.LocalAuthProvider(auth_module.AUTH_CONFIG)
    user = await provider.authenticate(_build_request())

    assert user is not None
    assert user.user_id == "local_default"
    assert user.email == "local_default@localhost"
    assert user.name == "Local Default"
    assert user.role == "admin"


@pytest.mark.asyncio
async def test_local_auth_provider_invalid_token_falls_back_to_default_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_session_local = _build_test_session_local(tmp_path)
    monkeypatch.setattr(database_module, "SessionLocal", test_session_local)
    _apply_local_default_config(monkeypatch)

    provider = auth_module.LocalAuthProvider(auth_module.AUTH_CONFIG)
    request = _build_request(headers=[(b"cookie", b"access_token=broken-token")])
    user = await provider.authenticate(request)

    assert user is not None
    assert user.user_id == "local_default"
    assert user.role == "admin"


@pytest.mark.asyncio
async def test_local_auth_provider_valid_token_is_ignored_in_single_user_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_session_local = _build_test_session_local(tmp_path)
    monkeypatch.setattr(database_module, "SessionLocal", test_session_local)
    _apply_local_default_config(monkeypatch)

    provider = auth_module.LocalAuthProvider(auth_module.AUTH_CONFIG)
    request = _build_request(headers=[(b"cookie", b"access_token=valid-token")])
    user = await provider.authenticate(request)

    assert user is not None
    assert user.user_id == "local_default"
    assert user.email == "local_default@localhost"
    assert user.role == "admin"


def test_local_mode_logout_returns_noop_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_route.AUTH_CONFIG, "mode", "local")
    response = Response()

    import asyncio

    result = asyncio.run(auth_route.logout(response))

    assert result["success"] is True
    assert "无需登出" in result["message"]
