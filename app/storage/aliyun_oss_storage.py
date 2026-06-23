"""Aliyun OSS storage backend implemented with OSS Python SDK V2."""

import asyncio
import os
import tempfile
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import AsyncIterator, Iterator

try:
    import alibabacloud_oss_v2 as oss
except ImportError:  # LocalStorage remains usable before dependencies are synced.
    oss = None

from app.schemas.file_schema import DirMetadata, FileMetadata
from app.services.storage_config_service import OSSConfig
from app.storage.base import (
    StorageBackend, StorageConfigurationError, StorageConnectionError,
    StorageError, StorageFileNotFoundError, StorageIsADirectoryError,
    StorageNotADirectoryError, StoragePermissionError,
)


class AliyunOSSStorage(StorageBackend):
    """A V2-API-only OSS backend with a user-scoped virtual root."""

    name = "AliyunOSS"
    CHUNK_SIZE = 1024 * 1024
    MULTIPART_THRESHOLD = 16 * 1024 * 1024
    MULTIPART_PART_SIZE = 10 * 1024 * 1024
    SEARCH_MAX_RESULTS = 2000

    def __init__(self, config: OSSConfig, user_id: str):
        if oss is None:
            raise StorageConfigurationError(
                "Aliyun OSS support requires the 'alibabacloud-oss-v2' package"
            )
        if not all((config.region, config.endpoint, config.bucket, config.access_key_id, config.access_key_secret)):
            raise StorageConfigurationError(
                "OSS region, endpoint, bucket and credentials are required"
            )
        self.config = config
        self.user_id = user_id
        self.root_prefix = self._join(config.prefix, "users", user_id)
        sdk_config = oss.config.load_default()
        sdk_config.credentials_provider = oss.credentials.StaticCredentialsProvider(
            config.access_key_id, config.access_key_secret
        )
        # V2 uses V4 signatures, therefore a region is mandatory even if endpoint is set.
        sdk_config.region = config.region
        sdk_config.endpoint = config.endpoint
        self.client = oss.Client(sdk_config)

    @staticmethod
    def _join(*parts: str) -> str:
        return "/".join(str(part).strip("/") for part in parts if str(part).strip("/"))

    def _path(self, remote_path: str, directory: bool = False) -> str:
        raw = str(remote_path or "").replace("\\", "/").lstrip("/")
        parts = [part for part in PurePosixPath(raw).parts if part not in {"", "."}]
        if any(part == ".." for part in parts):
            raise StoragePermissionError("Access denied: path is outside the storage root")
        key = self._join(self.root_prefix, *parts)
        return f"{key}/" if directory and key else key

    def _relative(self, key: str) -> str:
        return key.removeprefix(f"{self.root_prefix}/").rstrip("/")

    @staticmethod
    def _timestamp(value) -> float | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.replace(tzinfo=value.tzinfo or timezone.utc).timestamp()
        try:
            return datetime.strptime(str(value), "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            return None

    @staticmethod
    def _raise(error: Exception) -> None:
        while isinstance(error, oss.exceptions.OperationError):
            unwrapped = error.unwrap()
            if unwrapped is None or unwrapped is error:
                break
            error = unwrapped
        status = getattr(error, "status_code", None)
        code = getattr(error, "code", "")
        if status == 404 or code in {"NoSuchKey", "NoSuchBucket", "NoSuchObject"}:
            raise StorageFileNotFoundError(str(error)) from error
        if status in {401, 403} or code in {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"}:
            raise StoragePermissionError(str(error)) from error
        raise StorageConnectionError(str(error)) from error

    def _head(self, key: str):
        try:
            return self.client.head_object(oss.HeadObjectRequest(bucket=self.config.bucket, key=key))
        except (oss.exceptions.ServiceError, oss.exceptions.OperationError) as error:
            self._raise(error)

    def _list_pages(self, prefix: str, delimiter: str | None = None):
        token = None
        while True:
            result = self.client.list_objects_v2(oss.ListObjectsV2Request(
                bucket=self.config.bucket,
                prefix=prefix,
                delimiter=delimiter,
                continuation_token=token,
                max_keys=1000,
            ))
            yield result
            if not result.is_truncated:
                return
            token = result.next_continuation_token

    def _is_dir(self, remote_path: str) -> bool:
        # Each user has a virtual root even before its first object is uploaded.
        if str(remote_path or "").strip("./") == "":
            return True
        prefix = self._path(remote_path, directory=True)
        if not prefix:
            return True
        try:
            result = self.client.list_objects_v2(oss.ListObjectsV2Request(
                bucket=self.config.bucket, prefix=prefix, delimiter="/", max_keys=1
            ))
            return bool(result.contents or result.common_prefixes)
        except (oss.exceptions.ServiceError, oss.exceptions.OperationError) as error:
            self._raise(error)

    def exists(self, remote_path: str) -> bool:
        try:
            self._head(self._path(remote_path))
            return True
        except StorageFileNotFoundError:
            return self._is_dir(remote_path)

    def get_full_path(self, remote_path: str) -> str:
        raise StorageError("AliyunOSS does not expose local file paths; use a stream")

    async def upload_file(self, file_object: AsyncIterator[bytes], remote_path: str) -> None:
        key = self._path(remote_path)
        if not key:
            raise StorageConfigurationError("Cannot upload to the storage root")
        with tempfile.NamedTemporaryFile(prefix="stardrive-oss-upload-", delete=False) as source:
            source_path = source.name
            try:
                async for chunk in file_object:
                    if chunk:
                        source.write(chunk)
                size = source.tell()
                source.flush()
                if size >= self.MULTIPART_THRESHOLD:
                    await asyncio.to_thread(self._multipart_upload, key, source_path, size)
                else:
                    source.seek(0)
                    await asyncio.to_thread(self.client.put_object, oss.PutObjectRequest(
                        bucket=self.config.bucket, key=key, body=source
                    ))
            except (oss.exceptions.ServiceError, oss.exceptions.OperationError) as error:
                self._raise(error)
            finally:
                os.unlink(source_path)

    def _multipart_upload(self, key: str, source_path: str, size: int) -> None:
        """Use V2 multipart request models; no resume state is written locally."""
        initiated = self.client.initiate_multipart_upload(
            oss.InitiateMultipartUploadRequest(bucket=self.config.bucket, key=key)
        )
        parts = []
        try:
            with open(source_path, "rb") as source:
                part_number = 1
                for start in range(0, size, self.MULTIPART_PART_SIZE):
                    length = min(self.MULTIPART_PART_SIZE, size - start)
                    reader = oss.io_utils.SectionReader(
                        oss.io_utils.ReadAtReader(source), start, length
                    )
                    result = self.client.upload_part(oss.UploadPartRequest(
                        bucket=self.config.bucket,
                        key=key,
                        upload_id=initiated.upload_id,
                        part_number=part_number,
                        body=reader,
                    ))
                    parts.append(oss.UploadPart(part_number=part_number, etag=result.etag))
                    part_number += 1
            self.client.complete_multipart_upload(oss.CompleteMultipartUploadRequest(
                bucket=self.config.bucket,
                key=key,
                upload_id=initiated.upload_id,
                complete_multipart_upload=oss.CompleteMultipartUpload(parts=parts),
            ))
        except Exception:
            self.client.abort_multipart_upload(oss.AbortMultipartUploadRequest(
                bucket=self.config.bucket, key=key, upload_id=initiated.upload_id
            ))
            raise

    def download_file(self, remote_path: str) -> bytes:
        return b"".join(self.download_file_with_stream(remote_path))

    def download_file_with_stream(self, remote_path: str, offset: int = 0, length: int | None = None) -> Iterator[bytes]:
        range_header = None
        if offset or length is not None:
            end = "" if length is None else str(offset + max(length - 1, 0))
            range_header = f"bytes={offset}-{end}"
        try:
            result = self.client.get_object(oss.GetObjectRequest(
                bucket=self.config.bucket, key=self._path(remote_path), range_header=range_header
            ))
            with result.body as body:
                yield from body.iter_bytes(block_size=self.CHUNK_SIZE)
        except (oss.exceptions.ServiceError, oss.exceptions.OperationError) as error:
            self._raise(error)

    def delete_file(self, remote_path: str) -> None:
        if self._is_dir(remote_path):
            raise StorageIsADirectoryError(remote_path)
        self._head(self._path(remote_path))
        try:
            self.client.delete_object(oss.DeleteObjectRequest(
                bucket=self.config.bucket, key=self._path(remote_path)
            ))
        except (oss.exceptions.ServiceError, oss.exceptions.OperationError) as error:
            self._raise(error)

    def _metadata_for_object(self, item) -> FileMetadata:
        path = self._relative(item.key)
        name = PurePosixPath(path).name
        return FileMetadata(name=name, path=path, extension=PurePosixPath(name).suffix or None, size=item.size, modified_at=self._timestamp(item.last_modified), custom_updated_at=self._timestamp(item.last_modified))

    def _directory_metadata(self, prefix: str) -> DirMetadata:
        path = self._relative(prefix)
        return DirMetadata(name=PurePosixPath(path).name, path=path, size=0)

    def list_files(self, remote_path: str) -> list[FileMetadata | DirMetadata]:
        prefix = self._path(remote_path, directory=True)
        if remote_path and not self._is_dir(remote_path):
            raise StorageNotADirectoryError(remote_path)
        items: list[FileMetadata | DirMetadata] = []
        try:
            for result in self._list_pages(prefix, delimiter="/"):
                for child_prefix in result.common_prefixes or []:
                    # OSS V2 returns CommonPrefix objects here, unlike the
                    # string values returned by earlier SDK versions.
                    child_prefix = getattr(child_prefix, "prefix", child_prefix)
                    path = self._relative(child_prefix)
                    if path and not PurePosixPath(path).name.startswith("."):
                        items.append(self._directory_metadata(child_prefix))
                for item in result.contents or []:
                    if item.key == prefix or item.key.endswith("/"):
                        continue
                    metadata = self._metadata_for_object(item)
                    if not metadata.name.startswith("."):
                        items.append(metadata)
        except (oss.exceptions.ServiceError, oss.exceptions.OperationError) as error:
            self._raise(error)
        return items

    def create_directory(self, remote_path: str) -> None:
        key = self._path(remote_path, directory=True)
        if key:
            try:
                self.client.put_object(oss.PutObjectRequest(bucket=self.config.bucket, key=key, body=b""))
            except (oss.exceptions.ServiceError, oss.exceptions.OperationError) as error:
                self._raise(error)

    def _keys_under(self, prefix: str) -> list[str]:
        return [item.key for result in self._list_pages(prefix) for item in (result.contents or [])]

    def _delete_keys(self, keys: list[str]) -> None:
        for index in range(0, len(keys), 1000):
            delete = oss.Delete(objects=[oss.ObjectIdentifier(key=key) for key in keys[index:index + 1000]], quiet=True)
            self.client.delete_multiple_objects(oss.DeleteMultipleObjectsRequest(
                bucket=self.config.bucket, delete=delete
            ))

    def delete_directory(self, remote_path: str) -> None:
        if not self._is_dir(remote_path):
            raise StorageFileNotFoundError(remote_path)
        try:
            self._delete_keys(self._keys_under(self._path(remote_path, directory=True)))
        except (oss.exceptions.ServiceError, oss.exceptions.OperationError) as error:
            self._raise(error)

    def copy_file(self, src_path: str, dest_path: str) -> None:
        try:
            self.client.copy_object(oss.CopyObjectRequest(
                bucket=self.config.bucket,
                key=self._path(dest_path),
                source_bucket=self.config.bucket,
                source_key=self._path(src_path),
            ))
        except (oss.exceptions.ServiceError, oss.exceptions.OperationError) as error:
            self._raise(error)

    def move_file(self, src_path: str, dest_path: str) -> None:
        if self._is_dir(src_path):
            source_prefix, destination_prefix = self._path(src_path, True), self._path(dest_path, True)
            try:
                keys = self._keys_under(source_prefix)
                for key in keys:
                    self.client.copy_object(oss.CopyObjectRequest(
                        bucket=self.config.bucket,
                        key=destination_prefix + key.removeprefix(source_prefix),
                        source_bucket=self.config.bucket,
                        source_key=key,
                    ))
                self._delete_keys(keys)
            except (oss.exceptions.ServiceError, oss.exceptions.OperationError) as error:
                self._raise(error)
        else:
            self.copy_file(src_path, dest_path)
            self.delete_file(src_path)

    def get_file_metadata(self, remote_path: str) -> FileMetadata | DirMetadata:
        try:
            meta = self._head(self._path(remote_path))
            name = PurePosixPath(remote_path).name
            return FileMetadata(name=name, path=str(remote_path).strip("/"), extension=PurePosixPath(name).suffix or None, size=int(meta.content_length), modified_at=self._timestamp(meta.last_modified), custom_updated_at=self._timestamp(meta.last_modified))
        except StorageFileNotFoundError:
            if self._is_dir(remote_path):
                return self._directory_metadata(self._path(remote_path, True))
            raise

    async def get_directory_size(self, remote_path: str) -> int:
        if not self._is_dir(remote_path):
            raise StorageNotADirectoryError(remote_path)
        try:
            return await asyncio.to_thread(lambda: sum(
                item.size for result in self._list_pages(self._path(remote_path, True))
                for item in (result.contents or []) if not item.key.endswith("/")
            ))
        except (oss.exceptions.ServiceError, oss.exceptions.OperationError) as error:
            self._raise(error)

    async def search(self, query: str, remote_path: str, offset: int, limit: int) -> list[FileMetadata | DirMetadata]:
        prefix = self._path(remote_path, directory=True)
        matches: list[FileMetadata | DirMetadata] = []
        seen_dirs: set[str] = set()
        try:
            for result in await asyncio.to_thread(lambda: list(self._list_pages(prefix))):
                for item in result.contents or []:
                    relative = self._relative(item.key)
                    if not relative or any(part.startswith(".") for part in PurePosixPath(relative).parts):
                        continue
                    if query.lower() in PurePosixPath(relative).name.lower():
                        matches.append(self._metadata_for_object(item))
                    for parent in PurePosixPath(relative).parents:
                        if str(parent) != "." and query.lower() in parent.name.lower() and str(parent) not in seen_dirs:
                            seen_dirs.add(str(parent))
                            matches.append(DirMetadata(name=parent.name, path=str(parent), size=0))
                    if len(matches) >= self.SEARCH_MAX_RESULTS:
                        return matches[offset:offset + limit]
        except (oss.exceptions.ServiceError, oss.exceptions.OperationError) as error:
            self._raise(error)
        return matches[offset:offset + limit]
