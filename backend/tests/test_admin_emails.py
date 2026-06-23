"""Tests for admin email role assignment."""
from config.admin_emails import ADMIN_EMAILS, role_for_email


def test_admin_emails_contains_dev_admin():
    assert "261-35-113@diu.edu.bd" in ADMIN_EMAILS


def test_role_for_email_admin():
    assert role_for_email("261-35-113@diu.edu.bd") == "admin"
    assert role_for_email(" 261-35-113@diu.edu.bd ") == "admin"


def test_role_for_email_student():
    assert role_for_email("student@diu.edu.bd") == "viewer"
