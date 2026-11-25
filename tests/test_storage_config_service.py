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


def test_s3_profile_secret_merge_activation_failure_restart_and_return(mocker):
    from app.storage.providers import S3, s3_provider

    async def scenario():
        service = StorageConfigService()
        local = await service.create_or_update_profile(
            StorageProfileDraft("Local", LOCAL_STORAGE, {})
        )
        await service.activate_profile(local.id)
        config = dict(
            endpoint="http://127.0.0.1:9000",
            region="test",
            bucket="synthetic",
            prefix="测试",
        )
        remote = await service.create_or_update_profile(
            StorageProfileDraft(
                "S3",
                S3,
                {**config, "access_key_id": "must-not-be-public"},
                {
                    "access_key_id": "synthetic-id",
                    "access_key_secret": "synthetic-secret",
                },
            )
        )
        assert "access_key_id" not in remote.public_config
        assert "synthetic-secret" not in repr(remote)
        with pytest.raises(ValueError, match="Test the saved"):
            await service.activate_profile(remote.id)
        assert service.current_profile.id == local.id
        await service.create_or_update_profile(
            StorageProfileDraft(
                "S3", S3, config, {"access_key_secret": "replacement"}, remote.id
            )
        )
        stored = await FakeStorageProfileCRUD.get(None, remote.id)
        secrets = service._decrypt_secrets(stored.encrypted_secrets)
        assert secrets == {
            "access_key_id": "synthetic-id",
            "access_key_secret": "replacement",
        }
        check = mocker.patch.object(
            s3_provider, "connection_test", return_value=(False, "S3 probe failed")
        )
        assert not (await service.test_profile(remote.id)).success
        with pytest.raises(ValueError):
            await service.activate_profile(remote.id)
        assert service.current_profile.id == local.id
        check.return_value = (True, "Storage profile connection verified")
        assert (await service.test_profile(remote.id)).success
        await service.activate_profile(remote.id)
        with pytest.raises(ValueError, match="Switch to another"):
            await service.create_or_update_profile(
                StorageProfileDraft("S3", S3, config, {}, remote.id)
            )
        restarted = StorageConfigService()
        await restarted.load()
        assert restarted.current_backend == S3
        assert restarted.oss_config.access_key_id == "synthetic-id"
        await restarted.activate_profile(local.id)
        assert restarted.current_backend == LOCAL_STORAGE
        await restarted.create_or_update_profile(
            StorageProfileDraft("S3", S3, config, {}, remote.id)
        )
        with pytest.raises(ValueError, match="Test the saved"):
            await restarted.activate_profile(remote.id)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "endpoint",
    [
        "file:///tmp",
        "http://user:pass@host",
        "https://host/path",
        "https://host?token=secret",
        "https://host:bad",
        "https://host/#fragment",
    ],
)
def test_s3_rejects_endpoint_before_network(endpoint):
    from app.storage.providers import s3_provider

    with pytest.raises(ValueError, match="Invalid S3 endpoint"):
        s3_provider.validate(
            StorageProfileDraft(
                "S3", "S3", dict(endpoint=endpoint, region="test", bucket="synthetic")
            )
        )


@pytest.mark.parametrize("failure", [None, "put_object", "get_object", "delete_object"])
def test_s3_probe_unique_cleanup_and_sanitized_errors(mocker, failure):
    import io
    from app.storage.providers import s3_provider

    calls = []

    def call(operation, **kwargs):
        calls.append((operation, kwargs))
        if operation == failure:
            raise RuntimeError("synthetic-credential-do-not-display")
        return {"Body": io.BytesIO(b"StarDrive connection probe")}

    mocker.patch.object(s3_provider, "build", return_value=SimpleNamespace(_call=call))
    config = s3_provider.decode(
        dict(
            endpoint="http://localhost:9000",
            region="test",
            bucket="synthetic",
            prefix="prefix",
        ),
        {},
    )
    first = s3_provider.connection_test(config)
    second = s3_provider.connection_test(config)
    assert first[0] == (failure is None)
    assert "synthetic-credential" not in first[1]
    assert calls[0][1]["Key"].startswith("prefix/.stardrive-probes/")
    assert calls[0][1]["IfNoneMatch"] == "*"
    deletes = [args["Key"] for operation, args in calls if operation == "delete_object"]
    assert len(deletes) == 2 and len(set(deletes)) == 2
    if failure == "delete_object":
        assert "cleanup failed" in first[1]


