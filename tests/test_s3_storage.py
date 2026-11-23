"""In-memory S3 protocol fixture; never opens a network connection."""

import asyncio
import io
from types import SimpleNamespace

import pytest

from app.storage.s3_storage import S3Config, S3Storage
from app.storage.local_storage import LocalStorage
from app.storage.base import (
    StorageError,
    StoragePermissionError,
    StorageFileNotFoundError,
)
from app.services.file_service import StorageManager
from test_archive_backends import archive_manifest


class Client:
    def __init__(self):
        self.objects = {}
        self.uploads = {}
        self.aborted = []
        self.pages = []
        self.bodies = []
        self.fail_part = False
        self.fail_copy = False
        self.fail_delete = False

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise StorageFileNotFoundError(Key)
        return {"ContentLength": len(self.objects[Key])}

    def put_object(self, Bucket, Key, Body):
        self.objects[Key] = Body
        return {}

    def list_objects_v2(
        self, Bucket, Prefix, MaxKeys, Delimiter=None, ContinuationToken=None
    ):
        contents, prefixes = [], set()
        for key, value in sorted(self.objects.items()):
            if not key.startswith(Prefix):
                continue
            rest = key[len(Prefix) :]
            if Delimiter and "/" in rest:
                prefixes.add(Prefix + rest.split("/", 1)[0] + "/")
            else:
                contents.append({"Key": key, "Size": len(value)})
        entries = [(False, o) for o in contents] + [
            (True, {"Prefix": p}) for p in sorted(prefixes)
        ]
        start = int(ContinuationToken or 0)
        end = start + min(MaxKeys, 2)
        self.pages.append(start)
        return {
            "Contents": [o for d, o in entries[start:end] if not d],
            "CommonPrefixes": [o for d, o in entries[start:end] if d],
            "IsTruncated": end < len(entries),
            "NextContinuationToken": str(end),
        }

    def get_object(self, Bucket, Key, Range=None):
        data = self.objects[Key]
        if Range:
            start, end = Range.removeprefix("bytes=").split("-")
            data = data[int(start) : int(end) + 1 if end else None]
        body = io.BytesIO(data)
        self.bodies.append(body)
        return {"Body": body}

    def create_multipart_upload(self, **kwargs):
        self.uploads["upload"] = []
        return {"UploadId": "upload"}

    def upload_part(self, Body, **kwargs):
        if self.fail_part:
            raise StorageError("synthetic part failure")
        self.uploads["upload"].append(Body)
        return {"ETag": "synthetic"}

    def complete_multipart_upload(self, Key, **kwargs):
        self.objects[Key] = b"".join(self.uploads.pop("upload"))
        return {}

    def abort_multipart_upload(self, UploadId, **kwargs):
        self.aborted.append(UploadId)
        self.uploads.pop(UploadId)
        return {}

    def copy_object(self, Key, CopySource, **kwargs):
        if self.fail_copy:
            raise StorageError("synthetic copy failure")
        self.objects[Key] = self.objects[CopySource["Key"]]
        return {}

    def delete_objects(self, Delete, **kwargs):
        if self.fail_delete:
            return {
                "Errors": [
                    {"Key": o["Key"], "Code": "AccessDenied"} for o in Delete["Objects"]
                ]
            }
        for obj in Delete["Objects"]:
            self.objects.pop(obj["Key"], None)
        return {"Deleted": Delete["Objects"]}


@pytest.fixture
def storage():
    backend = S3Storage.__new__(S3Storage)
    backend.config = S3Config(
        "https://synthetic.invalid", "test", "test", "id", "secret", "prefix"
    )
    backend.root_prefix = "prefix/users/owner"
    backend.client = Client()
    # This fixture exercises driver operations independently of SDK installation.
    backend._call = lambda operation, **kwargs: getattr(backend.client, operation)(
        Bucket="test", **kwargs
    )
    return backend


async def chunks(*values):
    for value in values:
        yield value


