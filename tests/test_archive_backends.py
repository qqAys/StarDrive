"""Shared archive contract using a local tree and a paginated synthetic OSS client."""

import asyncio
import hashlib
import io
import tarfile
from types import SimpleNamespace

import pytest

from app.services.file_service import StorageManager
from app.storage.aliyun_oss_storage import AliyunOSSStorage
from app.storage.base import StorageFileNotFoundError
from app.storage.local_storage import LocalStorage


class SyntheticBody:
    def __init__(self, data, fail=False):
        self.data = data
        self.fail = fail
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True

    def iter_bytes(self, block_size):
        yield self.data[:1]
        if self.fail:
            raise OSError("Synthetic network read failure")
        yield self.data[1:]


class SyntheticOSSClient:
    def __init__(self, objects):
        self.objects = objects
        self.pages = []
        self.bodies = []
        self.fail_list = False
        self.fail_read = False

    def list_objects_v2(self, request):
        if self.fail_list:
            raise OSError("Synthetic listing connection failure")
        prefix = request.prefix
        contents = []
        prefixes = set()
        for key, data in sorted(self.objects.items()):
            if not key.startswith(prefix):
                continue
            suffix = key[len(prefix) :]
            if request.delimiter and "/" in suffix:
                prefixes.add(prefix + suffix.split("/", 1)[0] + "/")
            else:
                contents.append(
                    SimpleNamespace(key=key, size=len(data), last_modified=None)
                )
        entries = [(False, item) for item in contents] + [
            (True, SimpleNamespace(prefix=value)) for value in sorted(prefixes)
        ]
        start = int(request.continuation_token or 0)
        # Deliberately paginate well below the SDK's requested maximum.
        end = start + min(request.max_keys or 1000, 2)
        self.pages.append((prefix, start))
        return SimpleNamespace(
            contents=[item for directory, item in entries[start:end] if not directory],
            common_prefixes=[
                item for directory, item in entries[start:end] if directory
            ],
            is_truncated=end < len(entries),
            next_continuation_token=str(end),
        )

    def get_object(self, request):
        body = SyntheticBody(self.objects[request.key], self.fail_read)
        self.bodies.append(body)
        return SimpleNamespace(body=body)


def backend_pair(tmp_path):
    files = {
        "资料/é.txt": b"unicode",
        "资料/sub/one": b"one",
        "资料/sub/two": b"two",
        "资料/sub/three": b"three",
        "资料-extra": b"separate prefix",
        "zero": b"",
    }
    for path, data in files.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (tmp_path / "资料/空目录").mkdir()
    local = StorageManager(root_path=tmp_path)
    local.set_current_backend(LocalStorage.name)
    oss = AliyunOSSStorage.__new__(AliyunOSSStorage)
    oss.root_prefix = "synthetic/users/owner"
    oss.config = SimpleNamespace(bucket="synthetic")
    objects = {oss._path(path): data for path, data in files.items()}
    objects[oss._path("资料/空目录", directory=True)] = b""
    # A different user's objects must never enter the listing or archive.
    objects["synthetic/users/other/private"] = b"other user"
    oss.client = SyntheticOSSClient(objects)

    def head(key):
        if key not in objects:
            raise StorageFileNotFoundError(key)
        return SimpleNamespace(content_length=len(objects[key]), last_modified=None)

    oss._head = head
    remote = StorageManager(root_path=tmp_path)
    remote.register_backend(oss.name, oss)
    remote.set_current_backend(oss.name)
    return local, remote, oss.client


def archive_manifest(storage, paths, base="."):
    async def collect():
        return b"".join(
            [
                part
                async for part in storage.download_file_with_compressed_stream(
                    paths, base
                )
            ]
        )

    data = asyncio.run(asyncio.wait_for(collect(), 3))
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        assert len(names) == len(set(names))
        return {
            member.name: (
                "dir"
                if member.isdir()
                else hashlib.sha256(archive.extractfile(member).read()).hexdigest()
            )
            for member in members
        }


@pytest.mark.parametrize("child_first", [False, True])
def test_archive_backend_parity_pagination_overlap_and_unicode(tmp_path, child_first):
    local, remote, client = backend_pair(tmp_path)
    paths = ["资料", "./资料/", "资料/é.txt", "资料/sub", "资料-extra", "zero", "zero"]
    if child_first:
        paths.insert(0, "资料/sub/one")
    expected = archive_manifest(local, paths)
    assert set(expected) == {
        "资料",
        "资料/é.txt",
        "资料/sub",
        "资料/sub/one",
        "资料/sub/two",
        "资料/sub/three",
        "资料/空目录",
        "资料-extra",
        "zero",
    }
    assert expected["资料/空目录"] == "dir"
    assert archive_manifest(remote, paths) == expected
    assert any(start > 0 for _, start in client.pages)
    assert all(body.closed for body in client.bodies)
    assert archive_manifest(
        remote, ["资料/sub", "资料/sub/one"], "资料"
    ) == archive_manifest(local, ["资料/sub", "资料/sub/one"], "资料")


@pytest.mark.parametrize("failure", ["listing", "read"])
def test_oss_archive_network_failure_terminates_and_closes(tmp_path, failure):
    _, remote, client = backend_pair(tmp_path)
    if failure == "listing":
        # Preflight head succeeds, then recursive enumeration loses connectivity.
        remote._get_current_backend()._is_dir = lambda path: True
        client.fail_list = True
    else:
        client.fail_read = True
    with pytest.raises(OSError, match="Synthetic"):
        archive_manifest(remote, ["资料"])
    assert all(body.closed for body in client.bodies)
    if failure == "read":
        assert client.bodies


@pytest.mark.parametrize("backend", ["local", "oss"])
@pytest.mark.parametrize("change", ["missing", "short_read"])
def test_archive_source_change_rejects_incomplete_output(
    tmp_path, monkeypatch, backend, change
):
    local, remote, _ = backend_pair(tmp_path)
    storage = local if backend == "local" else remote
    closed = []

    def changed_stream(path):
        try:
            if change == "missing":
                raise StorageFileNotFoundError("Synthetic source disappeared")
            yield b"x"
        finally:
            closed.append(path)

    monkeypatch.setattr(storage, "download_file_with_stream", changed_stream)
    with pytest.raises((StorageFileNotFoundError, OSError)):
        archive_manifest(storage, ["资料/é.txt"])
    assert closed == ["资料/é.txt"]
