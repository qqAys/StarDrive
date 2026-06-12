import asyncio
from pathlib import Path
from typing import AsyncIterator, BinaryIO

import pytest

from app.schemas.file_schema import DirMetadata, FileMetadata
from app.services.file_service import BackendNotFoundError, StorageManager
from app.storage.base import StorageBackend
from app.storage.local_storage import LocalStorage


class MockLocalStorage(StorageBackend):
    name = "LocalStorage"

    def __init__(self, mocker):
        self.exists_mock = mocker.Mock()
        self.get_full_path_mock = mocker.Mock()
        self.upload_file_mock = mocker.AsyncMock()
        self.download_file_mock = mocker.Mock()
        self.download_file_with_stream_mock = mocker.Mock()
        self.delete_file_mock = mocker.Mock()
        self.list_files_mock = mocker.Mock()
        self.create_directory_mock = mocker.Mock()
        self.delete_directory_mock = mocker.Mock()
        self.move_file_mock = mocker.Mock()
        self.copy_file_mock = mocker.Mock()
        self.get_file_metadata_mock = mocker.Mock()
        self.get_directory_size_mock = mocker.AsyncMock()
        self.search_mock = mocker.AsyncMock()

    def exists(self, remote_path: str) -> bool:
        return self.exists_mock(remote_path)

    def get_full_path(self, remote_path: str) -> Path:
        return self.get_full_path_mock(remote_path)

    async def upload_file(
        self, file_object: AsyncIterator[bytes], remote_path: str
    ) -> None:
        await self.upload_file_mock(file_object, remote_path)

    def download_file(self, remote_path: str) -> bytes:
        return self.download_file_mock(remote_path)

    def download_file_with_stream(self, remote_path: str) -> BinaryIO:
        return self.download_file_with_stream_mock(remote_path)

    def delete_file(self, remote_path: str) -> None:
        self.delete_file_mock(remote_path)

    def list_files(self, remote_path: str) -> list[FileMetadata | DirMetadata]:
        return self.list_files_mock(remote_path)

    def create_directory(self, remote_path: str) -> None:
        self.create_directory_mock(remote_path)

    def delete_directory(self, remote_path: str) -> None:
        self.delete_directory_mock(remote_path)

    def move_file(self, src_path: str, dest_path: str) -> None:
        self.move_file_mock(src_path, dest_path)

    def copy_file(self, src_path: str, dest_path: str) -> None:
        self.copy_file_mock(src_path, dest_path)

    def get_file_metadata(self, remote_path: str) -> FileMetadata | DirMetadata:
        return self.get_file_metadata_mock(remote_path)

    async def get_directory_size(self, remote_path: str) -> int:
        return await self.get_directory_size_mock(remote_path)

    async def search(
        self, query: str, remote_path: str, offset: int, limit: int
    ) -> list[FileMetadata | DirMetadata]:
        return await self.search_mock(query, remote_path, offset, limit)


async def iter_bytes(*chunks: bytes):
    for chunk in chunks:
        yield chunk


@pytest.fixture
def mock_local_storage(mocker):
    mock_instance = MockLocalStorage(mocker)
    local_storage_class = mocker.patch("app.services.file_service.LocalStorage")
    local_storage_class.name = LocalStorage.name
    local_storage_class.return_value = mock_instance
    return mock_instance


@pytest.fixture
def manager_with_local(mock_local_storage):
    manager = StorageManager()
    manager.set_current_backend(LocalStorage.name)
    return manager


