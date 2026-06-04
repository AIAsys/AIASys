import logging

import pytest

from app.core import encryption as encryption_module


def test_resolve_encryption_master_key_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "explicit-secret")
    monkeypatch.setattr(encryption_module, "DEBUG", False)
    monkeypatch.setattr(encryption_module, "AUTH_MODE", "local")

    assert encryption_module.resolve_encryption_master_key() == "explicit-secret"


def test_resolve_encryption_master_key_uses_dev_fallback_in_local_mode(
    monkeypatch,
    caplog,
):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("AIASYS_DEV_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(encryption_module, "DEBUG", False)
    monkeypatch.setattr(encryption_module, "AUTH_MODE", "local")
    monkeypatch.setattr(encryption_module, "_derive_dev_key", lambda: "dev-fallback-key")

    with caplog.at_level(logging.INFO):
        resolved = encryption_module.resolve_encryption_master_key()

    assert resolved == "dev-fallback-key"
    assert "当前处于本地开发模式" in caplog.text


def test_resolve_encryption_master_key_warns_outside_local_mode(
    monkeypatch,
    caplog,
):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("AIASYS_DEV_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(encryption_module, "DEBUG", False)
    monkeypatch.setattr(encryption_module, "AUTH_MODE", "sso")

    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError):
            encryption_module.resolve_encryption_master_key()

    assert "ENCRYPTION_KEY" in caplog.text
