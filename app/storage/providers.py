"""Provider configuration and construction; persistence belongs to the service."""

from dataclasses import dataclass
from app.core.paths import STORAGE_DIR

try:
    import alibabacloud_oss_v2 as oss
except ImportError:  # LocalStorage remains usable before OSS dependencies are synced.
    oss = None

LOCAL_STORAGE = "LocalStorage"
ALIYUN_OSS = "AliyunOSS"
S3 = "S3"
SUPPORTED_BACKENDS = {LOCAL_STORAGE, ALIYUN_OSS, S3}


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


def validate_s3(config):
    from urllib.parse import urlsplit
    import re

    try:
        endpoint = urlsplit(config.endpoint)
        endpoint.port  # Validate numeric port syntax.
        valid = (
            endpoint.scheme in {"http", "https"}
            and endpoint.hostname
            and not endpoint.username
            and not endpoint.password
            and not endpoint.query
            and not endpoint.fragment
            and endpoint.path in {"", "/"}
            and not any(c.isspace() for c in config.endpoint)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Invalid S3 endpoint")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]{0,62}", config.bucket):
        raise ValueError("Invalid S3 bucket")
    if "\\" in config.prefix or any(p in {".", ".."} for p in config.prefix.split("/")):
        raise ValueError("Invalid S3 prefix")
    if not config.region:
        raise ValueError("S3 region is required")


class S3Provider(StorageProvider):
    # Both credential fields are encrypted; neither is returned in public views.
    public_fields = ("region", "endpoint", "bucket", "prefix")
    secret_fields = ("access_key_id", "access_key_secret")

    def decode(self, config, secrets):
        from app.storage.s3_storage import S3Config

        return S3Config(
            **{f: str(config.get(f) or "").strip() for f in self.public_fields},
            **{f: str(secrets.get(f) or "").strip() for f in self.secret_fields},
        )

    def validate(self, draft):
        if not draft.name.strip():
            raise ValueError("Profile name is required")
        validate_s3(self.decode(draft.public_config, draft.secrets or {}))

    def public_config(self, draft):
        return {
            f: str(draft.public_config.get(f) or "").strip() for f in self.public_fields
        }

    def build(self, config, user_id):
        from app.storage.s3_storage import S3Storage

        validate_s3(config)
        storage = S3Storage(config, user_id)
        from urllib.parse import urlsplit

        expected = urlsplit(config.endpoint)

        def check_destination(request, **kwargs):
            actual = urlsplit(request.url)
            if (actual.scheme, actual.hostname, actual.port) != (
                expected.scheme,
                expected.hostname,
                expected.port,
            ):
                raise ValueError("S3 destination changed; redirects are not allowed")

        storage.client.meta.events.register("before-send.s3", check_destination)
        return storage

    def connection_test(self, config):
        from uuid import uuid4

        key = "/".join(
            filter(None, [config.prefix.strip("/"), ".stardrive-probes", uuid4().hex])
        )
        storage = self.build(config, "connection-test")
        payload = b"StarDrive connection probe"
        success = False
        try:
            storage._call("put_object", Key=key, Body=payload, IfNoneMatch="*")
            body = storage._call("get_object", Key=key)["Body"]
            try:
                success = body.read(len(payload) + 1) == payload
            finally:
                body.close()
        except Exception:
            pass
        finally:
            cleanup_failed = False
            try:
                storage._call("delete_object", Key=key)
            except Exception:
                cleanup_failed = True
            finally:
                client = getattr(storage, "client", None)
                if client is not None:
                    client.close()
            if cleanup_failed:
                return (
                    False,
                    "S3 probe cleanup failed; inspect .stardrive-probes before retrying",
                )
        return (
            (True, "Storage profile connection verified")
            if success
            else (
                False,
                "S3 probe failed; check endpoint, credentials and object permissions",
            )
        )


s3_provider = S3Provider()


def get_provider(backend):
    if backend == S3:
        return s3_provider
    if backend in {LOCAL_STORAGE, ALIYUN_OSS}:
        return provider
    raise ValueError("Unsupported storage backend")
