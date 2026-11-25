"""S3 backend shared by explicit construction and persisted administrator profiles."""

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import AsyncIterator

from app.storage.aliyun_oss_storage import AliyunOSSStorage
from app.storage.base import (
    StorageConfigurationError,
    StorageConnectionError,
    StorageError,
    StorageFileNotFoundError,
    StorageIsADirectoryError,
    StoragePermissionError,
)

try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    boto3 = None


@dataclass(frozen=True)
class S3Config:
    endpoint: str
    region: str
    bucket: str
    access_key_id: str = field(repr=False)
    access_key_secret: str = field(repr=False)
    prefix: str = ""


class S3Storage(AliyunOSSStorage):
    """Reuse virtual paths/metadata/list/search, overriding every OSS SDK operation.

    Explicit credentials prevent ambient credential discovery. Blocking requests run
    in worker threads in async entry points. No profile or database format changes.
    """

    name = "S3"
    MULTIPART_PART_SIZE = 8 * 1024 * 1024

    def __init__(self, config: S3Config, user_id: str):
        if boto3 is None:
            raise StorageConfigurationError("S3 support requires boto3")
        if not all(
            (
                config.endpoint,
                config.region,
                config.bucket,
                config.access_key_id,
                config.access_key_secret,
            )
        ):
            raise StorageConfigurationError(
                "S3 endpoint, region, bucket and credentials required"
            )
        from urllib.parse import urlsplit

        endpoint = urlsplit(config.endpoint)
        if (
            endpoint.scheme not in {"http", "https"}
            or not endpoint.hostname
            or endpoint.username
            or endpoint.password
            or endpoint.query
            or endpoint.fragment
        ):
            raise StorageConfigurationError("Invalid S3 endpoint")
        for value in (config.prefix, user_id):
            if "\\" in value or any(p in {".", ".."} for p in value.split("/")):
                raise StorageConfigurationError("Invalid S3 root")
        if not user_id or "/" in user_id:
            raise StorageConfigurationError("Invalid S3 user")
        self.config = config
        self.root_prefix = self._join(config.prefix, "users", user_id)
        self.client = boto3.client(
            "s3",
            endpoint_url=config.endpoint,
            region_name=config.region,
            aws_access_key_id=config.access_key_id,
            aws_secret_access_key=config.access_key_secret,
            config=Config(
                connect_timeout=5,
                read_timeout=30,
                retries={"mode": "standard", "total_max_attempts": 3},
                s3={"addressing_style": "path"},
            ),
        )

    def _relative(self, key):
        if key.rstrip("/") == self.root_prefix:
            return ""
        if not key.startswith(self.root_prefix + "/"):
            raise StoragePermissionError("S3 response outside user root")
        return key[len(self.root_prefix) + 1 :].rstrip("/")

    def _call(self, operation, **kwargs):
        try:
            return getattr(self.client, operation)(Bucket=self.config.bucket, **kwargs)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                raise StorageFileNotFoundError("S3 object not found") from error
            if code in {
                "403",
                "AccessDenied",
                "InvalidAccessKeyId",
                "SignatureDoesNotMatch",
            }:
                raise StoragePermissionError("S3 permission denied") from error
            raise StorageConnectionError("S3 request failed") from error
        except BotoCoreError as error:
            raise StorageConnectionError("S3 connection failed") from error

    def _head(self, key):
        result = self._call("head_object", Key=key)
        return SimpleNamespace(
            content_length=result["ContentLength"],
            last_modified=result.get("LastModified"),
        )

    def _list_pages(self, prefix, delimiter=None):
        token = None
        seen = set()
        while True:
            args = {"Prefix": prefix, "MaxKeys": 1000}
            if delimiter:
                args["Delimiter"] = delimiter
            if token:
                args["ContinuationToken"] = token
            result = self._call("list_objects_v2", **args)
            yield SimpleNamespace(
                contents=[
                    SimpleNamespace(
                        key=o["Key"],
                        size=o["Size"],
                        last_modified=o.get("LastModified"),
                    )
                    for o in result.get("Contents", [])
                ],
                common_prefixes=[o["Prefix"] for o in result.get("CommonPrefixes", [])],
            )
            if not result.get("IsTruncated"):
                return
            token = result.get("NextContinuationToken")
            if not token or token in seen:
                raise StorageConnectionError("S3 pagination did not advance")
            seen.add(token)

    def _is_dir(self, remote_path):
        prefix = self._path(remote_path, True)
        if prefix == self.root_prefix + "/":
            return True
        result = self._call("list_objects_v2", Prefix=prefix, MaxKeys=1)
        return bool(result.get("Contents") or result.get("CommonPrefixes"))

    async def _async_call(self, operation, **kwargs):
        # A cancelled await must not race an in-flight part against ABORT.
        task = asyncio.create_task(asyncio.to_thread(self._call, operation, **kwargs))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                result = await task
            except Exception:
                raise asyncio.CancelledError from None
            if operation == "create_multipart_upload":
                try:
                    await asyncio.to_thread(
                        self._call,
                        "abort_multipart_upload",
                        Key=kwargs["Key"],
                        UploadId=result["UploadId"],
                    )
                except Exception as cleanup:
                    raise StorageError("S3 multipart cleanup unconfirmed") from cleanup
            raise

    async def upload_file(self, file_object: AsyncIterator[bytes], remote_path: str):
        key = self._path(remote_path)
        if self._is_root(remote_path):
            raise StorageIsADirectoryError("Cannot upload to root")
        # Bounded memory: one part plus the incoming producer chunk. Multipart is
        # initiated only after enough data arrives; zero-byte objects use PUT.
        pending = bytearray()
        upload_id = None
        parts = []
        try:
            async for chunk in file_object:
                pending.extend(chunk)
                while len(pending) >= self.MULTIPART_PART_SIZE:
                    if upload_id is None:
                        upload_id = (
                            await self._async_call("create_multipart_upload", Key=key)
                        )["UploadId"]
                    body = bytes(pending[: self.MULTIPART_PART_SIZE])
                    del pending[: self.MULTIPART_PART_SIZE]
                    result = await self._async_call(
                        "upload_part",
                        Key=key,
                        UploadId=upload_id,
                        PartNumber=len(parts) + 1,
                        Body=body,
                    )
                    parts.append({"PartNumber": len(parts) + 1, "ETag": result["ETag"]})
                    if len(parts) >= 10000:
                        raise StorageError("S3 multipart part limit reached")
            if upload_id is None:
                await self._async_call("put_object", Key=key, Body=bytes(pending))
            else:
                if pending:
                    result = await self._async_call(
                        "upload_part",
                        Key=key,
                        UploadId=upload_id,
                        PartNumber=len(parts) + 1,
                        Body=bytes(pending),
                    )
                    parts.append({"PartNumber": len(parts) + 1, "ETag": result["ETag"]})
                await self._async_call(
                    "complete_multipart_upload",
                    Key=key,
                    UploadId=upload_id,
                    MultipartUpload={"Parts": parts},
                )
        except BaseException:
            if upload_id is not None:
                try:
                    await asyncio.shield(
                        asyncio.to_thread(
                            self._call,
                            "abort_multipart_upload",
                            Key=key,
                            UploadId=upload_id,
                        )
                    )
                except Exception as cleanup:
                    raise StorageError(
                        "S3 upload failed; multipart cleanup unconfirmed"
                    ) from cleanup
            raise

    async def get_directory_size(self, remote_path):
        def measure():
            from app.storage.base import StorageNotADirectoryError

            if not self._is_dir(remote_path):
                raise StorageNotADirectoryError(remote_path)
            return sum(
                item.size
                for page in self._list_pages(self._path(remote_path, True))
                for item in page.contents
                if not item.key.endswith("/")
            )

        return await asyncio.to_thread(measure)

    def _is_root(self, path):
        return self._path(path) == self.root_prefix

    def download_file_with_stream(self, remote_path, offset=0, length=None):
        if offset < 0 or (length is not None and length < 0):
            raise ValueError("Invalid byte range")
        if length == 0:
            return
        args = {"Key": self._path(remote_path)}
        if offset or length is not None:
            args["Range"] = f"bytes={offset}-" + (
                str(offset + length - 1) if length is not None else ""
            )
        body = self._call("get_object", **args)["Body"]
        try:
            while chunk := body.read(self.CHUNK_SIZE):
                yield chunk
        except (BotoCoreError, OSError) as error:
            raise StorageConnectionError(
                "S3 stream interrupted; restart download"
            ) from error
        finally:
            body.close()

    def create_directory(self, remote_path):
        if not self._is_root(remote_path):
            self._call("put_object", Key=self._path(remote_path, True), Body=b"")

    def delete_file(self, remote_path):
        if self._is_dir(remote_path):
            raise StorageIsADirectoryError(remote_path)
        key = self._path(remote_path)
        self._head(key)
        self._call("delete_object", Key=key)

    def _delete_keys(self, keys):
        for index in range(0, len(keys), 1000):
            batch = keys[index : index + 1000]
            result = self._call(
                "delete_objects",
                Delete={"Objects": [{"Key": k} for k in batch], "Quiet": False},
            )
            confirmed = {o["Key"] for o in result.get("Deleted", [])}
            if result.get("Errors") or not set(batch).issubset(confirmed):
                raise StorageError(
                    "S3 deletion incomplete; source objects may remain; retain destination copies and inspect before retrying"
                )

    def _copy_key(self, source, destination):
        # CopyObject is limited to 5 GiB. Refuse larger objects before deletion.
        if self._head(source).content_length > 5 * 1024**3:
            raise StorageError("S3 copy above 5 GiB is not supported")
        self._call(
            "copy_object",
            Key=destination,
            CopySource={"Bucket": self.config.bucket, "Key": source},
        )

    def copy_file(self, src_path, dest_path):
        self._copy_key(self._path(src_path), self._path(dest_path))

    def move_file(self, src_path, dest_path):
        source, destination = self._path(src_path), self._path(dest_path)
        # Overlapping trees can map a destination onto a source key that the
        # delete phase would remove. Reject both directions before any copy.
        if (
            self._is_root(src_path)
            or source == destination
            or destination.startswith(source + "/")
            or source.startswith(destination + "/")
        ):
            raise StoragePermissionError("Invalid S3 move destination")
        if self._is_dir(src_path):
            keys = self._keys_under(source + "/")
            for key in keys:
                self._copy_key(key, destination + key[len(source) :])
            self._delete_keys(keys)
        else:
            self._copy_key(source, destination)
            self._delete_keys([source])