def test_shared_archive_range_and_user_isolation(storage, tmp_path):
    files = {"资料/é.txt": b"unicode", "资料/a": b"a", "资料/b": b"b", "zero": b""}
    for path, data in files.items():
        asyncio.run(storage.upload_file(chunks(data), path))
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    storage.create_directory("资料/空目录")
    (tmp_path / "资料/空目录").mkdir()
    storage.client.objects["prefix/users/other/private"] = b"private"
    manager = StorageManager(root_path=tmp_path)
    manager.set_current_backend(LocalStorage.name)
    local_manifest = archive_manifest(manager, ["资料", "zero"])
    manager.register_backend(storage.name, storage)
    manager.set_current_backend(storage.name)
    assert archive_manifest(manager, ["资料", "zero"]) == local_manifest
    assert b"".join(storage.download_file_with_stream("资料/é.txt", 1, 3)) == b"nic"
    assert b"".join(storage.download_file_with_stream("zero", length=0)) == b""
    assert all(b.closed for b in storage.client.bodies)
    assert any(p > 0 for p in storage.client.pages)
    assert asyncio.run(storage.get_directory_size(".")) == 9
    assert [m.path for m in asyncio.run(storage.search("空", ".", 0, 30))] == [
        "资料/空目录"
    ]
    for path in ("../other", "x/../../other", "..\\other"):
        with pytest.raises(StoragePermissionError):
            storage.exists(path)


@pytest.mark.parametrize("failure", ["producer", "part", "cancel"])
def test_multipart_failure_abort_and_retry_digest(storage, failure):
    import hashlib

    storage.MULTIPART_PART_SIZE = 4
    storage.client.fail_part = failure == "part"

    async def interrupted():
        yield b"abcd"
        if failure == "cancel":
            raise asyncio.CancelledError
        raise RuntimeError("synthetic producer failure")

    with pytest.raises((RuntimeError, StorageError, asyncio.CancelledError)):
        asyncio.run(storage.upload_file(interrupted(), "large"))
    assert storage.client.aborted == ["upload"]
    assert not storage.client.uploads
    assert storage._path("large") not in storage.client.objects
    storage.client.fail_part = False
    asyncio.run(storage.upload_file(chunks(b"abcdefghij"), "large"))
    assert (
        hashlib.sha256(storage.download_file("large")).digest()
        == hashlib.sha256(b"abcdefghij").digest()
    )


def test_copy_and_partial_delete_recovery(storage):
    storage.client.objects[storage._path("folder/a")] = b"source"
    storage.client.fail_copy = True
    with pytest.raises(StorageError, match="copy"):
        storage.move_file("folder", "dest")
    assert storage.download_file("folder/a") == b"source"
    storage.client.fail_copy = False
    storage.client.fail_delete = True
    with pytest.raises(StorageError, match="incomplete"):
        storage.move_file("folder", "dest")
    assert storage.download_file("folder/a") == storage.download_file("dest/a")
    storage.client.fail_delete = False
    storage.move_file("folder", "dest")
    assert storage._path("folder/a") not in storage.client.objects
    assert storage.download_file("dest/a") == b"source"
    with pytest.raises(StoragePermissionError):
        storage.move_file("dest", "dest/sub")


def test_sdk_configuration_and_error_mapping(monkeypatch):
    import boto3
    from botocore.exceptions import ClientError
    import app.storage.s3_storage as module

    captured = {}

    def client(service, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(boto3, "client", client)
    config = S3Config("https://synthetic.invalid", "test", "test", "id", "secret")
    backend = S3Storage(config, "owner")
    assert captured["config"].retries["total_max_attempts"] == 3
    assert captured["config"].connect_timeout == 5
    assert "secret" not in repr(config)

    def denied(**kwargs):
        raise ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "secret"}}, "GetObject"
        )

    backend.client = SimpleNamespace(get_object=denied)
    with pytest.raises(StoragePermissionError, match="^S3 permission denied$"):
        backend.download_file("x")
    monkeypatch.setattr(module, "boto3", None)
    from app.storage.base import StorageConfigurationError

    with pytest.raises(StorageConfigurationError):
        S3Storage(config, "owner")


def test_cancel_inflight_part_waits_before_abort(storage):
    import threading

    started, release = threading.Event(), threading.Event()
    original = storage.client.upload_part

    def slow_part(**kwargs):
        started.set()
        assert release.wait(3)
        assert not storage.client.aborted
        return original(**kwargs)

    storage.client.upload_part = slow_part
    storage.MULTIPART_PART_SIZE = 4

    async def run():
        task = asyncio.create_task(storage.upload_file(chunks(b"abcd"), "large"))
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        await asyncio.sleep(0)
        assert not storage.client.aborted
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert storage.client.aborted == ["upload"]
    assert not storage.client.uploads


