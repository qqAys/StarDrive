import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.models.user_model import User
from app.services.file_service import (
    can_user_store_bytes,
    create_user_storage_manager,
)
from app.services.user_service import UserManager
from app.security.routes import is_route_unrestricted
from app.ui.pages.console import _build_user_table_row, _modifiable_user_rows
from app.utils.time import utc_now


class FakeUserCRUD:
    users: dict[str, User] = {}

    @classmethod
    async def list(cls, session, offset=0, limit=20, query=None, include_deleted=False):
        users = list(cls.users.values())
        if not include_deleted:
            users = [user for user in users if user.deleted_at is None]
        if query:
            users = [user for user in users if query in user.email]
        return users[offset : offset + limit]

    @classmethod
    async def count(cls, session, query=None, include_deleted=False):
        return len(
            await cls.list(session, query=query, include_deleted=include_deleted)
        )

    @classmethod
    async def get_by_email(cls, session, email, include_deleted=False):
        user = cls.users.get(email)
        if user and user.deleted_at is not None and not include_deleted:
            return None
        return user

    @classmethod
    async def get_by_id(cls, session, user_id, include_deleted=False):
        for user in cls.users.values():
            if user.id == user_id:
                if user.deleted_at is not None and not include_deleted:
                    return None
                return user
        return None

    @classmethod
    async def create(
        cls,
        session,
        *,
        email,
        password,
        is_superuser=False,
        is_active=True,
        quota_bytes=0,
    ):
        user = User(
            id=f"user_{len(cls.users) + 1}",
            email=email,
            password_hash="hash",
            is_superuser=is_superuser,
            is_active=is_active,
            quota_bytes=quota_bytes,
        )
        cls.users[email] = user
        return user

    @classmethod
    async def authenticate(cls, session, *, email, password):
        user = cls.users.get(email)
        if not user or not user.is_active or user.deleted_at is not None:
            return None
        return user

    @classmethod
    async def update_password(cls, session, *, user, new_password, revoke_tokens=True):
        if revoke_tokens:
            user.token_version += 1
        return user

    @classmethod
    async def update_status(cls, session, *, user, is_active):
        user.is_active = is_active
        return user

    @classmethod
    async def update_superuser(cls, session, *, user, is_superuser):
        user.is_superuser = is_superuser
        return user

    @classmethod
    async def update_quota(cls, session, *, user, quota_bytes):
        user.quota_bytes = quota_bytes
        return user

    @classmethod
    async def revoke_sessions(cls, session, *, user):
        user.token_version += 1
        return user

    @classmethod
    async def soft_delete(cls, session, *, user, deleted_at):
        user.deleted_at = deleted_at
        user.is_active = False
        user.token_version += 1
        return user


class FakeDBContext:
    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def fake_db_context():
    return FakeDBContext()


def test_create_user_defaults_to_active_regular_user_quota(mocker):
    async def run_test():
        FakeUserCRUD.users = {}
        mocker.patch(
            "app.services.user_service.AppSettingCRUD.get_value", return_value="1"
        )
        manager = UserManager(user_crud=FakeUserCRUD, db_context=fake_db_context)

        user = await manager.register_user(
            email="new@example.com",
            password="Valid123!",
        )

        assert user.is_active is True
        assert user.is_superuser is False
        assert user.quota_bytes > 0

    asyncio.run(run_test())


def test_registration_can_be_disabled(mocker):
    async def run_test():
        FakeUserCRUD.users = {}
        mocker.patch(
            "app.services.user_service.AppSettingCRUD.get_value", return_value="0"
        )
        manager = UserManager(user_crud=FakeUserCRUD, db_context=fake_db_context)

        with pytest.raises(ValueError, match="Registration"):
            await manager.register_user(
                email="new@example.com",
                password="Valid123!",
            )

    asyncio.run(run_test())


def test_admin_reset_password_revokes_existing_sessions():
    async def run_test():
        FakeUserCRUD.users = {}
        manager = UserManager(user_crud=FakeUserCRUD, db_context=fake_db_context)
        user = await manager.create_user(
            email="user@example.com",
            password="Valid123!",
            quota_bytes=123,
        )

        await manager.admin_reset_password(
            email="user@example.com",
            new_password="Other123!",
        )

        assert user.token_version == 1

    asyncio.run(run_test())


