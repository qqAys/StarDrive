"""Opt-in real SMTP contract test. Uses a dedicated recipient configured in CI."""

import os

import pytest

from app.config import settings
from app.services.user_service import UserManager


REQUIRED = (
    "STARDRIVE_TEST_SMTP_HOST",
    "STARDRIVE_TEST_SMTP_PORT",
    "STARDRIVE_TEST_SMTP_SENDER",
    "STARDRIVE_TEST_SMTP_RECIPIENT",
)


@pytest.mark.external
def test_password_reset_email_can_be_sent_via_real_smtp(monkeypatch):
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        pytest.skip("Dedicated SMTP test settings are not configured")

    monkeypatch.setattr(settings, "SMTP_HOST", os.environ["STARDRIVE_TEST_SMTP_HOST"])
    monkeypatch.setattr(
        settings, "SMTP_PORT", int(os.environ["STARDRIVE_TEST_SMTP_PORT"])
    )
    monkeypatch.setattr(
        settings, "SMTP_SENDER", os.environ["STARDRIVE_TEST_SMTP_SENDER"]
    )
    monkeypatch.setattr(
        settings,
        "SMTP_USE_TLS",
        os.environ.get("STARDRIVE_TEST_SMTP_USE_TLS", "true").lower() == "true",
    )
    monkeypatch.setattr(
        settings, "SMTP_USERNAME", os.environ.get("STARDRIVE_TEST_SMTP_USERNAME")
    )
    password = os.environ.get("STARDRIVE_TEST_SMTP_PASSWORD")
    if password:
        from pydantic import SecretStr

        monkeypatch.setattr(settings, "SMTP_PASSWORD", SecretStr(password))

    manager = UserManager(user_crud=None, db_context=None)
    manager._send_password_reset_email(
        os.environ["STARDRIVE_TEST_SMTP_RECIPIENT"],
        "https://example.invalid/reset-password/?token=stardrive-ci-contract-test",
    )
