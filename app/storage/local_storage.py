import asyncio
import os
import shutil
from collections import deque
from pathlib import Path
from typing import AsyncIterator, NamedTuple, Optional, Iterator

import aiofiles

from app.config import settings
from app.core.i18n import _
from app.core.logging import logger
from app.core.paths import STORAGE_DIR
from app.schemas.file_schema import FileMetadata, DirMetadata
from app.storage.base import (
    StorageBackend,
    StorageFileNotFoundError,
    StorageFileExistsError,
    StorageIsADirectoryError,
    StorageNotADirectoryError,
    StoragePermissionError,
    StorageError,
)


class PathStat(NamedTuple):
    """Custom named tuple representing file or directory metadata."""

    size: int
    accessed_at: Optional[float]
    modified_at: Optional[float]
    created_at: Optional[float]
    status_changed_at: Optional[float]
    custom_updated_at: Optional[float]


def parse_path_stat(stat: os.stat_result) -> PathStat:
    """
    Parse an `os.stat_result` into a platform-aware `PathStat` object.

    This function handles cross-platform differences in how file timestamps are interpreted:
    - On Windows, `st_ctime` represents the file creation time.
    - On Unix-like systems (Linux/macOS), `st_ctime` represents the last status change time,
      and file creation time (if available) is accessed via `st_birthtime`.
    """
    size = stat.st_size
    accessed_at = stat.st_atime
    modified_at = stat.st_mtime

    created_at = None
    status_changed_at = None
    custom_updated_at = None

    current_system = settings.SYSTEM_NAME

    if current_system == "Windows":
        # On Windows, st_ctime is the creation time
        created_at = stat.st_ctime
        custom_updated_at = accessed_at
    elif current_system in ["Linux", "Darwin"]:
        # On Linux/macOS, st_ctime is the last status change time
        status_changed_at = stat.st_ctime
        custom_updated_at = stat.st_ctime

        # Attempt to retrieve true creation time if supported by the filesystem
        if hasattr(stat, "st_birthtime"):
            created_at = stat.st_birthtime
        # Note: On Linux, st_birthtime availability depends on the filesystem (e.g., ext4).
        # If unavailable, created_at remains None.
    else:
        # Fallback for other systems (e.g., BSD): treat st_ctime as status change time
        status_changed_at = stat.st_ctime

    return PathStat(
        size=size,
        accessed_at=accessed_at,
        modified_at=modified_at,
        created_at=created_at,
        status_changed_at=status_changed_at,
        custom_updated_at=custom_updated_at,
    )


