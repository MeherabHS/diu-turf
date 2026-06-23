"""Google ID token verification — Phase 4.

Uses Google's tokeninfo endpoint for async, library-free verification.
Google's servers handle RS256 signature verification, expiry, and issuer
checks before returning a response.

Security properties guaranteed by this endpoint:
  - Token was signed by Google (signature verified server-side by Google)
  - Token has not expired (exp claim checked by Google)
  - Token was issued by accounts.google.com (iss verified by Google)
  - We additionally verify: aud (our client ID), email_verified, domain

Production upgrade path:
  Replace the tokeninfo HTTP call with offline JWT verification using the
  'google-auth' Python library (pip install google-auth).  That avoids the
  external call on every login at the cost of fetching Google's public JWKS
  once per key rotation (~hours).  See:
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport.requests import Request as GoogleRequest
"""
from __future__ import annotations

import logging
import os
from typing import TypedDict

import httpx

log = logging.getLogger(__name__)

# Google tokeninfo endpoint — verifies signature, expiry, and issuer.
_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
_VALID_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})

# DIU domain restriction — authoritative check happens here, not on the frontend.
ALLOWED_DOMAIN = "@diu.edu.bd"


class GoogleClaims(TypedDict):
    sub: str            # Google account unique ID (stable, never changes)
    email: str          # Lowercase, verified by Google
    name: str           # Display name from Google profile
    picture: str | None # Profile photo URL (may be None)


def _get_allowed_client_ids() -> list[str]:
    """Return non-empty client IDs from environment."""
    return [
        cid for cid in (
            os.getenv("GOOGLE_CLIENT_ID_WEB"),
            os.getenv("GOOGLE_CLIENT_ID_ANDROID"),
            os.getenv("GOOGLE_CLIENT_ID_IOS"),
        )
        if cid
    ]


async def verify_google_id_token(token: str) -> GoogleClaims:
    """Verify a Google ID token and return safe, verified claims.

    Raises ValueError with a safe (non-leaking) message on any failure.
    Never raises HTTPException — callers do that conversion.

    Steps performed:
      1. Call Google's tokeninfo endpoint (signature + expiry + issuer verified by Google).
      2. Check aud claim against configured client IDs.
      3. Check iss claim is a known Google issuer.
      4. Confirm email_verified == true.
      5. Extract and return sub, email, name, picture.
    """
    if not token or len(token) < 20:
        raise ValueError("Malformed ID token")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(_TOKENINFO_URL, params={"id_token": token})
        except httpx.HTTPError as exc:
            log.warning("Google tokeninfo request failed: %s", exc)
            raise ValueError("Could not reach Google verification service") from exc

    if resp.status_code != 200:
        # Don't leak Google's raw error body — just a safe message.
        raise ValueError("Invalid or expired Google ID token")

    data = resp.json()

    iss = data.get("iss", "")
    aud = data.get("aud", "")
    email_verified = data.get("email_verified")
    log.info(
        "[GOOGLE_AUTH] tokeninfo ok iss=%s aud=%s email_verified=%s",
        iss,
        aud[:24] + "..." if len(str(aud)) > 24 else aud,
        email_verified,
    )

    # ── Issuer verification ───────────────────────────────────────────────────
    iss = data.get("iss", "")
    if iss not in _VALID_ISSUERS:
        raise ValueError("Unexpected token issuer")

    # ── Email verification (before audience — clearer errors) ─────────────────
    if not data.get("email_verified"):
        raise ValueError("Google account email is not verified")

    email = (data.get("email") or "").lower().strip()
    if not email:
        raise ValueError("Token is missing the email claim")

    # ── Audience verification ─────────────────────────────────────────────────
    allowed = _get_allowed_client_ids()
    if allowed:
        if aud not in allowed:
            log.warning("[GOOGLE_AUTH] token aud '%s' not in configured client IDs", aud)
            raise ValueError("Token audience does not match this application")
    else:
        log.warning("[GOOGLE_AUTH] no GOOGLE_CLIENT_ID_* configured — skipping aud check")

    sub = data.get("sub", "")
    if not sub:
        raise ValueError("Token is missing the sub claim")

    return GoogleClaims(
        sub=sub,
        email=email,
        name=(data.get("name") or "").strip() or email.split("@")[0],
        picture=data.get("picture") or None,
    )


def is_diu_email(email: str) -> bool:
    """Return True if the email belongs to DIU (@diu.edu.bd or @*.diu.edu.bd)."""
    email = email.strip().lower()
    if "@" not in email:
        return False
    domain = email.split("@", 1)[1]
    return domain == "diu.edu.bd" or domain.endswith(".diu.edu.bd")
