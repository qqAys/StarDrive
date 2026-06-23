import os

import pytest
from pydantic import ValidationError

os.environ.setdefault("STARDRIVE_APP_SECRET", "test-secret")

from app.config import Config
from app.core.version import app_version


def test_app_version_comes_from_package_metadata(monkeypatch):
    monkeypatch.setenv("STARDRIVE_APP_VERSION", "not-a-real-release")

    assert Config().APP_VERSION == app_version() == "2026.6.23"


def test_app_secret_accepts_legacy_unprefixed_environment_variable(monkeypatch):
    monkeypatch.delenv("STARDRIVE_APP_SECRET", raising=False)
    monkeypatch.setenv("APP_SECRET", "legacy-local-secret")

    assert Config(_env_file=None).APP_SECRET == "legacy-local-secret"


def test_app_secret_is_required_when_no_environment_or_env_file_is_available(
    monkeypatch,
):
    monkeypatch.delenv("STARDRIVE_APP_SECRET", raising=False)
    monkeypatch.delenv("APP_SECRET", raising=False)

    with pytest.raises(ValidationError, match="APP_SECRET"):
        Config(_env_file=None)
