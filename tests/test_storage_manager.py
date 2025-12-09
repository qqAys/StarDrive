from io import BytesIO
from typing import Generator, BinaryIO

import pytest
from models.file_metadata import FileMetadata

from storage.base import StorageBackend
from storage.local_storage import LocalStorage
from storage.manager import StorageManager, BackendNotFoundError


# --- 1. Mock/Fake 类定义 ---


class FakeFileMetadata:
    def __init__(self, name: str, is_dir: bool = False, size: int = 0):
        self.name = name
        self.is_dir = is_dir
        self.size = size


class MockLocalStorage(StorageBackend):
    name = "LocalStorage"

    def exists(self, remote_path: str) -> bool:
        pass

    def upload_file(self, file_object: BinaryIO, remote_path: str):
        pass

    def upload_file_from_path(self, local_path: str, remote_path: str):
        pass

    def download_file(self, remote_path: str) -> bytes:
        pass

    def download_file_with_stream(
        self, remote_path: str
    ) -> Generator[bytes, None, None]:
        pass

    def delete_file(self, remote_path: str):
        pass

    def list_files(self, remote_path: str) -> list[FileMetadata]:
        pass

    def create_directory(self, remote_path: str):
        pass

    def delete_directory(self, remote_path: str):
        pass

    def move_file(self, src_path: str, dest_path: str):
        pass

    def copy_file(self, src_path: str, dest_path: str):
        pass

    def get_file_metadata(self, remote_path: str) -> FileMetadata:
        pass


# --- 2. Pytest Fixture ---


@pytest.fixture
def mock_local_storage(mocker):
    """
    Fixture: 模拟 LocalStorage 实例，并确保 StorageManager 使用它。
    """
    # 模拟 LocalStorage 类本身，使其在被实例化时返回一个 Mock 对象
    mock_instance = mocker.MagicMock(spec=MockLocalStorage)
    mocker.patch("storage.manager.LocalStorage", return_value=mock_instance)
    # 同时 mock 掉 LocalStorage.name
    mocker.patch("storage.manager.LocalStorage.name", new="LocalStorage")
    return mock_instance


@pytest.fixture
def manager_with_local(mock_local_storage):
    """
    Fixture: 创建一个 StorageManager 实例，它会自动注册 MockLocalStorage。
    并设置 'local' 为当前活跃后端。
    """
    manager = StorageManager()
    manager.set_current_backend(LocalStorage.name)
    return manager


# --- 3. 测试用例 (Test Cases) ---


