"""Persisted, server-side storage backend configuration.

Secrets never enter NiceGUI storage.  They are encrypted in the application DB
and kept in memory only while an OSS backend is active.
"""

import base64
import hashlib
import json
from dataclasses import asdict, dataclass

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # LocalStorage remains bootable before optional deps are synced.
    Fernet = None
    InvalidToken = Exception

from app.config import settings
from app.crud.system_crud import AppSettingCRUD
from app.services.local_db_service import get_db_context

CURRENT_BACKEND_KEY = "storage.current_backend"
OSS_CONFIG_KEY = "storage.oss.config"


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


class StorageConfigService:
    def __init__(self):
        self.current_backend = "LocalStorage"
        self.oss_config: OSSConfig | None = None

    @staticmethod
    def _fernet():
        if Fernet is None:
            raise RuntimeError(
                "Encrypted OSS settings require the 'cryptography' package"
            )
        key = base64.urlsafe_b64encode(
            hashlib.sha256(settings.APP_SECRET.encode()).digest()
        )
        return Fernet(key)

    async def load(self) -> None:
        async with get_db_context() as session:
            self.current_backend = (
                await AppSettingCRUD.get_value(
                    session, CURRENT_BACKEND_KEY, "LocalStorage"
                )
            ) or "LocalStorage"
            raw = await AppSettingCRUD.get_value(session, OSS_CONFIG_KEY)
        self.oss_config = self._decode(raw) if raw else None
        if self.current_backend == "AliyunOSS" and self.oss_config is None:
            self.current_backend = "LocalStorage"

    def _decode(self, raw: str) -> OSSConfig | None:
        try:
            data = json.loads(raw)
            secret = (
                self._fernet().decrypt(data.pop("access_key_secret").encode()).decode()
            )
            return OSSConfig(access_key_secret=secret, **data)
        except (KeyError, TypeError, ValueError, InvalidToken):
            return None

    async def save_oss(self, config: OSSConfig) -> None:
        payload = asdict(config)
        payload["access_key_secret"] = (
            self._fernet().encrypt(config.access_key_secret.encode()).decode()
        )
        async with get_db_context() as session:
            await AppSettingCRUD.set_value(session, OSS_CONFIG_KEY, json.dumps(payload))
        self.oss_config = config

    async def select_backend(self, backend: str) -> None:
        if backend not in {"LocalStorage", "AliyunOSS"}:
            raise ValueError("Unsupported storage backend")
        if backend == "AliyunOSS" and self.oss_config is None:
            raise ValueError("OSS is not configured")
        async with get_db_context() as session:
            await AppSettingCRUD.set_value(session, CURRENT_BACKEND_KEY, backend)
        self.current_backend = backend

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
