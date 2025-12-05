from abc import ABC, abstractmethod
from typing import BinaryIO

from schemas.file_schema import FileMetadata, DirMetadata


# 顶级存储后端基类
class StorageError(Exception):
    pass


# 操作级异常
class StorageConfigurationError(StorageError):
    pass


class StorageConnectionError(StorageError):
    pass


class StorageAuthenticationError(StorageError):
    pass


# 文件系统级异常
class StorageFileError(StorageError):
    pass


class StorageFileNotFoundError(StorageFileError):
    pass


class StorageFileExistsError(StorageFileError):
    pass


class StorageIsADirectoryError(StorageFileError):
    pass


class StorageNotADirectoryError(StorageFileError):
    pass


class StoragePermissionError(StorageFileError):
    pass


class StorageBackend(ABC):
    name: str

    @abstractmethod
    def exists(self, remote_path: str):
        pass

    @abstractmethod
    def upload_file(self, file_object: BinaryIO, remote_path: str):
        pass

    @abstractmethod
    def upload_file_from_path(self, local_path: str, remote_path: str):
        pass

    @abstractmethod
    def download_file(self, remote_path: str):
        pass

    @abstractmethod
    def download_file_with_stream(self, remote_path: str) -> BinaryIO:
        pass

    @abstractmethod
    def delete_file(self, remote_path: str):
        pass

    @abstractmethod
    def list_files(self, remote_path: str) -> list[FileMetadata | DirMetadata]:
        pass

    @abstractmethod
    def create_directory(self, remote_path: str):
        pass

    @abstractmethod
    def delete_directory(self, remote_path: str):
        pass

    @abstractmethod
    def move_file(self, src_path: str, dest_path: str):
        pass

    @abstractmethod
    def copy_file(self, src_path: str, dest_path: str):
        pass

    @abstractmethod
    def get_file_metadata(self, remote_path: str) -> FileMetadata | DirMetadata:
        pass
