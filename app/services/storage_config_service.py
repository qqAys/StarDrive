"""Persisted, server-side storage backend profiles.

Secrets never enter NiceGUI storage. They are encrypted in the application DB
and kept in memory only while a backend profile is active.
"""

import base64
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # LocalStorage remains bootable before optional deps are synced.
    Fernet = None
    InvalidToken = Exception

try:
    import alibabacloud_oss_v2 as oss
except ImportError:  # LocalStorage remains usable before OSS dependencies are synced.
    oss = None

from app.config import settings
from app.core.paths import STORAGE_DIR
from app.crud.system_crud import AppSettingCRUD, StorageProfileCRUD
from app.models.system_model import StorageProfile
from app.services.local_db_service import get_db_context
from app.utils.time import utc_now

CURRENT_BACKEND_KEY = "storage.current_backend"
OSS_CONFIG_KEY = "storage.oss.config"
LOCAL_STORAGE = "LocalStorage"
ALIYUN_OSS = "AliyunOSS"
SUPPORTED_BACKENDS = {LOCAL_STORAGE, ALIYUN_OSS}


@dataclass(slots=True)
class OSSConfig:
    region: str
    endpoint: str
    bucket: str
    access_key_id: str
    access_key_secret: str
    prefix: str = ""

    def public(self) -> dict[str, str | bool]:
        return {
            "region": self.region,
            "endpoint": self.endpoint,
            "bucket": self.bucket,
            "access_key_id": self.access_key_id,
            "prefix": self.prefix,
            "has_access_key_secret": bool(self.access_key_secret),
        }


@dataclass(slots=True)
class StorageProfileView:
    id: str
    name: str
    backend_type: str
    is_active: bool
    public_config: dict
    has_secrets: bool
    last_tested_at: datetime | None
    last_test_success: bool | None
    last_test_message: str | None


@dataclass(slots=True)
class StorageProfileDraft:
    name: str
    backend_type: str
    public_config: dict
    secrets: dict | None = None
    profile_id: str | None = None


@dataclass(slots=True)
class StorageProfileTestResult:
    success: bool
    message: str


