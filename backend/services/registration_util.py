"""Registration validation - DIU email + student ID matching."""
from __future__ import annotations

import re

STUDENT_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")
EMAIL_STUDENT_MISMATCH = "Student ID must match the part before @ in your DIU email."
DIU_EMAIL_REQUIRED = "Use a DIU email (@diu.edu.bd)."
STUDENT_ID_FORMAT_ERROR = (
    "Student ID must use alphanumeric groups separated by hyphens "
    "(for example xxxx-xx-xxx, xxx-xxx-xx, or xxxx-xxxxx-xxxx)."
)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_student_id(student_id: str) -> str:
    return student_id.strip().lower()


def email_local_part(email: str) -> str:
    return email.split("@", 1)[0]


def validate_student_id_format(student_id: str) -> str | None:
    if not STUDENT_ID_PATTERN.fullmatch(student_id):
        return STUDENT_ID_FORMAT_ERROR
    return None


def is_diu_root_email(email: str) -> bool:
    email = normalize_email(email)
    if "@" not in email:
        return False
    local, domain = email.rsplit("@", 1)
    return bool(local) and domain == "diu.edu.bd"


def validate_registration_identity(email: str, student_id: str) -> str | None:
    """Return an error message or None when email + student_id are valid."""
    email = normalize_email(email)
    student_id = normalize_student_id(student_id)

    if not is_diu_root_email(email):
        return DIU_EMAIL_REQUIRED

    sid_err = validate_student_id_format(student_id)
    if sid_err:
        return sid_err

    if email_local_part(email) != student_id:
        return EMAIL_STUDENT_MISMATCH

    return None
