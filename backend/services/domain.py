"""DIU email domain enforcement."""
from __future__ import annotations

ALLOWED_DOMAIN = "@diu.edu.bd"


def is_diu_email(email: str | None) -> bool:
    if not email:
        return False
    return email.lower().strip().endswith(ALLOWED_DOMAIN)
