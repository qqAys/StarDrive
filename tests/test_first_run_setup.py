"""Defensive setup regressions using isolated synthetic SQLite data only."""

import asyncio
import shutil
import sqlite3
import secrets
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.crud.user_crud import UserCRUD
from app.models.system_model import AppSetting
from app.models.user_model import User
from app.schemas.user_schema import UserLogin
from app.security.hashing import HashingManager
from app.security.password import generate_random_password
from app.services.local_db_service import migrate_database
from app.services.user_service import INITIAL_SETUP_KEY, UserManager
from app.ui.pages import setup
from app.utils.time import utc_now

# Ephemeral synthetic credentials: never persist deployable test secrets.
TOKEN = secrets.token_urlsafe(32)
PASSWORD = generate_random_password(24)
EMAIL = "owner@example.com"


@pytest.fixture
def installation(tmp_path, monkeypatch):
    path = tmp_path / "setup.db"
    migrate_database(f"sqlite+aiosqlite:///{path}")
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def context():
        async with factory() as session:
            yield session

    manager = UserManager(user_crud=UserCRUD, db_context=context)
    monkeypatch.setattr(settings, "APP_SETUP_TOKEN", SecretStr(TOKEN))
    monkeypatch.setattr(setup.globals, "get_user_manager", lambda: manager)
    yield manager, path, factory
    asyncio.run(engine.dispose())


def credentials(**updates):
    return (
        dict(setup_token=TOKEN, email=EMAIL, password=PASSWORD, confirmation=PASSWORD)
        | updates
    )


def test_empty_installation_blocks_registration_until_setup(installation, monkeypatch):
    manager, _, _ = installation
    monkeypatch.setattr(settings, "APP_ALLOW_REGISTRATION", True)

    async def run():
        await manager.initialize()
        assert not await manager.is_registration_allowed()
        with pytest.raises(ValueError, match="disabled"):
            await manager.register_user(email="member@example.com", password=PASSWORD)
        async with manager.db_context() as session:
            assert await UserCRUD.count(session, include_deleted=True) == 0
            assert await session.get(AppSetting, INITIAL_SETUP_KEY) is None

        await manager.complete_setup(**credentials())
        assert await manager.is_registration_allowed()
        user = await manager.register_user(
            email="member@example.com", password=PASSWORD
        )
        assert user.is_active and not user.is_superuser
        assert user.quota_bytes > 0
        async with manager.db_context() as session:
            assert await UserCRUD.count(session, include_deleted=True) == 2

    asyncio.run(run())


def test_setup_atomic_success_restart_and_legacy_authentication(installation):
    manager, _, _ = installation

    async def run():
        await manager.initialize()
        assert await manager.setup_required()
        await manager.complete_setup(**credentials())
        await manager.initialize()
        assert not await manager.setup_required()
        async with manager.db_context() as session:
            user = await UserCRUD.authenticate(session, email=EMAIL, password=PASSWORD)
            assert user.is_active and user.is_superuser
            assert not user.must_change_password
            assert user.quota_bytes == 0
            assert (await session.get(AppSetting, INITIAL_SETUP_KEY)).value == "1"
        with pytest.raises(ValueError, match="already complete"):
            await manager.complete_setup(**credentials())
        # Completion survives even permanent removal of every account.
        async with manager.db_context() as session:
            await session.execute(delete(User))
            await session.commit()
        await manager.initialize()
        assert not await manager.setup_required()
        with pytest.raises(ValueError, match="already complete"):
            await manager.complete_setup(**credentials())

    asyncio.run(run())


@pytest.mark.parametrize(
    "updates",
    [
        {"setup_token": "incorrect"},
        {"email": "invalid"},
        {"confirmation": "different"},
        {"password": "weak", "confirmation": "weak"},
        {"password": "A1!" + "x" * 70, "confirmation": "A1!" + "x" * 70},
    ],
)
def test_invalid_setup_has_no_persistent_effect(installation, updates):
    manager, _, _ = installation

    async def run():
        with pytest.raises(ValueError):
            await manager.complete_setup(**credentials(**updates))
        async with manager.db_context() as session:
            assert await UserCRUD.count(session, include_deleted=True) == 0
            assert await session.get(AppSetting, INITIAL_SETUP_KEY) is None
        assert await manager.setup_required()

    asyncio.run(run())


@pytest.mark.parametrize("token", [None, SecretStr("short")])
def test_missing_or_short_deployment_credential_fails_closed(
    installation, monkeypatch, token
):
    manager, _, _ = installation
    monkeypatch.setattr(settings, "APP_SETUP_TOKEN", token)

    async def run():
        with pytest.raises(ValueError, match="unavailable"):
            await manager.complete_setup(**credentials())
        with pytest.raises(ValueError, match="disabled"):
            await manager.register_user(email=EMAIL, password=PASSWORD)
        assert await manager.setup_required()

    asyncio.run(run())
    app = FastAPI()
    app.include_router(setup.router)
    with TestClient(app) as client:
        page = client.get(setup.PATH)
        assert "STARDRIVE_APP_SETUP_TOKEN" in page.text
        assert "<form" not in page.text


