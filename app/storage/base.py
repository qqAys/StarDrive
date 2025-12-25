from abc import ABC, abstractmethod
from typing import BinaryIO, AsyncIterator

from app.schemas.file_schema import FileMetadata, DirMetadata


# Base exception for storage-related errors
class StorageError(Exception):
    """Base exception class for all storage backend errors."""


# Configuration and connectivity exceptions
class StorageConfigurationError(StorageError):
    """Raised when the storage backend is misconfigured."""


class StorageConnectionError(StorageError):
    """Raised when the storage backend cannot establish a connection."""


class StorageAuthenticationError(StorageError):
    """Raised when authentication to the storage backend fails."""


# File system-level exceptions
class StorageFileError(StorageError):
    """Base exception for file or directory operation errors."""


class StorageFileNotFoundError(StorageFileError):
    """Raised when a requested file or directory does not exist."""


class StorageFileExistsError(StorageFileError):
    """Raised when attempting to create a file or directory that already exists."""


class StorageIsADirectoryError(StorageFileError):
    """Raised when a file operation is applied to a directory."""


class StorageNotADirectoryError(StorageFileError):
    """Raised when a directory operation is applied to a file."""


class StoragePermissionError(StorageFileError):
    """Raised when the operation is denied due to insufficient permissions."""


class StorageBackend(ABC):
    """
    Abstract base class defining the interface for all storage backends.
    Implementations must support file and directory operations with consistent semantics.
    """

    name: str

    @abstractmethod
    def exists(self, remote_path: str) -> bool:
        """
        Check whether a file or directory exists at the given path.
        """

    @abstractmethod
    def get_full_path(self, remote_path: str) -> str:
        """
        Return the absolute or normalized full path for the given remote path.
        """

    @abstractmethod
    async def upload_file(
        self, file_object: AsyncIterator[bytes], remote_path: str
    ) -> None:
        """
        Upload a file from an async byte stream to the specified remote path.
        """

    @abstractmethod
    def download_file(self, remote_path: str) -> bytes:
        """
        Download the entire content of a file as bytes.
        """

    @abstractmethod
    def download_file_with_stream(self, remote_path: str) -> BinaryIO:
        """
        Return a readable binary stream for the file at the given path.
        The caller is responsible for closing the stream.
        """

    @abstractmethod
    def delete_file(self, remote_path: str) -> None:
        """
        Delete the file at the specified path.
        Raises StorageFileNotFoundError if the file does not exist.
        """

    @abstractmethod
    def list_files(self, remote_path: str) -> list[FileMetadata | DirMetadata]:
        """
        List all items (files and directories) in the specified directory.
        Returns a list of metadata objects.
        """

    @abstractmethod
    def create_directory(self, remote_path: str) -> None:
        """
        Create a new directory at the specified path.
        Raises StorageFileExistsError if the path already exists.
        """

    @abstractmethod
    def delete_directory(self, remote_path: str) -> None:
        """
        Delete an empty directory at the specified path.
        Raises StorageFileNotFoundError if the directory does not exist,
        or StorageIsADirectoryError if it contains items (implementation-dependent).
        """

    @abstractmethod
    def move_file(self, src_path: str, dest_path: str) -> None:
        """
        Move or rename a file or directory from src_path to dest_path.
        """

    @abstractmethod
    def copy_file(self, src_path: str, dest_path: str) -> None:
        """
        Copy a file from src_path to dest_path.
        """

    @abstractmethod
    def get_file_metadata(self, remote_path: str) -> FileMetadata | DirMetadata:
        """
        Retrieve metadata (e.g., size, type, modification time) for the item at the given path.
        """

    @abstractmethod
    async def get_directory_size(self, remote_path: str) -> int:
        """
        Calculate and return the total size (in bytes) of all files within a directory recursively.
        """

    @abstractmethod
    async def search(
        self, query: str, remote_path: str, offset: int, limit: int
    ) -> list[FileMetadata | DirMetadata]:
        """
        Search for files and directories matching the query within the given path.
        Supports pagination via offset and limit.
        """