def test_s3_rejects_redirect_destination_before_sending(mocker):
    from app.storage.providers import s3_provider
    from app.storage import s3_storage

    events = SimpleNamespace(register=mocker.Mock())
    mocker.patch.object(
        s3_storage,
        "S3Storage",
        return_value=SimpleNamespace(
            client=SimpleNamespace(meta=SimpleNamespace(events=events))
        ),
    )
    config = s3_provider.decode(
        dict(endpoint="http://127.0.0.1:9000", region="test", bucket="synthetic"), {}
    )
    s3_provider.build(config, "user")
    name, guard = events.register.call_args.args
    assert name == "before-send.s3"
    guard(SimpleNamespace(url="http://127.0.0.1:9000/synthetic/key"))
    for url in [
        "http://other.invalid:9000/synthetic/key",
        "https://127.0.0.1:9000/key",
        "http://127.0.0.1:8000/key",
    ]:
        with pytest.raises(ValueError, match="destination changed"):
            guard(SimpleNamespace(url=url))


def test_storage_callback_guard_rechecks_current_admin(monkeypatch):
    from app.security import guards

    calls = []
    user = SimpleNamespace(is_active=True, is_superuser=False)

    async def current_user():
        return user

    monkeypatch.setattr(
        guards,
        "app",
        SimpleNamespace(storage=SimpleNamespace(user={"signed-in": True})),
    )
    monkeypatch.setattr(
        guards.globals,
        "get_user_manager",
        lambda: SimpleNamespace(current_user=current_user),
    )
    monkeypatch.setattr(guards.notify, "error", lambda message: None)
    monkeypatch.setattr(guards, "navigate_to", lambda *args: None)

    @guards.require_user(superuser=True)
    async def callback():
        calls.append("executed")

    async def scenario():
        await callback()
        assert calls == []
        user.is_superuser = True
        await callback()
        assert calls == ["executed"]
        user.is_active = False
        await callback()
        assert calls == ["executed"]

    asyncio.run(scenario())


@pytest.mark.parametrize("cancel_probe", [False, True])
def test_concurrent_s3_test_edit_cannot_certify_changed_profile(
    monkeypatch, cancel_probe
):
    """Two clients share the service lock even if the testing page is cancelled."""
    import threading
    from app.storage.providers import S3, s3_provider

    async def scenario():
        service = StorageConfigService()
        public = dict(
            endpoint="http://127.0.0.1:9000", region="test", bucket="synthetic"
        )
        remote = await service.create_or_update_profile(
            StorageProfileDraft(
                "S3",
                S3,
                public,
                {
                    "access_key_id": "synthetic-id",
                    "access_key_secret": "synthetic-secret",
                },
            )
        )
        entered, release = threading.Event(), threading.Event()
        cleaned = threading.Event()
        configs = []

        def probe(config):
            configs.append(config)
            entered.set()
            try:
                assert release.wait(3), "test did not release synthetic probe"
                return True, "verified"
            finally:
                cleaned.set()

        monkeypatch.setattr(s3_provider, "connection_test", probe)
        testing = asyncio.create_task(service.test_profile(remote.id))
        editing = None
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            if cancel_probe:
                testing.cancel()
                await asyncio.sleep(0)
            editing = asyncio.create_task(
                service.create_or_update_profile(
                    StorageProfileDraft(
                        "Changed",
                        S3,
                        {**public, "prefix": "changed"},
                        {},
                        remote.id,
                    )
                )
            )
            await asyncio.sleep(0)
            assert not editing.done()
            assert not cleaned.is_set()
            release.set()
            if cancel_probe:
                with pytest.raises(asyncio.CancelledError):
                    await testing
            else:
                assert (await testing).success
            await editing
            assert cleaned.is_set()
            assert configs[0].prefix == ""
            saved = (await service.list_profiles())[0]
            assert saved.public_config["prefix"] == "changed"
            assert saved.last_test_success is None
            with pytest.raises(ValueError, match="Test the saved"):
                await service.activate_profile(remote.id)
            # A reconnect reads persistent state and explicitly retests the new config.
            assert (await service.test_profile(remote.id)).success
            await service.activate_profile(remote.id)
            assert service.oss_config.prefix == "changed"
        finally:
            release.set()
            await asyncio.gather(
                testing, *([editing] if editing else []), return_exceptions=True
            )

    asyncio.run(scenario())
