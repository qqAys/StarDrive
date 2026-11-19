"""Persisted pre-provider profiles and SDK-boundary compatibility, without services."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.crud.system_crud import StorageProfileCRUD
from app.models.system_model import StorageProfile
from app.services import storage_config_service as service_module
from app.services import file_service
from app.storage import providers
from app.services.storage_config_service import (
    StorageConfigService,
    StorageProfileDraft,
)

PUBLIC = dict(
    region="synthetic-region",
    endpoint="https://oss.invalid",
    bucket="synthetic",
    access_key_id="synthetic-id",
    prefix="old-prefix",
)


@pytest.mark.parametrize(
    "active_backend", [providers.LOCAL_STORAGE, providers.ALIYUN_OSS]
)
def test_persisted_old_profiles_restart_blank_secret_failure_and_switch(
    tmp_path, monkeypatch, active_backend
):
    async def scenario():
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{tmp_path / 'profiles.sqlite'}"
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        @asynccontextmanager
        async def context():
            async with sessions() as session:
                yield session

        monkeypatch.setattr(service_module, "get_db_context", context)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(
                    lambda conn: SQLModel.metadata.create_all(
                        conn, tables=[StorageProfile.__table__]
                    )
                )
            original = StorageConfigService()
            encrypted = original._encrypt_secrets(
                {"access_key_secret": "synthetic-secret"}
            )
            # Seed the exact persisted shape from before provider extraction, bypassing drafts.
            async with sessions() as session:
                local = StorageProfile(
                    name="Old local",
                    backend_type=providers.LOCAL_STORAGE,
                    public_config={"root_path": str(tmp_path)},
                    is_active=active_backend == providers.LOCAL_STORAGE,
                )
                remote = StorageProfile(
                    name="Old OSS",
                    backend_type=providers.ALIYUN_OSS,
                    public_config=PUBLIC.copy(),
                    encrypted_secrets=encrypted,
                    is_active=active_backend == providers.ALIYUN_OSS,
                )
                invalid = StorageProfile(
                    name="Incomplete",
                    backend_type=providers.ALIYUN_OSS,
                    public_config=PUBLIC.copy(),
                )
                session.add_all([local, remote, invalid])
                await session.commit()
                local_id, remote_id, invalid_id = local.id, remote.id, invalid.id
            await engine.dispose()  # Reopen persisted SQLite rather than reusing ORM identities.
            restarted = StorageConfigService()
            await restarted.load()
            assert restarted.current_backend == active_backend
            await restarted.create_or_update_profile(
                StorageProfileDraft(
                    name="Updated OSS",
                    backend_type=providers.ALIYUN_OSS,
                    public_config=PUBLIC.copy(),
                    secrets={"access_key_secret": ""},
                    profile_id=remote_id,
                )
            )
            async with sessions() as session:
                stored = await StorageProfileCRUD.get(session, remote_id)
                assert stored.encrypted_secrets == encrypted
            before = restarted.current_profile.id
            with pytest.raises(ValueError, match="OSS is not configured"):
                await restarted.activate_profile(invalid_id)
            assert restarted.current_profile.id == before
            again = StorageConfigService()
            await again.load()
            assert again.current_profile.id == before
            await again.activate_profile(remote_id)
            assert again.oss_config.access_key_secret == "synthetic-secret"
            assert again.public_oss_config() == {
                **PUBLIC,
                "has_access_key_secret": True,
            }
            assert all(
                "access_key_secret" not in view.public_config
                for view in await again.list_profiles()
            )
            # Switching back and reopening must preserve actual local download bytes.
            await again.activate_profile(local_id)
            await engine.dispose()
            restored = StorageConfigService()
            await restored.load()
            assert restored.current_profile.id == local_id
            monkeypatch.setattr(file_service, "storage_config", restored)
            monkeypatch.setattr(file_service, "USER_STORAGE_DIR", tmp_path / "users")
            manager = file_service.create_user_storage_manager("owner")
            path = tmp_path / "users" / "owner" / "old.txt"
            path.write_bytes(b"old download bytes")
            assert (
                b"".join(manager.download_file_with_stream("old.txt"))
                == b"old download bytes"
            )
        finally:
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize("outcome", ["success", "failure", "missing"])
def test_provider_connection_sdk_parameters_and_failures(monkeypatch, outcome):
    captured = {}
    config = SimpleNamespace()

    def credentials(key, secret):
        captured["credentials"] = (key, secret)
        return "synthetic-credentials"

    class Client:
        def __init__(self, sdk_config):
            captured["config"] = sdk_config

        def get_bucket_info(self, request):
            captured["bucket"] = request.bucket
            if outcome == "failure":
                raise OSError("synthetic connection failure")

    sdk = SimpleNamespace(
        config=SimpleNamespace(load_default=lambda: config),
        credentials=SimpleNamespace(StaticCredentialsProvider=credentials),
        Client=Client,
        GetBucketInfoRequest=lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(providers, "oss", None if outcome == "missing" else sdk)
    profile = StorageProfile(
        name="Old OSS",
        backend_type=providers.ALIYUN_OSS,
        public_config=PUBLIC.copy(),
        encrypted_secrets=StorageConfigService()._encrypt_secrets(
            {"access_key_secret": "synthetic-secret"}
        ),
    )
    result = asyncio.run(StorageConfigService()._test_profile_model(profile))
    assert result.success == (outcome == "success")
    if outcome == "missing":
        assert "requires" in result.message
        assert not captured
    else:
        assert captured["credentials"] == ("synthetic-id", "synthetic-secret")
        assert config.credentials_provider == "synthetic-credentials"
        assert config.region == PUBLIC["region"]
        assert config.endpoint == PUBLIC["endpoint"]
        assert captured["bucket"] == PUBLIC["bucket"]
        if outcome == "failure":
            assert result.message == "synthetic connection failure"


@pytest.mark.parametrize(
    "changes", [{"name": " "}, {"backend_type": "unknown"}, {"public_config": {}}]
)
def test_provider_rejects_invalid_drafts(changes):
    draft = StorageProfileDraft(
        name="OSS", backend_type=providers.ALIYUN_OSS, public_config=PUBLIC.copy()
    )
    for key, value in changes.items():
        setattr(draft, key, value)
    with pytest.raises(ValueError):
        providers.provider.validate(draft)


def test_provider_build_keeps_user_prefix_and_stream_bytes(monkeypatch):
    from app.storage import aliyun_oss_storage
    from contextlib import contextmanager

    requests = []

    @contextmanager
    def body():
        yield SimpleNamespace(iter_bytes=lambda block_size: iter([b"old OSS bytes"]))

    class Client:
        def __init__(self, config):
            assert config.region == PUBLIC["region"]
            assert config.endpoint == PUBLIC["endpoint"]

        def get_object(self, request):
            requests.append(request)
            return SimpleNamespace(body=body())

    monkeypatch.setattr(aliyun_oss_storage.oss, "Client", Client)
    config = providers.OSSConfig(**PUBLIC, access_key_secret="synthetic-secret")
    owner = providers.provider.build(config, "owner")
    other = providers.provider.build(config, "other")
    assert owner.root_prefix == "old-prefix/users/owner"
    assert other.root_prefix == "old-prefix/users/other"
    assert owner.config is config
    assert b"".join(owner.download_file_with_stream("old.txt")) == b"old OSS bytes"
    assert requests[0].key == "old-prefix/users/owner/old.txt"
    assert requests[0].bucket == PUBLIC["bucket"]
