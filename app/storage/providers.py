"""Provider configuration and construction; persistence belongs to the service."""

from dataclasses import dataclass
from app.core.paths import STORAGE_DIR

try:
    import alibabacloud_oss_v2 as oss
except ImportError:  # LocalStorage remains usable before OSS dependencies are synced.
    oss = None

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


class StorageProvider:
    def validate(self, draft) -> None:
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

    def public_config(self, draft) -> dict:
        if draft.backend_type == LOCAL_STORAGE:
            return {"root_path": STORAGE_DIR.as_posix()}
        return {
            "region": str(draft.public_config.get("region") or "").strip(),
            "endpoint": str(draft.public_config.get("endpoint") or "").strip(),
            "bucket": str(draft.public_config.get("bucket") or "").strip(),
            "access_key_id": str(
                draft.public_config.get("access_key_id") or ""
            ).strip(),
            "prefix": str(draft.public_config.get("prefix") or "").strip(),
        }

    public_fields = ("region", "endpoint", "bucket", "access_key_id", "prefix")
    secret_fields = ("access_key_secret",)

    def decode(self, config, secrets):
        return OSSConfig(
            **{
                field: (config.get(field) or "").strip() for field in self.public_fields
            },
            access_key_secret=(secrets.get("access_key_secret") or "").strip(),
        )

    def build(self, config, user_id):
        from app.storage.aliyun_oss_storage import AliyunOSSStorage

        return AliyunOSSStorage(config, user_id)

    def connection_test(self, config):
        if oss is None:
            return (
                False,
                "Aliyun OSS support requires the 'alibabacloud-oss-v2' package",
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
            return (False, str(exc))
        return (True, "Storage profile connection verified")


provider = StorageProvider()
