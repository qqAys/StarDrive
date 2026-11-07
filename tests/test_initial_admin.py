import asyncio
from contextlib import asynccontextmanager, nullcontext
from io import StringIO
from types import SimpleNamespace

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.auth import login_api
from app.core.exceptions import BusinessException
from app.crud.user_crud import PasswordResetTokenCRUD, UserCRUD
from app.models.system_model import PasswordResetToken
from app.recover_initial_admin import recover_initial_admin
from app.schemas.user_schema import UserLogin, UserModifyPassword
from app.security.hashing import HashingManager
from app.services.local_db_service import _alembic_config, migrate_database
from app.services.user_service import UserManager
from app.utils.time import utc_now

ADMIN_EMAIL = "initial-admin@example.com"
REPLACEMENT_PASSWORD = "Replacement-123!"


@pytest.fixture
def isolated_users(tmp_path, mocker):
    path = tmp_path / "local.db"
    dsn = f"sqlite+aiosqlite:///{path}"
    engine = create_async_engine(dsn)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def db_context():
        async with session_factory() as session:
            yield session

    storage = {}
    mocker.patch(
        "app.services.user_service.app",
        SimpleNamespace(storage=SimpleNamespace(user=storage)),
    )
    mocker.patch(
        "app.services.user_service.get_user_timezone_from_browser", return_value="UTC"
    )
    mocker.patch("app.api.auth.get_db_context", db_context)
    mocker.patch("app.services.user_service.settings.APP_INIT_USER", ADMIN_EMAIL)
    yield UserManager(user_crud=UserCRUD, db_context=db_context), path, storage
    asyncio.run(engine.dispose())


@pytest.fixture
def credential_terminal(mocker):
    terminal = StringIO()
    mocker.patch(
        "app.services.user_service.open_password_terminal",
        return_value=nullcontext(terminal),
    )
    return terminal


def consume_temporary_password(terminal):
    lines = terminal.getvalue().splitlines()
    terminal.seek(0)
    terminal.truncate()
    prefix = f"Initial administrator: {ADMIN_EMAIL}. Temporary password: "
    if len(lines) != 1 or not lines[0].startswith(prefix):
        pytest.fail(
            "Expected one-time credential on the private terminal.", pytrace=False
        )
    return lines[0].removeprefix(prefix)


def test_first_login_requires_password_change(
    isolated_users, credential_terminal, capsys, caplog
):
    manager, path, storage = isolated_users
    dsn = f"sqlite+aiosqlite:///{path}"
    migrate_database(dsn)

    async def run():
        await manager.initialize()
        temporary = consume_temporary_password(credential_terminal)
        captured = capsys.readouterr()
        if (
            len(temporary) != 24
            or temporary in caplog.text + captured.out + captured.err
        ):
            pytest.fail(
                "Invalid initial credential or leaked application log.", pytrace=False
            )
        login = UserLogin(email=ADMIN_EMAIL, password=temporary)

        migrate_database(dsn)
        await manager.initialize()
        assert not credential_terminal.getvalue()
        with pytest.raises(BusinessException) as rejected:
            await login_api(login)
        assert rejected.value.http_status == 403

        user = await manager.login(login)
        assert user.must_change_password
        assert await manager.current_user() is None
        assert "access_token" not in storage
        assert await manager.initial_password_email() == ADMIN_EMAIL
        old_pending_session = storage.copy()
        await manager.logout()
        assert await manager.initial_password_email() is None
        await manager.login(login)

        for current, replacement in (
            ("incorrect", REPLACEMENT_PASSWORD),
            (temporary, temporary),
        ):
            with pytest.raises(ValueError):
                await manager.complete_initial_password_change(
                    UserModifyPassword(
                        current_password=current, new_password=replacement
                    )
                )
        await manager.complete_initial_password_change(
            UserModifyPassword(
                current_password=temporary, new_password=REPLACEMENT_PASSWORD
            )
        )
        assert not storage

        storage.update(old_pending_session)
        assert await manager.initial_password_email() is None
        assert not storage
        with pytest.raises(BusinessException) as old_login:
            await login_api(login)
        assert old_login.value.http_status == 401
        new_login = UserLogin(email=ADMIN_EMAIL, password=REPLACEMENT_PASSWORD)
        updated = await manager.login(new_login)
        assert updated.token_version == user.token_version + 1
        assert (await manager.current_user()).id == user.id
        assert (await login_api(new_login)).data["access_token"]

    asyncio.run(run())