def test_pagination_stall_and_stream_close(storage):
    storage.client.list_objects_v2 = lambda **kwargs: {
        "IsTruncated": True,
        "NextContinuationToken": "same",
    }
    from app.storage.base import StorageConnectionError

    with pytest.raises(StorageConnectionError, match="advance"):
        storage.list_files(".")
    storage.client.objects[storage._path("file")] = b"abcdef"
    stream = storage.download_file_with_stream("file")
    assert next(stream) == b"abcdef"
    stream.close()
    assert storage.client.bodies[-1].closed


def test_root_and_response_boundaries(storage):
    assert storage._relative(storage.root_prefix + "/") == ""
    with pytest.raises(StoragePermissionError):
        storage._relative("prefix/users/other/private")
    from app.storage.base import StorageIsADirectoryError

    with pytest.raises(StorageIsADirectoryError):
        asyncio.run(storage.upload_file(chunks(b"x"), "."))
    with pytest.raises(ValueError):
        list(storage.download_file_with_stream("x", -1))


@pytest.mark.parametrize("destination", ["a", "a/b/sub", "a/b"])
def test_move_rejects_overlapping_paths_before_copy(storage, destination):
    storage.client.objects.update(
        {
            storage._path("a/b/x"): b"outer source",
            storage._path("a/b/b/x"): b"inner source",
            storage._path("a/x"): b"existing destination",
        }
    )
    before = dict(storage.client.objects)

    def unexpected_copy(**kwargs):
        pytest.fail("overlapping move must be rejected before copying")

    storage.client.copy_object = unexpected_copy
    with pytest.raises(StoragePermissionError):
        storage.move_file("a/b", destination)
    assert storage.client.objects == before


@pytest.mark.parametrize("failure", ["mixed", "missing", "next_batch"])
def test_directory_move_partial_deletion_retry_preserves_digest(storage, failure):
    import hashlib

    count = 1002 if failure == "next_batch" else 3
    originals = {f"{index:04d}": f"payload-{index}".encode() for index in range(count)}
    for name, data in originals.items():
        storage.client.objects[storage._path("source/" + name)] = data
    original_delete = storage.client.delete_objects
    calls = []

    def partial_delete(Delete, **kwargs):
        objects = Delete["Objects"]
        calls.append([obj["Key"] for obj in objects])
        if failure == "next_batch" and len(calls) == 1:
            return original_delete(Delete=Delete, **kwargs)
        # One confirmed deletion, one retained object, and (when present) an
        # unconfirmed deletion. A retry must preserve the full destination.
        storage.client.objects.pop(objects[0]["Key"])
        result = {"Deleted": objects[:1]}
        if failure != "missing":
            result["Errors"] = [{"Key": objects[1]["Key"], "Code": "AccessDenied"}]
        for obj in objects[2:]:
            storage.client.objects.pop(obj["Key"])
        return result

    storage.client.delete_objects = partial_delete
    with pytest.raises(StorageError, match="incomplete"):
        storage.move_file("source", "destination")
    assert [len(batch) for batch in calls] == (
        [1000, 2] if failure == "next_batch" else [3]
    )
    remaining = {
        key: value
        for key, value in storage.client.objects.items()
        if key.startswith(storage._path("source") + "/")
    }
    assert remaining == {calls[-1][1]: originals[calls[-1][1].rsplit("/", 1)[1]]}
    expected = {name: hashlib.sha256(data).digest() for name, data in originals.items()}

    def destination_digests():
        prefix = storage._path("destination") + "/"
        return {
            key[len(prefix) :]: hashlib.sha256(data).digest()
            for key, data in storage.client.objects.items()
            if key.startswith(prefix)
        }

    assert destination_digests() == expected
    storage.client.delete_objects = original_delete
    storage.move_file("source", "destination")
    assert not any(
        key.startswith(storage._path("source") + "/") for key in storage.client.objects
    )
    assert destination_digests() == expected