class TestLocalStorageThroughStorageManager:

    # 1. 初始化和设置检查
    def test_manager_initialization_registers_local(
        self, manager_with_local, mock_local_storage
    ):
        """
        验证 StorageManager 初始化时，LocalStorage 是否被正确注册。
        """
        # Manager 初始化时，'local' 应该在已注册后端列表中
        assert "LocalStorage" in manager_with_local.list_backends()
        # 验证当前后端已设置为 'local'
        assert manager_with_local._current_backend_name == "LocalStorage"
        # 验证注册的实例是 mock_local_storage
        assert manager_with_local._backends["LocalStorage"] == mock_local_storage

    # 2. 文件上传/存在测试
    def test_upload_file_proxies_correctly(
        self, manager_with_local, mock_local_storage
    ):
        """
        测试 upload_file 是否正确代理到 LocalStorage 的对应方法。
        """
        remote_path = "test/file_stream.txt"
        file_content = BytesIO(b"Hello Local Storage")

        manager_with_local.upload_file(file_content, remote_path)

        # 验证 mock 实例的 upload_file 方法被调用
        mock_local_storage.upload_file.assert_called_once_with(
            file_content, remote_path
        )

    def test_upload_file_from_path_proxies_correctly(
        self, manager_with_local, mock_local_storage
    ):
        """
        测试 upload_file_from_path 是否正确代理到 LocalStorage 的对应方法。
        """
        local_path = "/tmp/local_test.txt"
        remote_path = "test/file_path.txt"

        manager_with_local.upload_file_from_path(local_path, remote_path)

        # 验证 mock 实例的 upload_file_from_path 方法被调用
        mock_local_storage.upload_file_from_path.assert_called_once_with(
            local_path, remote_path
        )

    def test_exists_proxies_correctly(self, manager_with_local, mock_local_storage):
        """
        测试 exists 是否正确代理到 LocalStorage 的对应方法并返回结果。
        """
        remote_path = "existing/file.txt"
        mock_local_storage.exists.return_value = True

        result = manager_with_local.exists(remote_path)

        assert result is True
        mock_local_storage.exists.assert_called_once_with(remote_path)

    # 3. 文件下载测试
    def test_download_file_proxies_correctly(
        self, manager_with_local, mock_local_storage
    ):
        """
        测试 download_file 是否正确代理到 LocalStorage 并返回下载内容。
        """
        remote_path = "test/download.txt"
        expected_content = b"Binary File Content"
        mock_local_storage.download_file.return_value = expected_content

        content = manager_with_local.download_file(remote_path)

        assert content == expected_content
        mock_local_storage.download_file.assert_called_once_with(remote_path)

    def test_download_file_with_stream_proxies_correctly(
        self, manager_with_local, mock_local_storage
    ):
        """
        测试 download_file_with_stream 是否正确代理并返回一个生成器。
        """
        remote_path = "test/stream.bin"

        # 模拟生成器返回的块
        def mock_generator():
            yield b"chunk 1"
            yield b"chunk 2"

        mock_local_storage.download_file_with_stream.return_value = mock_generator()

        stream = manager_with_local.download_file_with_stream(remote_path)

        # 验证返回的是一个生成器，并且内容正确
        assert isinstance(stream, Generator)
        assert list(stream) == [b"chunk 1", b"chunk 2"]
        mock_local_storage.download_file_with_stream.assert_called_once_with(
            remote_path
        )

    # 4. 文件/目录管理测试
    def test_delete_file_proxies_correctly(
        self, manager_with_local, mock_local_storage
    ):
        """
        测试 delete_file 是否正确代理。
        """
        remote_path = "test/obsolete.txt"
        manager_with_local.delete_file(remote_path)
        mock_local_storage.delete_file.assert_called_once_with(remote_path)

    def test_create_directory_proxies_correctly(
        self, manager_with_local, mock_local_storage
    ):
        """
        测试 create_directory 是否正确代理。
        """
        remote_path = "new_dir"
        manager_with_local.create_directory(remote_path)
        mock_local_storage.create_directory.assert_called_once_with(remote_path)

    def test_delete_directory_proxies_correctly(
        self, manager_with_local, mock_local_storage
    ):
        """
        测试 delete_directory 是否正确代理。
        """
        remote_path = "old_dir"
        manager_with_local.delete_directory(remote_path)
        mock_local_storage.delete_directory.assert_called_once_with(remote_path)

    # 5. 元数据和列表测试
    def test_list_files_proxies_correctly(self, manager_with_local, mock_local_storage):
        """
        测试 list_files 是否正确代理并返回列表。
        """
        remote_path = "root/"
        mock_metadata = [
            FakeFileMetadata(name="file1.txt", size=100),
            FakeFileMetadata(name="subdir", is_dir=True),
        ]
        mock_local_storage.list_files.return_value = mock_metadata

        result = manager_with_local.list_files(remote_path)

        assert result == mock_metadata
        mock_local_storage.list_files.assert_called_once_with(remote_path)

    def test_get_file_metadata_proxies_correctly(
        self, manager_with_local, mock_local_storage
    ):
        """
        测试 get_file_metadata 是否正确代理并返回元数据。
        """
        remote_path = "target.pdf"
        expected_metadata = FakeFileMetadata(name="target.pdf", size=10240)
        mock_local_storage.get_file_metadata.return_value = expected_metadata

        metadata = manager_with_local.get_file_metadata(remote_path)

        assert metadata == expected_metadata
        mock_local_storage.get_file_metadata.assert_called_once_with(remote_path)

    # 6. 移动/复制测试
    def test_move_file_proxies_correctly(self, manager_with_local, mock_local_storage):
        """
        测试 move_file 是否正确代理。
        """
        src_path = "old/path/file.txt"
        dest_path = "new/path/file.txt"
        manager_with_local.move_file(src_path, dest_path)
        mock_local_storage.move_file.assert_called_once_with(src_path, dest_path)

    def test_copy_file_proxies_correctly(self, manager_with_local, mock_local_storage):
        """
        测试 copy_file 是否正确代理。
        """
        src_path = "source.jpg"
        dest_path = "copy_of_source.jpg"
        manager_with_local.copy_file(src_path, dest_path)
        mock_local_storage.copy_file.assert_called_once_with(src_path, dest_path)

    # 7. 异常测试 (确保在未设置当前后端时抛出异常)
    def test_proxy_raises_error_if_no_current_backend(self, mock_local_storage):
        """
        测试在没有设置当前后端时，任何代理方法调用都会抛出 BackendNotFoundError。
        """
        manager = StorageManager()  # 此时 _current_backend_name 为 None

        # 随便选一个代理方法进行测试
        with pytest.raises(BackendNotFoundError, match="当前存储后端未设置或找不到"):
            manager.exists("any/path")
