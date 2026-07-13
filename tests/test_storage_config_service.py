import asyncio
from types import SimpleNamespace

import pytest

from app.models.system_model import StorageProfile
from app.services import storage_config_service as module
from app.services.storage_config_service import (
    ALIYUN_OSS,
    LOCAL_STORAGE,
    StorageConfigService,
    StorageProfileDraft,
)
from app.ui.pages.console import (
    _build_storage_profile_table_row,
    _replacement_storage_profile_row,
)
from app.utils.time import utc_now


class FakeDBContext:
    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def fake_db_context():
    return FakeDBContext()


class FakeStorageProfileCRUD:
    profiles: list[StorageProfile] = []

    @classmethod
    async def list(cls, session):
        return sorted(cls.profiles, key=lambda item: (not item.is_active, item.name))

    @classmethod
    async def get(cls, session, profile_id):
        return next((item for item in cls.profiles if item.id == profile_id), None)

    @classmethod
    async def create(
        cls,
        session,
        *,
        name,
        backend_type,
        public_config,
        encrypted_secrets=None,
        is_active=False,
    ):
        profile = StorageProfile(
            name=name,
            backend_type=backend_type,
            public_config=public_config,
            encrypted_secrets=encrypted_secrets or {},
            is_active=is_active,
        )
        cls.profiles.append(profile)
        return profile

    @classmethod
    async def update(
        cls,
        session,
        profile,
        *,
        name,
        public_config,
        encrypted_secrets,
    ):
        profile.name = name
        profile.public_config = public_config
        profile.encrypted_secrets = encrypted_secrets
        return profile

    @classmethod
    async def activate(cls, session, profile):
        for item in cls.profiles:
            item.is_active = item.id == profile.id

    @classmethod
    async def delete(cls, session, profile):
        cls.profiles = [item for item in cls.profiles if item.id != profile.id]

    @classmethod
    async def record_test_result(
        cls,
        session,
        profile,
        *,
        tested_at,
        success,
        message,
    ):
        profile.last_tested_at = tested_at
        profile.last_test_success = success
        profile.last_test_message = message
        return profile


@pytest.fixture(autouse=True)
def fake_storage_profile_crud(mocker):
    FakeStorageProfileCRUD.profiles = []
    mocker.patch.object(module, "StorageProfileCRUD", FakeStorageProfileCRUD)
    mocker.patch.object(module, "get_db_context", fake_db_context)


def test_storage_profile_secret_is_encrypted_and_hidden_from_public_view():
    async def run_test():
        service = StorageConfigService()

        profile = await service.create_or_update_profile(
            StorageProfileDraft(
                name="OSS production",
                backend_type=ALIYUN_OSS,
                public_config={
                    "region": "cn-hangzhou",
                    "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
                    "bucket": "stardrive",
                    "access_key_id": "ak",
                    "prefix": "prod",
                },
                secrets={"access_key_secret": "secret-value"},
            )
        )

        stored = FakeStorageProfileCRUD.profiles[0]

        assert profile.has_secrets is True
        assert stored.encrypted_secrets["access_key_secret"] != "secret-value"
        assert "access_key_secret" not in profile.public_config

    asyncio.run(run_test())


def test_activate_profile_updates_current_backend_and_oss_config():
    async def run_test():
        service = StorageConfigService()
        local = await service.create_or_update_profile(
            StorageProfileDraft(
                name="Local", backend_type=LOCAL_STORAGE, public_config={}
            )
        )
        oss_profile = await service.create_or_update_profile(
            StorageProfileDraft(
                name="OSS",
                backend_type=ALIYUN_OSS,
                public_config={
                    "region": "cn-hangzhou",
                    "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
                    "bucket": "stardrive",
                    "access_key_id": "ak",
                    "prefix": "",
                },
                secrets={"access_key_secret": "secret-value"},
            )
        )

        await service.activate_profile(local.id)
        await service.activate_profile(oss_profile.id)

        assert service.current_backend == ALIYUN_OSS
        assert service.current_profile.id == oss_profile.id
        assert service.oss_config.bucket == "stardrive"
        assert service.oss_config.access_key_secret == "secret-value"

    asyncio.run(run_test())


def test_oss_profile_without_secret_cannot_be_activated():
    async def run_test():
        service = StorageConfigService()
        profile = await service.create_or_update_profile(
            StorageProfileDraft(
                name="Incomplete OSS",
                backend_type=ALIYUN_OSS,
                public_config={
                    "region": "cn-hangzhou",
                    "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
                    "bucket": "stardrive",
                    "access_key_id": "ak",
                    "prefix": "",
                },
            )
        )

        with pytest.raises(ValueError, match="OSS is not configured"):
            await service.activate_profile(profile.id)

    asyncio.run(run_test())