def test_headless_startup_only_logs_recovery_hint(
    isolated_users, mocker, capsys, caplog
):
    manager, path, _ = isolated_users
    migrate_database(f"sqlite+aiosqlite:///{path}")
    temporary = "Sample-only-boot123!"
    mocker.patch(
        "app.services.user_service.generate_random_password", return_value=temporary
    )
    mocker.patch(
        "app.services.user_service.open_password_terminal", side_effect=OSError
    )

    asyncio.run(manager.initialize())
    captured = capsys.readouterr()
    if temporary in captured.out + captured.err + caplog.text:
        pytest.fail("Headless startup leaked a credential.", pytrace=False)
    assert "Use local administrator recovery." in caplog.text

    with pytest.raises(BusinessException) as rejected:
        asyncio.run(login_api(UserLogin(email=ADMIN_EMAIL, password=temporary)))
    assert rejected.value.http_status == 403


def test_old_database_login_and_offline_recovery(
    isolated_users, credential_terminal, mocker
):
    manager, path, storage = isolated_users
    dsn = f"sqlite+aiosqlite:///{path}"
    sync_engine = create_engine(f"sqlite:///{path}")
    try:
        with sync_engine.begin() as connection:
            config = _alembic_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "0002_console_storage_profiles")
            # The baseline migration uses live metadata. Restore the original v2 shape.
            connection.exec_driver_sql(
                "ALTER TABLE users DROP COLUMN must_change_password"
            )
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, email, is_active, is_superuser, token_version, quota_bytes, password_hash) "
                    "VALUES ('existing-admin', :email, 1, 1, 3, 0, :password_hash)"
                ),
                {
                    "email": ADMIN_EMAIL,
                    "password_hash": HashingManager.hash_password(REPLACEMENT_PASSWORD),
                },
            )
    finally:
        sync_engine.dispose()

    mocker.patch("app.recover_initial_admin.settings.LOCAL_DB_DSN", dsn)
    mocker.patch("app.recover_initial_admin.get_db_context", manager.db_context)
    mocker.patch(
        "app.recover_initial_admin.init_local_db",
        side_effect=lambda: migrate_database(dsn),
    )
    mocker.patch("app.recover_initial_admin.close_local_db")

    migrate_database(dsn)

    async def run():
        await manager.initialize()
        assert not credential_terminal.getvalue()
        login = UserLogin(email=ADMIN_EMAIL, password=REPLACEMENT_PASSWORD)
        user = await manager.login(login)
        assert not user.must_change_password
        assert user.token_version == 3
        async with manager.db_context() as session:
            reset = await PasswordResetTokenCRUD.create(
                session,
                user_id=user.id,
                token_hash="existing-reset",
                expires_at=utc_now(),
            )
            reset_id = reset.id

        await recover_initial_admin(credential_terminal)
        temporary = consume_temporary_password(credential_terminal)
        assert await manager.current_user() is None
        assert not storage
        with pytest.raises(BusinessException) as old_login:
            await login_api(login)
        assert old_login.value.http_status == 401
        async with manager.db_context() as session:
            assert await session.get(PasswordResetToken, reset_id) is None

        pending = await manager.login(UserLogin(email=ADMIN_EMAIL, password=temporary))
        assert pending.must_change_password
        assert pending.token_version == 4

    asyncio.run(run())