@pytest.mark.parametrize("state", ["normal", "inactive", "deleted", "pending"])
def test_existing_account_history_never_reopens_setup(installation, state):
    manager, _, _ = installation

    async def run():
        async with manager.db_context() as session:
            user = await UserCRUD.create(
                session,
                email=EMAIL,
                password=PASSWORD,
                is_superuser=True,
                is_active=state != "inactive",
                must_change_password=state == "pending",
            )
            if state == "deleted":
                await UserCRUD.soft_delete(session, user=user, deleted_at=utc_now())
        # Guard works before initialization marks historical installations too.
        assert not await manager.setup_required()
        with pytest.raises(ValueError):
            await manager.complete_setup(**credentials())
        await manager.initialize()
        async with manager.db_context() as session:
            assert await session.get(AppSetting, INITIAL_SETUP_KEY) is not None
            assert await UserCRUD.count(session, include_deleted=True) == 1

    asyncio.run(run())


def test_concurrent_setup_creates_one_admin(installation):
    manager, _, _ = installation

    async def run():
        results = await asyncio.gather(
            manager.complete_setup(**credentials()),
            manager.complete_setup(**credentials(email="second@example.com")),
            return_exceptions=True,
        )
        assert sum(result is None for result in results) == 1
        assert sum(isinstance(result, ValueError) for result in results) == 1
        async with manager.db_context() as session:
            assert await UserCRUD.count(session, include_deleted=True) == 1
            assert await session.get(AppSetting, INITIAL_SETUP_KEY) is not None

    asyncio.run(run())


def test_commit_failure_rolls_back_both_writes_and_can_retry(installation, monkeypatch):
    manager, _, factory = installation

    async def run():
        async with factory() as broken:
            original = broken.commit

            async def fail():
                await broken.flush()
                raise RuntimeError("synthetic commit failure")

            monkeypatch.setattr(broken, "commit", fail)

            @asynccontextmanager
            async def context():
                yield broken

            original_context = manager.db_context
            manager.db_context = context
            with pytest.raises(RuntimeError, match="synthetic"):
                await manager.complete_setup(**credentials())
            monkeypatch.setattr(broken, "commit", original)
            manager.db_context = original_context
        async with manager.db_context() as session:
            assert await UserCRUD.count(session, include_deleted=True) == 0
            assert await session.get(AppSetting, INITIAL_SETUP_KEY) is None
        await manager.complete_setup(**credentials())
        assert not await manager.setup_required()

    asyncio.run(run())


def test_backup_restore_and_previous_schema_compatibility(installation, tmp_path):
    manager, path, _ = installation
    backup = tmp_path / "before.db"
    shutil.copy2(path, backup)
    with sqlite3.connect(backup) as connection:
        original_schema = connection.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()
    asyncio.run(manager.complete_setup(**credentials()))
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(
                "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
            ).fetchall()
            == original_schema
        )

    # Verify the unchanged hash format and login state; this does not execute
    # a previous application binary.
    async def verify():
        async with manager.db_context() as session:
            user = (await session.execute(select(User))).scalar_one()
            assert HashingManager.verify_password(PASSWORD, user.password_hash)
            assert not user.must_change_password

    asyncio.run(verify())
    restored = tmp_path / "restored.db"
    shutil.copy2(backup, restored)
    migrate_database(f"sqlite+aiosqlite:///{restored}")
    with sqlite3.connect(restored) as connection:
        assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 0
        assert (
            connection.execute(
                "SELECT count(*) FROM app_settings WHERE key = ?", (INITIAL_SETUP_KEY,)
            ).fetchone()[0]
            == 0
        )


def form(client):
    import re

    response = client.get(setup.PATH)
    csrf = re.search('name="csrf" value="([^"]+)"', response.text).group(1)
    return credentials() | {"csrf": csrf}