class StorageConfigService:
    def __init__(self):
        self.current_backend = LOCAL_STORAGE
        self.current_profile: StorageProfileView | None = None
        self.oss_config: OSSConfig | None = None

    @staticmethod
    def _fernet():
        if Fernet is None:
            raise RuntimeError(
                "Encrypted storage settings require the 'cryptography' package"
            )
        key = base64.urlsafe_b64encode(
            hashlib.sha256(settings.APP_SECRET.encode()).digest()
        )
        return Fernet(key)

    @staticmethod
    def _local_public_config() -> dict[str, str]:
        return {"root_path": STORAGE_DIR.as_posix()}

    def _encrypt_secrets(self, secrets: dict | None) -> dict[str, str]:
        if not secrets:
            return {}
        fernet = self._fernet()
        return {
            key: fernet.encrypt(str(value).encode()).decode()
            for key, value in secrets.items()
            if value
        }

    def _decrypt_secrets(self, encrypted: dict | None) -> dict[str, str]:
        if not encrypted:
            return {}
        fernet = self._fernet()
        return {
            key: fernet.decrypt(str(value).encode()).decode()
            for key, value in encrypted.items()
            if value
        }

    @staticmethod
    def _profile_view(profile: StorageProfile) -> StorageProfileView:
        return StorageProfileView(
            id=profile.id,
            name=profile.name,
            backend_type=profile.backend_type,
            is_active=profile.is_active,
            public_config=profile.public_config or {},
            has_secrets=bool(profile.encrypted_secrets),
            last_tested_at=profile.last_tested_at,
            last_test_success=profile.last_test_success,
            last_test_message=profile.last_test_message,
        )

    async def load(self) -> None:
        async with get_db_context() as session:
            profiles = await StorageProfileCRUD.list(session)
            if not profiles:
                await self._bootstrap_profiles(session)
                profiles = await StorageProfileCRUD.list(session)

            active = next((profile for profile in profiles if profile.is_active), None)
            if active is None:
                active = profiles[0]
                await StorageProfileCRUD.activate(session, active)
                await session.refresh(active)

        self._set_active_profile(active)

    async def _bootstrap_profiles(self, session) -> None:
        local = await StorageProfileCRUD.create(
            session,
            name="Local storage",
            backend_type=LOCAL_STORAGE,
            public_config=self._local_public_config(),
            is_active=True,
        )

        legacy_backend = (
            await AppSettingCRUD.get_value(session, CURRENT_BACKEND_KEY, LOCAL_STORAGE)
        ) or LOCAL_STORAGE
        legacy_oss_raw = await AppSettingCRUD.get_value(session, OSS_CONFIG_KEY)
        legacy_oss = self._decode_legacy_oss(legacy_oss_raw) if legacy_oss_raw else None
        if legacy_oss:
            oss_profile = await StorageProfileCRUD.create(
                session,
                name="Aliyun OSS",
                backend_type=ALIYUN_OSS,
                public_config={
                    key: value
                    for key, value in legacy_oss.public().items()
                    if key != "has_access_key_secret"
                },
                encrypted_secrets=self._encrypt_secrets(
                    {"access_key_secret": legacy_oss.access_key_secret}
                ),
                is_active=False,
            )
            if legacy_backend == ALIYUN_OSS:
                await StorageProfileCRUD.activate(session, oss_profile)
        elif legacy_backend != ALIYUN_OSS:
            await StorageProfileCRUD.activate(session, local)

    def _decode_legacy_oss(self, raw: str) -> OSSConfig | None:
        try:
            data = json.loads(raw)
            secret = (
                self._fernet().decrypt(data.pop("access_key_secret").encode()).decode()
            )
            return OSSConfig(access_key_secret=secret, **data)
        except (KeyError, TypeError, ValueError, InvalidToken):
            return None

    def _set_active_profile(self, profile: StorageProfile) -> None:
        self.current_profile = self._profile_view(profile)
        self.current_backend = profile.backend_type
        self.oss_config = None
        if profile.backend_type == ALIYUN_OSS:
            self.oss_config = self._oss_config_from_profile(profile)
            if self.oss_config is None:
                self.current_backend = LOCAL_STORAGE

    def _activation_error(self, profile: StorageProfile) -> str | None:
        oss_config = self._oss_config_from_profile(profile)
        if profile.backend_type == ALIYUN_OSS and (
            oss_config is None or not oss_config.access_key_secret
        ):
            return "OSS is not configured"
        return None

    def _oss_config_from_profile(self, profile: StorageProfile) -> OSSConfig | None:
        try:
            config = dict(profile.public_config or {})
            secrets = self._decrypt_secrets(profile.encrypted_secrets)
            return OSSConfig(
                region=(config.get("region") or "").strip(),
                endpoint=(config.get("endpoint") or "").strip(),
                bucket=(config.get("bucket") or "").strip(),
                access_key_id=(config.get("access_key_id") or "").strip(),
                access_key_secret=(secrets.get("access_key_secret") or "").strip(),
                prefix=(config.get("prefix") or "").strip(),
            )
        except (InvalidToken, TypeError, ValueError):
            return None

    async def list_profiles(self) -> list[StorageProfileView]:
        async with get_db_context() as session:
            return [
                self._profile_view(profile)
                for profile in await StorageProfileCRUD.list(session)
            ]

    @staticmethod
    def replacement_profile(
        profiles: list[StorageProfile], deleted_profile_id: str
    ) -> StorageProfile | None:
        candidates = [
            profile for profile in profiles if profile.id != deleted_profile_id
        ]
        local = next(
            (
                profile
                for profile in candidates
                if profile.backend_type == LOCAL_STORAGE
            ),
            None,
        )
        return local or (candidates[0] if candidates else None)

    async def create_or_update_profile(
        self,
        draft: StorageProfileDraft,
    ) -> StorageProfileView:
        self._validate_draft(draft)
        async with get_db_context() as session:
            encrypted_secrets = self._encrypt_secrets(draft.secrets)
            if draft.profile_id:
                profile = await StorageProfileCRUD.get(session, draft.profile_id)
                if not profile:
                    raise ValueError("Storage profile does not exist")
                if not encrypted_secrets:
                    encrypted_secrets = dict(profile.encrypted_secrets or {})
                profile = await StorageProfileCRUD.update(
                    session,
                    profile,
                    name=draft.name.strip(),
                    public_config=self._normalized_public_config(draft),
                    encrypted_secrets=encrypted_secrets,
                )
            else:
                profile = await StorageProfileCRUD.create(
                    session,
                    name=draft.name.strip(),
                    backend_type=draft.backend_type,
                    public_config=self._normalized_public_config(draft),
                    encrypted_secrets=encrypted_secrets,
                )
            if profile.is_active:
                self._set_active_profile(profile)
            return self._profile_view(profile)

    def _validate_draft(self, draft: StorageProfileDraft) -> None:
        if not draft.name.strip():
            raise ValueError("Profile name is required")
        if draft.backend_type not in SUPPORTED_BACKENDS:
            raise ValueError("Unsupported storage backend")
        if draft.backend_type == ALIYUN_OSS:
            public_config = draft.public_config or {}
            required = ("region", "endpoint", "bucket", "access_key_id")
            if any(
                not str(public_config.get(field) or "").strip() for field in required
            ):
                raise ValueError(
                    "OSS region, endpoint, bucket and AccessKey ID are required"
                )

    def _normalized_public_config(self, draft: StorageProfileDraft) -> dict:
        if draft.backend_type == LOCAL_STORAGE:
            return self._local_public_config()
        return {
            "region": str(draft.public_config.get("region") or "").strip(),
            "endpoint": str(draft.public_config.get("endpoint") or "").strip(),
            "bucket": str(draft.public_config.get("bucket") or "").strip(),
            "access_key_id": str(
                draft.public_config.get("access_key_id") or ""
            ).strip(),
            "prefix": str(draft.public_config.get("prefix") or "").strip(),
        }

    async def test_profile(
        self,
        profile_id: str | None = None,
        draft_config: StorageProfileDraft | None = None,
    ) -> StorageProfileTestResult:
        if draft_config:
            result = await self._test_draft(draft_config)
            return result
        if not profile_id:
            raise ValueError("Storage profile id is required")
        async with get_db_context() as session:
            profile = await StorageProfileCRUD.get(session, profile_id)
            if not profile:
                raise ValueError("Storage profile does not exist")
            result = await self._test_profile_model(profile)
            await StorageProfileCRUD.record_test_result(
                session,
                profile,
                tested_at=utc_now(),
                success=result.success,
                message=result.message,
            )
            return result

    async def _test_draft(self, draft: StorageProfileDraft) -> StorageProfileTestResult:
        self._validate_draft(draft)
        if draft.backend_type == LOCAL_STORAGE:
            return StorageProfileTestResult(True, "Local storage is available")
        encrypted = self._encrypt_secrets(draft.secrets)
        if not encrypted and draft.profile_id:
            async with get_db_context() as session:
                profile = await StorageProfileCRUD.get(session, draft.profile_id)
                encrypted = dict(profile.encrypted_secrets or {}) if profile else {}
        profile = StorageProfile(
            name=draft.name,
            backend_type=draft.backend_type,
            public_config=self._normalized_public_config(draft),
            encrypted_secrets=encrypted,
        )
        return await self._test_profile_model(profile)

    async def _test_profile_model(
        self, profile: StorageProfile
    ) -> StorageProfileTestResult:
        if profile.backend_type == LOCAL_STORAGE:
            return StorageProfileTestResult(True, "Local storage is available")
        config = self._oss_config_from_profile(profile)
        if config is None or not config.access_key_secret:
            return StorageProfileTestResult(False, "OSS secret is not configured")
        if oss is None:
            return StorageProfileTestResult(
                False, "Aliyun OSS support requires the 'alibabacloud-oss-v2' package"
            )
        try:
            sdk_config = oss.config.load_default()
            sdk_config.credentials_provider = oss.credentials.StaticCredentialsProvider(
                config.access_key_id, config.access_key_secret
            )
            sdk_config.region = config.region
            sdk_config.endpoint = config.endpoint
            client = oss.Client(sdk_config)
            client.get_bucket_info(oss.GetBucketInfoRequest(bucket=config.bucket))
        except Exception as exc:
            return StorageProfileTestResult(False, str(exc))
        return StorageProfileTestResult(True, "Storage profile connection verified")

    async def activate_profile(self, profile_id: str) -> StorageProfileView:
        async with get_db_context() as session:
            profile = await StorageProfileCRUD.get(session, profile_id)
            if not profile:
                raise ValueError("Storage profile does not exist")
            activation_error = self._activation_error(profile)
            if activation_error:
                raise ValueError(activation_error)
            await StorageProfileCRUD.activate(session, profile)
        self._set_active_profile(profile)
        return self._profile_view(profile)

    async def delete_profile(self, profile_id: str) -> StorageProfileView | None:
        async with get_db_context() as session:
            profiles = await StorageProfileCRUD.list(session)
            profile = next((item for item in profiles if item.id == profile_id), None)
            if not profile:
                raise ValueError("Storage profile does not exist")
            if len(profiles) <= 1:
                raise ValueError("Cannot delete the only storage profile")

            replacement = None
            if profile.is_active:
                replacement = self.replacement_profile(profiles, profile.id)
                if replacement is None:
                    raise ValueError("Cannot delete the only storage profile")
                activation_error = self._activation_error(replacement)
                if activation_error:
                    raise ValueError(activation_error)
                await StorageProfileCRUD.activate(session, replacement)

            await StorageProfileCRUD.delete(session, profile)

        if replacement is not None:
            self._set_active_profile(replacement)
            return self._profile_view(replacement)
        return self.current_profile

    # Backward-compatible helpers used by older call sites and tests.
    async def save_oss(self, config: OSSConfig) -> None:
        profile = await self.create_or_update_profile(
            StorageProfileDraft(
                name="Aliyun OSS",
                backend_type=ALIYUN_OSS,
                public_config={
                    "region": config.region,
                    "endpoint": config.endpoint,
                    "bucket": config.bucket,
                    "access_key_id": config.access_key_id,
                    "prefix": config.prefix,
                },
                secrets={"access_key_secret": config.access_key_secret},
            )
        )
        self.oss_config = config
        if self.current_profile and self.current_profile.id == profile.id:
            self.current_profile = profile

    async def select_backend(self, backend: str) -> None:
        profiles = await self.list_profiles()
        profile = next(
            (item for item in profiles if item.backend_type == backend), None
        )
        if not profile:
            raise ValueError("Storage profile does not exist")
        await self.activate_profile(profile.id)

    def public_oss_config(self) -> dict[str, str | bool]:
        return (
            self.oss_config.public()
            if self.oss_config
            else {
                "region": "",
                "endpoint": "",
                "bucket": "",
                "access_key_id": "",
                "prefix": "",
                "has_access_key_secret": False,
            }
        )


storage_config = StorageConfigService()