class TestLocalStorageThroughStorageManager:
    def test_manager_initialization_registers_local(
        self, manager_with_local, mock_local_storage
    ):
        assert "LocalStorage" in manager_with_local.list_backends()
        assert manager_with_local._current_backend_name == "LocalStorage"
        assert manager_with_local._backends["LocalStorage"] == mock_local_storage

    def test_exists_proxies_correctly(self, manager_with_local, mock_local_storage):
        remote_path = "existing/file.txt"
        mock_local_storage.exists_mock.return_value = True

        result = manager_with_local.exists(remote_path)

        assert result is True
        mock_local_storage.exists_mock.assert_called_once_with(remote_path)

    def test_get_full_path_proxies_correctly(
        self, manager_with_local, mock_local_storage
    ):
        remote_path = "existing/file.txt"
        expected_path = Path("/tmp/stardrive/existing/file.txt")
        mock_local_storage.get_full_path_mock.return_value = expected_path

        result = manager_with_local.get_full_path(remote_path)

        assert result == expected_path
        mock_local_storage.get_full_path_mock.assert_called_once_with(remote_path)

    def test_upload_file_proxies_correctly(
        self, manager_with_local, mock_local_storage
    ):
        remote_path = "test/file_stream.txt"
        file_content = iter_bytes(b"Hello ", b"Local Storage")

        result = asyncio.run(manager_with_local.upload_file(file_content, remote_path))

        assert result is True
        mock_local_storage.upload_file_mock.assert_awaited_once_with(
            file_content, remote_path
        )

    def test_download_file_proxies_correctly(
        self, manager_with_local, mock_local_storage
    ):
        remote_path = "test/download.txt"
        expected_content = b"Binary File Content"
        mock_local_storage.download_file_mock.return_value = expected_content

        content = manager_with_local.download_file(remote_path)

        assert content == expected_content
        mock_local_storage.download_file_mock.assert_called_once_with(remote_path)

    def test_download_file_with_stream_proxies_correctly(
        self, manager_with_local, mock_local_storage
    ):
        remote_path = "test/stream.bin"
        mock_local_storage.download_file_with_stream_mock.return_value = iter(
            [b"chunk 1", b"chunk 2"]
        )

        stream = manager_with_local.download_file_with_stream(remote_path)

        assert list(stream) == [b"chunk 1", b"chunk 2"]
        mock_local_storage.download_file_with_stream_mock.assert_called_once_with(
            remote_path
        )

    def test_delete_file_proxies_correctly(
        self, manager_with_local, mock_local_storage
    ):
        remote_path = "test/obsolete.txt"

        result = manager_with_local.delete_file(remote_path)

        assert result is True
        mock_local_storage.delete_file_mock.assert_called_once_with(remote_path)

    def test_create_directory_proxies_correctly(
        self, manager_with_local, mock_local_storage
    ):
        remote_path = "new_dir"

        result = manager_with_local.create_directory(remote_path)

        assert result is True
        mock_local_storage.create_directory_mock.assert_called_once_with(remote_path)

    def test_delete_directory_proxies_correctly(
        self, manager_with_local, mock_local_storage
    ):
        remote_path = "old_dir"

        result = manager_with_local.delete_directory(remote_path)

        assert result is True
        mock_local_storage.delete_directory_mock.assert_called_once_with(remote_path)

    def test_list_files_proxies_correctly(self, manager_with_local, mock_local_storage):
        remote_path = "root/"
        metadata = [
            FileMetadata(name="file1.txt", path="root/file1.txt", size=100),
            DirMetadata(name="subdir", path="root/subdir"),
        ]
        mock_local_storage.list_files_mock.return_value = metadata

        result = manager_with_local.list_files(remote_path)

        assert result == metadata
        mock_local_storage.list_files_mock.assert_called_once_with(remote_path)

    def test_get_file_metadata_proxies_correctly(
        self, manager_with_local, mock_local_storage
    ):
        remote_path = "target.pdf"
        expected_metadata = FileMetadata(
            name="target.pdf", path="target.pdf", size=10240
        )
        mock_local_storage.get_file_metadata_mock.return_value = expected_metadata

        metadata = manager_with_local.get_file_metadata(remote_path)

        assert metadata == expected_metadata
        mock_local_storage.get_file_metadata_mock.assert_called_once_with(remote_path)

    def test_move_file_proxies_correctly(self, manager_with_local, mock_local_storage):
        src_path = "old/path/file.txt"
        dest_path = "new/path/file.txt"

        result = manager_with_local.move_file(src_path, dest_path)

        assert result is True
        mock_local_storage.move_file_mock.assert_called_once_with(src_path, dest_path)

    def test_copy_file_proxies_correctly(self, manager_with_local, mock_local_storage):
        src_path = "source.jpg"
        dest_path = "copy_of_source.jpg"

        result = manager_with_local.copy_file(src_path, dest_path)

        assert result is True
        mock_local_storage.copy_file_mock.assert_called_once_with(src_path, dest_path)

    def test_get_directory_size_proxies_correctly(
        self, manager_with_local, mock_local_storage
    ):
        remote_path = "media"
        mock_local_storage.get_directory_size_mock.return_value = 2048

        result = asyncio.run(manager_with_local.get_directory_size(remote_path))

        assert result == 2048
        mock_local_storage.get_directory_size_mock.assert_awaited_once_with(remote_path)

    def test_search_proxies_correctly(self, manager_with_local, mock_local_storage):
        mock_local_storage.search_mock.return_value = [
            FileMetadata(name="match.txt", path="docs/match.txt")
        ]

        result = asyncio.run(manager_with_local.search("match", "docs", 0, 10))

        assert result == [FileMetadata(name="match.txt", path="docs/match.txt")]
        mock_local_storage.search_mock.assert_awaited_once_with("match", "docs", 0, 10)

    def test_proxy_raises_error_if_no_current_backend(self, mock_local_storage):
        manager = StorageManager()

        with pytest.raises(
            BackendNotFoundError,
            match="current storage backend is not set or cannot be found",
        ):
            manager.exists("any/path")
