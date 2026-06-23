import asyncio

from app.api.health import health_check
from app.config import settings
from app.core.logging import redact_sensitive_data, redact_url


def test_health_endpoint_returns_status_and_version():
    response = asyncio.run(health_check())

    assert response.data == {"status": "ok", "version": settings.APP_VERSION}


def test_sensitive_log_values_and_url_tokens_are_redacted():
    value = {
        "Authorization": "Bearer secret",
        "cookie": "session=secret",
        "nested": {"access_token": "secret"},
    }

    assert redact_sensitive_data(value) == {
        "Authorization": "[redacted]",
        "cookie": "[redacted]",
        "nested": {"access_token": "[redacted]"},
    }
    assert redact_url("https://example.test/share?token=secret&page=2") == (
        "https://example.test/share?token=%5Bredacted%5D&page=2"
    )
    assert redact_url("https://example.test/share/very-secret-jwt") == (
        "https://example.test/share/[redacted]"
    )
    assert redact_url("https://example.test/api/preview-file/very-secret-jwt") == (
        "https://example.test/api/preview-file/[redacted]"
    )
