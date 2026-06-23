"""Sentry init is optional — must not break dev or tests when DSN is unset."""
from __future__ import annotations

import importlib


def test_init_sentry_noop_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    import services.sentry_config as sentry_config

    importlib.reload(sentry_config)
    assert sentry_config.init_sentry() is False


def test_init_sentry_accepts_dsn(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://examplePublicKey@o0.ingest.sentry.io/0")
    monkeypatch.setenv("ENVIRONMENT", "test")

    import services.sentry_config as sentry_config

    importlib.reload(sentry_config)
    assert sentry_config.init_sentry() is True
