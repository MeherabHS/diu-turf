"""Optional Sentry initialization — no-op when SENTRY_DSN is unset (local dev)."""
from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_initialized = False

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return _EMAIL_RE.sub("[email]", value)
    if isinstance(value, dict):
        return {k: _scrub_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_value(v) for v in value]
    return value


def _before_send(event: dict, hint: dict) -> dict | None:
    """Strip email addresses and other PII from outbound events."""
    if "user" in event and isinstance(event["user"], dict):
        user = event["user"]
        event["user"] = {k: v for k, v in user.items() if k in ("id", "ip_address")}

    request = event.get("request")
    if isinstance(request, dict):
        if "headers" in request and isinstance(request["headers"], dict):
            headers = dict(request["headers"])
            for key in ("Authorization", "Cookie", "X-Forwarded-For"):
                headers.pop(key, None)
            request["headers"] = headers
        if "data" in request:
            request["data"] = _scrub_value(request["data"])

    if "breadcrumbs" in event and isinstance(event["breadcrumbs"], list):
        for crumb in event["breadcrumbs"]:
            if isinstance(crumb, dict) and "message" in crumb:
                crumb["message"] = _scrub_value(crumb["message"])

    return event


def init_sentry() -> bool:
    """Initialize Sentry when SENTRY_DSN is set. Safe to call multiple times."""
    global _initialized
    if _initialized:
        return True

    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return False

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    traces_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0") or "0")

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("ENVIRONMENT", "development"),
        release=os.getenv("SENTRY_RELEASE") or None,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            StarletteIntegration(transaction_style="endpoint"),
        ],
        traces_sample_rate=traces_rate,
        send_default_pii=False,
        before_send=_before_send,
    )
    _initialized = True
    logger.info("[SENTRY] initialized (environment=%s)", os.getenv("ENVIRONMENT", "development"))
    return True