def test_soft_deleted_users_are_hidden_and_cannot_authenticate():
    async def run_test():
        FakeUserCRUD.users = {}
        manager = UserManager(user_crud=FakeUserCRUD, db_context=fake_db_context)
        user = await manager.create_user(
            email="deleted@example.com",
            password="Valid123!",
            quota_bytes=123,
        )

        await manager.soft_delete_user(email="deleted@example.com")

        visible_users, visible_total = await manager.list_users()
        all_users, all_total = await manager.list_users(include_deleted=True)
        authenticated = await FakeUserCRUD.authenticate(
            SimpleNamespace(), email="deleted@example.com", password="Valid123!"
        )

        assert user.deleted_at is not None
        assert user.is_active is False
        assert user.token_version == 1
        assert visible_users == []
        assert visible_total == 0
        assert all_users == [user]
        assert all_total == 1
        assert authenticated is None

    asyncio.run(run_test())


def test_admin_can_revoke_user_sessions_without_changing_password():
    async def run_test():
        FakeUserCRUD.users = {}
        manager = UserManager(user_crud=FakeUserCRUD, db_context=fake_db_context)
        user = await manager.create_user(
            email="session@example.com",
            password="Valid123!",
            quota_bytes=123,
        )

        await manager.revoke_sessions(email="session@example.com")

        assert user.token_version == 1

    asyncio.run(run_test())


def test_console_user_table_row_marks_status_quota_and_deleted_state():
    deleted_at = utc_now()
    user = User(
        id="deleted_user",
        email="deleted@example.com",
        password_hash="hash",
        is_active=False,
        is_superuser=True,
        quota_bytes=0,
        deleted_at=deleted_at,
    )

    row = _build_user_table_row(user, usage=0)

    assert row["id"] == "deleted_user"
    assert row["email"] == "deleted@example.com"
    assert row["is_active"] is False
    assert row["is_superuser"] is True
    assert row["quota_bytes"] == 0
    assert row["is_deleted"] is True
    assert row["deleted"] == deleted_at.strftime("%Y-%m-%d %H:%M:%S")


def test_console_batch_user_rows_skip_deleted_users():
    rows = [
        {"email": "active@example.com", "is_deleted": False},
        {"email": "deleted@example.com", "is_deleted": True},
        {"email": "missing-flag@example.com"},
    ]

    modifiable = _modifiable_user_rows(rows)

    assert modifiable == [rows[0], rows[2]]


def test_user_storage_roots_are_isolated(tmp_path, mocker):
    mocker.patch("app.services.file_service.USER_STORAGE_DIR", tmp_path / "users")

    first = create_user_storage_manager("user_a")
    second = create_user_storage_manager("user_b")

    first.create_directory("docs")
    second.create_directory("docs")
    asyncio.run(first.upload_file(_chunks(b"a"), "docs/same.txt"))
    asyncio.run(second.upload_file(_chunks(b"b"), "docs/same.txt"))

    assert first.get_full_path("docs/same.txt").read_bytes() == b"a"
    assert second.get_full_path("docs/same.txt").read_bytes() == b"b"
    assert first.get_full_path("docs/same.txt") != second.get_full_path("docs/same.txt")


def test_quota_check_uses_user_storage_usage(tmp_path, mocker):
    async def run_test():
        mocker.patch("app.services.file_service.USER_STORAGE_DIR", tmp_path / "users")
        user = User(
            id="quota_user",
            email="quota@example.com",
            password_hash="hash",
            quota_bytes=5,
        )
        manager = create_user_storage_manager(user.id)
        await manager.upload_file(_chunks(b"123"), "used.bin")

        allowed, remaining = await can_user_store_bytes(user, 3)

        assert allowed is False
        assert remaining == 2

    asyncio.run(run_test())


def test_password_reset_token_rejects_expired_token(mocker):
    async def run_test():
        manager = UserManager(user_crud=FakeUserCRUD, db_context=fake_db_context)
        reset_token = SimpleNamespace(
            used_at=None,
            expires_at=utc_now() - timedelta(minutes=1),
            user_id="user_1",
        )
        mocker.patch(
            "app.services.user_service.PasswordResetTokenCRUD.get_by_hash",
            return_value=reset_token,
        )

        with pytest.raises(ValueError, match="expired"):
            await manager.reset_password_with_token(
                token="expired",
                new_password="Valid123!",
            )

    asyncio.run(run_test())


def test_account_self_service_routes_are_public():
    assert is_route_unrestricted("/register/")
    assert is_route_unrestricted("/forgot-password/")
    assert is_route_unrestricted("/reset-password/")


async def _chunks(data: bytes):
    yield data
