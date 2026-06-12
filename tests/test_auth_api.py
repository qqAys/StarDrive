from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.api.auth import login_api
from app.core.exceptions import BusinessException
from app.schemas.user_schema import UserLogin


@asynccontextmanager
async def fake_db_context():
    yield object()


def test_login_api_rejects_invalid_credentials(mocker):
    mocker.patch("app.api.auth.get_db_context", return_value=fake_db_context())
    authenticate = mocker.patch("app.api.auth.UserCRUD.authenticate")
    authenticate.return_value = None

    with pytest.raises(BusinessException) as exc_info:
        import asyncio

        asyncio.run(
            login_api(UserLogin(email="missing@example.com", password="wrong-password"))
        )

    assert exc_info.value.code == 2001
    assert exc_info.value.http_status == 401
    authenticate.assert_awaited_once()


def test_login_api_returns_tokens_for_valid_credentials(mocker):
    mocker.patch("app.api.auth.get_db_context", return_value=fake_db_context())
    authenticate = mocker.patch("app.api.auth.UserCRUD.authenticate")
    authenticate.return_value = SimpleNamespace(id="user_123", token_version=3)
    mocker.patch("app.api.auth.create_access_token", return_value="access-token")
    mocker.patch("app.api.auth.create_refresh_token", return_value="refresh-token")

    import asyncio

    response = asyncio.run(
        login_api(UserLogin(email="admin@example.com", password="correct-password"))
    )

    assert response.code == 0
    assert response.data == {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "expires_in": 900,
    }
    authenticate.assert_awaited_once()