def test_browser_form_success_login_and_no_credential_echo(
    installation, monkeypatch, caplog
):
    manager, _, _ = installation
    app = FastAPI()
    app.include_router(setup.router)
    from app.api.auth import login_api

    monkeypatch.setattr("app.api.auth.get_db_context", manager.db_context)
    with TestClient(app) as client:
        data = form(client)
        assert TOKEN not in data["csrf"]
        response = client.post(
            setup.PATH,
            data=data,
            headers={"origin": "http://testserver"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/login/"
        assert response.headers["cache-control"] == "no-store"
        assert TOKEN not in response.text and PASSWORD not in response.text
        assert client.get(setup.PATH, follow_redirects=False).status_code == 303
        assert client.post(
            setup.PATH, data=data, headers={"origin": "http://testserver"}
        ).status_code in (400, 403)
    assert (asyncio.run(login_api(UserLogin(email=EMAIL, password=PASSWORD)))).data[
        "access_token"
    ]
    assert TOKEN not in caplog.text and PASSWORD not in caplog.text


@pytest.mark.parametrize(
    "rejection",
    [
        "origin",
        "missing-origin",
        "csrf",
        "unicode-csrf",
        "cookie",
        "expired",
        "fetch-site",
        "oversize",
        "duplicate",
    ],
)
def test_browser_form_rejects_invalid_submission(installation, rejection):
    manager, _, _ = installation
    app = FastAPI()
    app.include_router(setup.router)
    with TestClient(app) as client:
        data = form(client)
        headers = {"origin": "http://testserver"}
        if rejection == "origin":
            headers["origin"] = "http://other.invalid"
        elif rejection == "missing-origin":
            headers.clear()
        elif rejection == "csrf":
            data["csrf"] = "invalid"
        elif rejection == "unicode-csrf":
            data["csrf"] = data["csrf"].rsplit(".", 1)[0] + ".无效"
        elif rejection == "cookie":
            client.cookies.clear()
        elif rejection == "expired":
            token = "1." + "a" * 64
            data["csrf"] = token + "." + setup._signature(token)
            client.cookies.set(
                setup.COOKIE, data["csrf"], domain="testserver.local", path=setup.PATH
            )
        elif rejection == "fetch-site":
            headers["sec-fetch-site"] = "cross-site"
        elif rejection == "oversize":
            data["password"] = "x" * 9000
        if rejection == "duplicate":
            from urllib.parse import urlencode

            response = client.post(
                setup.PATH,
                content=urlencode(data) + "&email=extra",
                headers=headers | {"content-type": "application/x-www-form-urlencoded"},
            )
        else:
            response = client.post(setup.PATH, data=data, headers=headers)
        assert response.status_code in (403, 413)
        assert TOKEN not in response.text and PASSWORD not in response.text
    assert asyncio.run(manager.setup_required())


@pytest.mark.parametrize(
    "updates",
    [
        {"setup_token": "wrong"},
        {"email": "not-an-email"},
        {"confirmation": "different"},
        {"password": "weak", "confirmation": "weak"},
    ],
)
def test_browser_validation_failure_leaves_form_retryable(installation, updates):
    manager, _, _ = installation
    app = FastAPI()
    app.include_router(setup.router)
    with TestClient(app) as client:
        data = form(client) | updates
        response = client.post(
            setup.PATH, data=data, headers={"origin": "http://testserver"}
        )
        assert response.status_code == 400
        assert TOKEN not in response.text and PASSWORD not in response.text
        assert asyncio.run(manager.setup_required())
        response = client.post(
            setup.PATH,
            data=form(client),
            headers={"origin": "http://testserver"},
            follow_redirects=False,
        )
        assert response.status_code == 303


def test_browser_database_error_is_generic_and_retryable(installation, monkeypatch):
    manager, _, _ = installation
    from sqlalchemy.exc import SQLAlchemyError

    original = manager.complete_setup

    async def fail(**kwargs):
        raise SQLAlchemyError("synthetic private database diagnostic")

    monkeypatch.setattr(manager, "complete_setup", fail)
    app = FastAPI()
    app.include_router(setup.router)
    with TestClient(app) as client:
        response = client.post(
            setup.PATH, data=form(client), headers={"origin": "http://testserver"}
        )
        assert response.status_code == 503
        assert "private database diagnostic" not in response.text
        assert asyncio.run(manager.setup_required())
        monkeypatch.setattr(manager, "complete_setup", original)
        assert (
            client.post(
                setup.PATH,
                data=form(client),
                headers={"origin": "http://testserver"},
                follow_redirects=False,
            ).status_code
            == 303
        )


@pytest.mark.parametrize("value", ["0", "", "unexpected"])
def test_existing_completion_marker_fails_closed(installation, value):
    manager, _, _ = installation

    async def run():
        async with manager.db_context() as session:
            session.add(AppSetting(key=INITIAL_SETUP_KEY, value=value))
            await session.commit()
        assert not await manager.setup_required()
        with pytest.raises(ValueError, match="already complete"):
            await manager.complete_setup(**credentials())
        async with manager.db_context() as session:
            assert await UserCRUD.count(session, include_deleted=True) == 0
            assert (await session.get(AppSetting, INITIAL_SETUP_KEY)).value == value

    asyncio.run(run())