class LocalStorage(StorageBackend):
    """
    Implementation of a local file system storage backend.

    This class provides methods to manage files and directories within a designated root directory,
    ensuring security by restricting access to paths outside the root.
    """

    name: str = "LocalStorage"
    default_root_path: str = STORAGE_DIR
    MAX_SEARCH_DEPTH = 5
    MAX_SEARCH_RESULTS = 2000

    def __init__(self, root_path: str = default_root_path):
        self.root_path = Path(root_path).resolve()
        # Ensure the root directory exists
        if not self.root_path.is_dir():
            self.root_path.mkdir(parents=True, exist_ok=True)
        logger.debug(
            _("LocalStorage initialized with root directory: {root_path}").format(
                root_path=self.root_path
            )
        )

    def _get_full_path(self, remote_path: str) -> Path:
        """
        Convert a virtual remote path to an absolute local Path object.

        Ensures the resolved path stays within the allowed root directory to prevent path traversal attacks.
        """
        remote_path_str = str(remote_path)
        stripped_remote_path = remote_path_str.lstrip("/")
        full_path = self.root_path / stripped_remote_path

        try:
            full_resolved_path = full_path.resolve(strict=False)
        except OSError as e:
            raise StorageError(
                _("Failed to parse path: {remote_path}").format(remote_path=remote_path)
            ) from e

        if not full_resolved_path.is_relative_to(self.root_path):
            raise StoragePermissionError(
                _(
                    "Access denied: path is outside the allowed root directory: {remote_path}"
                ).format(remote_path=remote_path)
            )

        return full_resolved_path

    def exists(self, remote_path: str) -> bool:
        """Check whether a file or directory exists at the given path."""
        full_path = self._get_full_path(remote_path)
        return full_path.exists()

    def get_full_path(self, remote_path: str) -> Path:
        """
        Return the absolute local path for a given remote path.

        Raises an error if the file does not exist.
        """
        full_path = self._get_full_path(remote_path)
        if not full_path.exists():
            raise StorageFileNotFoundError(
                _("File not found: {remote_path}").format(remote_path=remote_path)
            )
        return full_path

    async def upload_file(self, file_object: AsyncIterator[bytes], remote_path: str):
        """
        Upload a file by writing chunks from an async iterator to the specified remote path.

        Creates parent directories if they don't exist.
        """
        full_path: Path = self._get_full_path(remote_path)
        try:
            await asyncio.to_thread(full_path.parent.mkdir, parents=True, exist_ok=True)
            async with aiofiles.open(full_path, mode="wb") as dest_file:
                async for chunk in file_object:
                    if not chunk:
                        continue
                    await dest_file.write(chunk)
        except PermissionError as e:
            raise StoragePermissionError(
                _("Permission denied when writing to: {path}").format(path=full_path)
            ) from e
        except Exception as e:
            raise StorageError(
                _("Failed to write file to: {path}").format(path=full_path)
            ) from e

    def download_file(self, remote_path: str) -> Path:
        """
        Return the local path of an existing file for direct access.

        Raises an error if the file does not exist.
        """
        return self.get_full_path(remote_path)

    def download_file_with_stream(self, remote_path: str):
        """
        Stream the contents of a file in chunks for efficient downloading.

        Raises an error if the path points to a directory.
        """
        full_path = self._get_full_path(remote_path)
        if not full_path.exists():
            raise StorageFileNotFoundError(
                _("File not found: {remote_path}").format(remote_path=remote_path)
            )
        if full_path.is_dir():
            raise StorageIsADirectoryError(
                _("Cannot download a directory: {remote_path}").format(
                    remote_path=remote_path
                )
            )

        chunk_size = 8192
        with full_path.open("rb") as src_file:
            while True:
                chunk = src_file.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    def delete_file(self, remote_path: str):
        """
        Delete a file at the specified path.

        Raises an error if the path points to a directory or does not exist.
        """
        full_path = self._get_full_path(remote_path)
        if not full_path.exists():
            raise StorageFileNotFoundError(
                _("File not found: {remote_path}").format(remote_path=remote_path)
            )
        if full_path.is_dir():
            raise StorageIsADirectoryError(
                _(
                    "Cannot delete a directory using this method. Use delete_directory instead: {remote_path}"
                ).format(remote_path=remote_path)
            )
        try:
            full_path.unlink()
        except PermissionError as e:
            raise StoragePermissionError(
                _("Permission denied when deleting file: {remote_path}").format(
                    remote_path=remote_path
                )
            ) from e

    def list_files(self, remote_path: str) -> list[FileMetadata | DirMetadata]:
        """
        List all non-hidden files and directories in the specified directory.

        Returns metadata for each entry, excluding those starting with a dot.
        """
        if not remote_path.startswith("/"):
            full_path = self._get_full_path(remote_path)
        else:
            full_path = Path(remote_path)

        if not full_path.exists():
            raise StorageFileNotFoundError(
                _("Directory not found: {path}").format(path=full_path)
            )
        if not full_path.is_dir():
            raise StorageNotADirectoryError(
                _("Path is not a directory: {path}").format(path=full_path)
            )

        metadata_list = []
        try:
            for entry_path in full_path.iterdir():
                if entry_path.name.startswith("."):
                    continue
                entry_remote_path = entry_path.relative_to(self.root_path).as_posix()
                stat_info = parse_path_stat(entry_path.stat())
                is_dir = entry_path.is_dir()

                if is_dir:
                    metadata = DirMetadata(
                        name=entry_path.name,
                        path=entry_remote_path,
                        size=0,
                        accessed_at=stat_info.accessed_at,
                        modified_at=stat_info.modified_at,
                        created_at=stat_info.created_at,
                        status_changed_at=stat_info.status_changed_at,
                        custom_updated_at=stat_info.custom_updated_at,
                        num_children=len(list(entry_path.iterdir())),
                    )
                else:
                    metadata = FileMetadata(
                        name=entry_path.name,
                        path=entry_remote_path,
                        extension=entry_path.suffix or None,
                        size=stat_info.size,
                        accessed_at=stat_info.accessed_at,
                        modified_at=stat_info.modified_at,
                        created_at=stat_info.created_at,
                        status_changed_at=stat_info.status_changed_at,
                        custom_updated_at=stat_info.custom_updated_at,
                    )
                metadata_list.append(metadata)
        except PermissionError as e:
            raise StoragePermissionError(
                _("Permission denied when reading directory: {path}").format(
                    path=full_path
                )
            ) from e
        except Exception as e:
            raise StorageError(
                _("Failed to read directory: {error}").format(error=str(e))
            ) from e

        return metadata_list

    def create_directory(self, remote_path: str):
        """
        Create a new directory, including any necessary parent directories.

        Raises an error if a file already exists at the target path.
        """
        full_path = self._get_full_path(remote_path)
        if full_path.is_file():
            raise StorageFileExistsError(
                _("A file already exists at this path: {path}").format(path=full_path)
            )
        try:
            full_path.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise StoragePermissionError(
                _("Permission denied when creating directory: {path}").format(
                    path=full_path
                )
            ) from e

    def delete_directory(self, remote_path: str):
        """
        Recursively delete a directory and all its contents.

        Raises an error if the path points to a file or does not exist.
        """
        full_path = self._get_full_path(remote_path)
        if not full_path.exists():
            raise StorageFileNotFoundError(
                _("Directory not found: {path}").format(path=full_path)
            )
        if full_path.is_file():
            raise StorageNotADirectoryError(
                _("Path is not a directory: {path}").format(path=full_path)
            )
        try:
            shutil.rmtree(full_path)
        except OSError as e:
            raise StorageError(
                _("Failed to delete directory: {error}").format(error=str(e))
            ) from e

    def move_file(self, src_path: str, dest_path: str):
        """
        Move or rename a file or directory from source to destination.

        Creates parent directories for the destination if needed.
        """
        src_full_path = self._get_full_path(src_path)
        dest_full_path = self._get_full_path(dest_path)

        if not src_full_path.exists():
            raise StorageFileNotFoundError(
                _("Source not found: {path}").format(path=src_full_path)
            )

        dest_full_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.move(src_full_path, dest_full_path)
        except PermissionError as e:
            raise StoragePermissionError(
                _("Insufficient permissions to move from {src} to {dest}").format(
                    src=src_path, dest=dest_path
                )
            ) from e
        except Exception as e:
            raise StorageError(
                _("Move operation failed: {error}").format(error=str(e))
            ) from e

    def copy_file(self, src_path: str, dest_path: str):
        """
        Copy a file from source to destination, preserving metadata.

        The source must be a file; directories are not supported.
        """
        src_full_path = self._get_full_path(src_path)
        dest_full_path = self._get_full_path(dest_path)

        if not src_full_path.is_file():
            raise StorageFileNotFoundError(
                _("Source is not a valid file: {path}").format(path=src_full_path)
            )

        dest_full_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(src_full_path, dest_full_path)
        except PermissionError as e:
            raise StoragePermissionError(
                _("Insufficient permissions to copy from {src} to {dest}").format(
                    src=src_path, dest=dest_path
                )
            ) from e
        except Exception as e:
            raise StorageError(
                _("Copy operation failed: {error}").format(error=str(e))
            ) from e

    def get_file_metadata(self, remote_path: str) -> FileMetadata | DirMetadata:
        """
        Retrieve detailed metadata for a file or directory at the given path.
        """
        full_path = self._get_full_path(remote_path)
        if not full_path.exists():
            raise StorageFileNotFoundError(
                _("File or directory not found: {path}").format(path=full_path)
            )

        stat_info = parse_path_stat(full_path.stat())
        is_dir = full_path.is_dir()

        if is_dir:
            return DirMetadata(
                name=full_path.name,
                path=remote_path,
                size=0,
                accessed_at=stat_info.accessed_at,
                modified_at=stat_info.modified_at,
                created_at=stat_info.created_at,
                status_changed_at=stat_info.status_changed_at,
                custom_updated_at=stat_info.custom_updated_at,
                num_children=len(list(full_path.iterdir())),
            )
        else:
            return FileMetadata(
                name=full_path.name,
                path=remote_path,
                extension=full_path.suffix or None,
                size=stat_info.size,
                accessed_at=stat_info.accessed_at,
                modified_at=stat_info.modified_at,
                created_at=stat_info.created_at,
                status_changed_at=stat_info.status_changed_at,
                custom_updated_at=stat_info.custom_updated_at,
            )

    async def get_directory_size(self, remote_path: str) -> int:
        """
        Asynchronously compute the total size (in bytes) of a directory and its contents.

        Hidden files and directories are excluded. Permission errors are silently ignored.
        """
        full_path = self._get_full_path(remote_path)
        if not full_path.exists():
            raise StorageFileNotFoundError(
                _("Directory not found: {path}").format(path=full_path)
            )
        if not full_path.is_dir():
            raise StorageNotADirectoryError(
                _("Path is not a directory: {path}").format(path=full_path)
            )

        async def _get_size(path: Path) -> int:
            total_size = 0
            try:
                entries = await asyncio.to_thread(list, path.iterdir())
            except PermissionError:
                return 0
            except Exception as e:
                logger.warning(f"Failed to list directory {path}: {e}")
                return 0

            for entry in entries:
                if entry.name.startswith("."):
                    continue
                try:
                    if entry.is_file():
                        stat_info = await asyncio.to_thread(entry.stat)
                        total_size += stat_info.st_size
                    elif entry.is_dir():
                        size = await _get_size(entry)
                        total_size += size
                except PermissionError:
                    continue
                except Exception as e:
                    logger.warning(f"Failed to access {entry}: {e}")
            return total_size

        size = await _get_size(full_path)
        return size

    @staticmethod
    def _sync_search_iter(
        start_path: Path,
        query: str,
        match_case: bool,
        file_only: bool,
        max_depth: int,
        max_results: int,
    ) -> Iterator[Path]:
        """
        Perform a breadth-first search (BFS) for files/directories matching the query.

        Hidden entries are skipped. Search respects depth and result limits.
        """
        queue = deque([(start_path, 0)])
        results_count = 0
        search_term = query if match_case else query.lower()

        while queue:
            current_path, depth = queue.popleft()
            if depth > max_depth:
                continue

            try:
                for entry in current_path.iterdir():
                    if entry.name.startswith("."):
                        continue

                    name = entry.name if match_case else entry.name.lower()
                    if search_term in name:
                        if not (file_only and entry.is_dir()):
                            yield entry
                            results_count += 1
                            if results_count >= max_results:
                                return

                    if entry.is_dir():
                        queue.append((entry, depth + 1))
            except PermissionError:
                logger.warning(f"Permission denied: {current_path}")
            except Exception as e:
                logger.error(f"Search error in {current_path}: {e}")

    def _get_metadata_for_search(self, path: Path):
        """Generate metadata for a search result entry."""
        if not path.is_relative_to(self.root_path):
            return None
        try:
            stat = parse_path_stat(path.stat())
            remote_path = path.relative_to(self.root_path).as_posix()
            if path.is_dir():
                return DirMetadata(
                    name=path.name,
                    path=remote_path,
                    size=0,
                    accessed_at=stat.accessed_at,
                    modified_at=stat.modified_at,
                    created_at=stat.created_at,
                    status_changed_at=stat.status_changed_at,
                    custom_updated_at=stat.custom_updated_at,
                )
            return FileMetadata(
                name=path.name,
                path=remote_path,
                extension=path.suffix or None,
                size=stat.size,
                accessed_at=stat.accessed_at,
                modified_at=stat.modified_at,
                created_at=stat.created_at,
                status_changed_at=stat.status_changed_at,
                custom_updated_at=stat.custom_updated_at,
            )
        except Exception as e:
            logger.warning(f"Metadata failed for {path}: {e}")
            return None

    async def search_iter(
        self,
        query: str,
        remote_path: str = "/",
        match_case: bool = False,
        file_only: bool = False,
    ):
        """
        Asynchronously iterate over search results matching the query.

        Uses a thread to avoid blocking the event loop during I/O-heavy operations.
        """
        start_path = self._get_full_path(remote_path)
        if not start_path.exists():
            raise StorageFileNotFoundError(remote_path)

        iterator = await asyncio.to_thread(
            self._sync_search_iter,
            start_path,
            query,
            match_case,
            file_only,
            self.MAX_SEARCH_DEPTH,
            self.MAX_SEARCH_RESULTS,
        )

        for path in iterator:
            metadata = await asyncio.to_thread(self._get_metadata_for_search, path)
            if metadata:
                yield metadata

    async def search(
        self,
        query: str,
        remote_path: str,
        offset: int,
        limit: int,
        match_case: bool = False,
        file_only: bool = False,
    ):
        """
        Perform a paginated search for files or directories matching the query.

        Returns up to `limit` results starting from the given `offset`.
        """
        results = []
        index = 0
        async for item in self.search_iter(query, remote_path, match_case, file_only):
            if index >= offset:
                results.append(item)
                if len(results) >= limit:
                    break
            index += 1
        return results