def test_delete_inactive_storage_profile_keeps_current_backend():
    async def run_test():
        service = StorageConfigService()
        local = await service.create_or_update_profile(
            StorageProfileDraft(
                name="Local", backend_type=LOCAL_STORAGE, public_config={}
            )
        )
        oss_profile = await service.create_or_update_profile(
            StorageProfileDraft(
                name="OSS",
                backend_type=ALIYUN_OSS,
                public_config={
                    "region": "cn-hangzhou",
                    "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
                    "bucket": "stardrive",
                    "access_key_id": "ak",
                    "prefix": "",
                },
                secrets={"access_key_secret": "secret-value"},
            )
        )

        await service.activate_profile(local.id)
        await service.delete_profile(oss_profile.id)

        assert [profile.id for profile in FakeStorageProfileCRUD.profiles] == [local.id]
        assert service.current_backend == LOCAL_STORAGE
        assert service.current_profile.id == local.id

    asyncio.run(run_test())


def test_delete_active_storage_profile_switches_to_local_profile():
    async def run_test():
        service = StorageConfigService()
        local = await service.create_or_update_profile(
            StorageProfileDraft(
                name="Local", backend_type=LOCAL_STORAGE, public_config={}
            )
        )
        oss_profile = await service.create_or_update_profile(
            StorageProfileDraft(
                name="OSS",
                backend_type=ALIYUN_OSS,
                public_config={
                    "region": "cn-hangzhou",
                    "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
                    "bucket": "stardrive",
                    "access_key_id": "ak",
                    "prefix": "",
                },
                secrets={"access_key_secret": "secret-value"},
            )
        )

        await service.activate_profile(oss_profile.id)
        replacement = await service.delete_profile(oss_profile.id)

        assert replacement.id == local.id
        assert service.current_backend == LOCAL_STORAGE
        assert service.current_profile.id == local.id
        assert [profile.id for profile in FakeStorageProfileCRUD.profiles] == [local.id]

    asyncio.run(run_test())


def test_delete_only_storage_profile_is_rejected():
    async def run_test():
        service = StorageConfigService()
        profile = await service.create_or_update_profile(
            StorageProfileDraft(
                name="Local", backend_type=LOCAL_STORAGE, public_config={}
            )
        )

        with pytest.raises(ValueError, match="only storage profile"):
            await service.delete_profile(profile.id)

        assert [item.id for item in FakeStorageProfileCRUD.profiles] == [profile.id]

    asyncio.run(run_test())


def test_delete_active_storage_profile_keeps_original_when_replacement_invalid():
    async def run_test():
        service = StorageConfigService()
        active_oss = await service.create_or_update_profile(
            StorageProfileDraft(
                name="Active OSS",
                backend_type=ALIYUN_OSS,
                public_config={
                    "region": "cn-hangzhou",
                    "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
                    "bucket": "stardrive",
                    "access_key_id": "ak",
                    "prefix": "",
                },
                secrets={"access_key_secret": "secret-value"},
            )
        )
        invalid_oss = await service.create_or_update_profile(
            StorageProfileDraft(
                name="Invalid OSS",
                backend_type=ALIYUN_OSS,
                public_config={
                    "region": "cn-hangzhou",
                    "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
                    "bucket": "stardrive",
                    "access_key_id": "ak",
                    "prefix": "",
                },
            )
        )

        await service.activate_profile(active_oss.id)

        with pytest.raises(ValueError, match="OSS is not configured"):
            await service.delete_profile(active_oss.id)

        assert {profile.id for profile in FakeStorageProfileCRUD.profiles} == {
            active_oss.id,
            invalid_oss.id,
        }
        assert next(
            profile
            for profile in FakeStorageProfileCRUD.profiles
            if profile.id == active_oss.id
        ).is_active

    asyncio.run(run_test())


def test_console_storage_profile_row_contains_status_and_public_config():
    tested_at = utc_now()
    profile = module.StorageProfileView(
        id="profile_1",
        name="OSS production",
        backend_type=ALIYUN_OSS,
        is_active=True,
        public_config={"bucket": "stardrive"},
        has_secrets=True,
        last_tested_at=tested_at,
        last_test_success=True,
        last_test_message="ok",
    )

    row = _build_storage_profile_table_row(profile)

    assert row["id"] == "profile_1"
    assert row["active"] == "Yes"
    assert row["is_active"] is True
    assert row["has_secrets"] is True
    assert row["tested"] == tested_at.strftime("%Y-%m-%d %H:%M:%S")
    assert row["result"] == "Passed"
    assert row["last_test_message"] == "ok"
    assert row["public_config"] == {"bucket": "stardrive"}


def test_console_storage_replacement_row_prefers_local_profile():
    rows = [
        {"id": "active", "backend_type": ALIYUN_OSS},
        {"id": "oss", "backend_type": ALIYUN_OSS},
        {"id": "local", "backend_type": LOCAL_STORAGE},
    ]

    replacement = _replacement_storage_profile_row(rows, "active")

    assert replacement == rows[2]


def test_console_storage_replacement_row_falls_back_to_first_candidate():
    rows = [
        {"id": "active", "backend_type": LOCAL_STORAGE},
        {"id": "oss", "backend_type": ALIYUN_OSS},
    ]

    replacement = _replacement_storage_profile_row(rows, "active")

    assert replacement == rows[1]
