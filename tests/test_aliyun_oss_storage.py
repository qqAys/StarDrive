from types import SimpleNamespace

from alibabacloud_oss_v2.models import CommonPrefix

from app.storage.aliyun_oss_storage import AliyunOSSStorage


def test_list_files_uses_the_prefix_from_oss_v2_common_prefix():
    """Delimited OSS listings expose directories as CommonPrefix models."""
    storage = AliyunOSSStorage.__new__(AliyunOSSStorage)
    storage.root_prefix = "stardrive/users/user-1"
    storage._is_dir = lambda _: True
    storage._list_pages = lambda *_args, **_kwargs: iter((
        SimpleNamespace(
            common_prefixes=[CommonPrefix(prefix="stardrive/users/user-1/documents/")],
            contents=[],
        ),
    ))

    assert storage.list_files("") == [
        storage._directory_metadata("stardrive/users/user-1/documents/")
    ]
