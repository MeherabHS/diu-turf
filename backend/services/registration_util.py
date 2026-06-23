"""Registration validation — DIU email + student ID matching."""
from __future__ import annotations

import re

from services.google_auth import is_diu_email

STUDENT_ID_PATTERN = re.compile(r"^\d{3}-\d{2}-\d{3,4}$")
EMAIL_STUDENT_MISMATCH = "Student ID must match the part before @ in your DIU email."
DIU_EMAIL_REQUIRED = "Use a DIU email (@diu.edu.bd or @*.diu.edu.bd)."


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_student_id(student_id: str) -> str:
    return student_id.strip()


def email_local_part(email: str) -> str:
    return email.split("@", 1)[0]


def validate_student_id_format(student_id: str) -> str | None:
    if not STUDENT_ID_PATTERN.fullmatch(student_id):
        return "Student ID must match xxx-xx-xxx or xxx-xx-xxxx (e.g. 252-35-166)."
    return None


def requires_email_student_id_match(email: str) -> bool:
    """Strict local-part match only for @diu.edu.bd (not department subdomains)."""
    domain = normalize_email(email).split("@", 1)[1]
    return domain == "diu.edu.bd"


def validate_registration_identity(email: str, student_id: str) -> str | None:
    """Return an error message or None when email + student_id are valid."""
    email = normalize_email(email)
    student_id = normalize_student_id(student_id)

    if not is_diu_email(email):
        return DIU_EMAIL_REQUIRED

    sid_err = validate_student_id_format(student_id)
    if sid_err:
        return sid_err

    if requires_email_student_id_match(email) and email_local_part(email) != student_id:
        return EMAIL_STUDENT_MISMATCH

    return None
