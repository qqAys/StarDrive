from types import SimpleNamespace

import pytest
from alibabacloud_oss_v2.exceptions import OperationError
from alibabacloud_oss_v2.models import (
    CommonPrefix,
    DeletedInfo,
    DeleteMultipleObjectsResult,
)

from app.storage.aliyun_oss_storage import AliyunOSSStorage
from app.storage.base import StorageConnectionError, StorageError


def test_list_files_uses_the_prefix_from_oss_v2_common_prefix():
    """Delimited OSS listings expose directories as CommonPrefix models."""
    storage = AliyunOSSStorage.__new__(AliyunOSSStorage)
    storage.root_prefix = "stardrive/users/user-1"
    storage._is_dir = lambda _: True
    storage._list_pages = lambda *_args, **_kwargs: iter(
        (
            SimpleNamespace(
                common_prefixes=[
                    CommonPrefix(prefix="stardrive/users/user-1/documents/")
                ],
                contents=[],
            ),
        )
    )

    assert storage.list_files("") == [
        storage._directory_metadata("stardrive/users/user-1/documents/")
    ]


@pytest.mark.parametrize("count", [0, 1, 1000, 1001, 2001])
def test_delete_keys_requires_verbose_confirmation(count):
    storage = AliyunOSSStorage.__new__(AliyunOSSStorage)
    storage.config = SimpleNamespace(bucket="synthetic")
    batches = []

    def delete(request):
        assert request.delete.quiet is False
        keys = [item.key for item in request.delete.objects]
        batches.append(keys)
        return DeleteMultipleObjectsResult(
            deleted_objects=[DeletedInfo(key=key) for key in keys]
        )

    storage.client = SimpleNamespace(delete_multiple_objects=delete)
    keys = [f"users/synthetic/{index}" for index in range(count)]
    storage._delete_keys(keys)
    assert batches == [keys[index : index + 1000] for index in range(0, count, 1000)]


@pytest.mark.parametrize(
    "confirmed",
    [None, [], [DeletedInfo(key="other")], [DeletedInfo(key="private-prefix/0")]],
)
def test_delete_keys_stops_on_missing_confirmation(confirmed):
    storage = AliyunOSSStorage.__new__(AliyunOSSStorage)
    storage.config = SimpleNamespace(bucket="synthetic")
    calls = []

    def delete(request):
        calls.append(request)
        return DeleteMultipleObjectsResult(deleted_objects=confirmed)

    storage.client = SimpleNamespace(delete_multiple_objects=delete)
    with pytest.raises(StorageError) as error:
        storage._delete_keys([f"private-prefix/{index}" for index in range(1001)])
    assert len(calls) == 1
    assert "private-prefix" not in str(error.value)


def test_delete_directory_maps_batch_request_failure():
    storage = AliyunOSSStorage.__new__(AliyunOSSStorage)
    storage.config = SimpleNamespace(bucket="synthetic")
    storage.root_prefix = "stardrive/users/user-1"
    private_key = "stardrive/users/user-1/documents/report.txt"

    def list_objects(request):
        assert request.prefix == "stardrive/users/user-1/documents/"
        return SimpleNamespace(
            contents=[SimpleNamespace(key=private_key)], is_truncated=False
        )

    def delete(request):
        assert [item.key for item in request.delete.objects] == [private_key]
        raise OperationError(name="DeleteMultipleObjects", error=TimeoutError())

    storage.client = SimpleNamespace(
        list_objects_v2=list_objects, delete_multiple_objects=delete
    )
    with pytest.raises(StorageConnectionError) as error:
        storage.delete_directory("documents")
    assert private_key not in str(error.value)


@pytest.mark.parametrize("request_times_out", [False, True])
def test_delete_directory_stops_after_later_batch_fails(request_times_out):
    storage = AliyunOSSStorage.__new__(AliyunOSSStorage)
    storage.config = SimpleNamespace(bucket="synthetic")
    storage.root_prefix = "stardrive/users/user-1"
    prefix = f"{storage.root_prefix}/documents/"
    keys = [f"{prefix}{index}" for index in range(2001)]
    sibling = "stardrive/users/user-2/documents/report.txt"
    remaining = dict.fromkeys([*keys, sibling])
    batches = []

    def list_objects(request):
        return SimpleNamespace(
            contents=[
                SimpleNamespace(key=key)
                for key in remaining
                if key.startswith(request.prefix)
            ],
            is_truncated=False,
        )

    def delete(request):
        batch = [item.key for item in request.delete.objects]
        batches.append(batch)
        if len(batches) == 2:
            if request_times_out:
                raise OperationError(name="DeleteMultipleObjects", error=TimeoutError())
            batch = batch[:1]
        for key in batch:
            del remaining[key]
        return DeleteMultipleObjectsResult(
            deleted_objects=[DeletedInfo(key=key) for key in batch]
        )

    storage.client = SimpleNamespace(
        list_objects_v2=list_objects, delete_multiple_objects=delete
    )
    expected_error = StorageConnectionError if request_times_out else StorageError
    with pytest.raises(expected_error) as error:
        storage.delete_directory("documents")

    assert prefix not in str(error.value)
    assert batches == [keys[:1000], keys[1000:2000]]
    retained_start = 1000 if request_times_out else 1001
    assert set(remaining) == {*keys[retained_start:], sibling}


def test_move_directory_retains_copies_when_delete_is_incomplete():
    storage = AliyunOSSStorage.__new__(AliyunOSSStorage)
    storage.config = SimpleNamespace(bucket="synthetic")
    storage.root_prefix = "stardrive/users/user-1"
    src_prefix = f"{storage.root_prefix}/source/"
    dst_prefix = f"{storage.root_prefix}/target/"
    source_files = {
        f"{src_prefix}报告 %.txt": b"report",
        f"{src_prefix}sub/file": b"data",
    }
    objects = source_files.copy()
    expected_copies = {
        dst_prefix + key.removeprefix(src_prefix): data
        for key, data in source_files.items()
    }

    def list_objects(request):
        return SimpleNamespace(
            contents=[
                SimpleNamespace(key=key)
                for key in objects
                if key.startswith(request.prefix)
            ],
            is_truncated=False,
        )

    def copy(request):
        objects[request.key] = objects[request.source_key]

    def delete(request):
        assert [item.key for item in request.delete.objects] == list(source_files)
        assert all(objects[key] == data for key, data in expected_copies.items())
        key = request.delete.objects[0].key
        del objects[key]
        return DeleteMultipleObjectsResult(deleted_objects=[DeletedInfo(key=key)])

    storage.client = SimpleNamespace(
        list_objects_v2=list_objects,
        copy_object=copy,
        delete_multiple_objects=delete,
    )
    with pytest.raises(StorageError):
        storage.move_file("source", "target")

    retained_key = f"{src_prefix}sub/file"
    assert objects == {retained_key: source_files[retained_key], **expected_copies}
