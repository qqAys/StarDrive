import asyncio
import os
import shutil
from collections import deque
from pathlib import Path
from typing import AsyncIterator, NamedTuple, Optional, Iterator

import aiofiles

from config import settings
from schemas.file_schema import FileMetadata, DirMetadata
from utils import logger, _
from .base import (
    StorageBackend,
    StorageFileNotFoundError,
    StorageFileExistsError,
    StorageIsADirectoryError,
    StorageNotADirectoryError,
    StoragePermissionError,
    StorageError,
)


class PathStat(NamedTuple):
    """文件/目录状态的自定义具名元组。"""

    size: int
    # 最后访问时间 (st_atime)
    accessed_at: Optional[float]
    # 最后修改时间 (st_mtime)
    modified_at: Optional[float]
    # 文件创建时间（仅在 Windows/macOS 上有明确含义，Linux 上可能为None）
    created_at: Optional[float]
    # 最后状态更改时间（仅在 Unix/Linux 上有明确含义，Windows 上可能为None）
    status_changed_at: Optional[float]

    # 自定义更新时间
    custom_updated_at: Optional[float]


def parse_path_stat(stat: os.stat_result) -> PathStat:
    # 提取不变的时间戳字段
    size = stat.st_size
    accessed_at = stat.st_atime
    modified_at = stat.st_mtime

    # 初始化 created_at 和 status_changed_at 为 None
    created_at = None
    status_changed_at = None
    custom_updated_at = None

    # --- 跨平台逻辑判断 st_ctime 的含义 ---

    current_system = settings.SYSTEM_NAME

    if current_system == "Windows":
        # 在 Windows 上，st_ctime 明确表示文件创建时间
        created_at = stat.st_ctime
        custom_updated_at = accessed_at

    elif current_system in ["Linux", "Darwin"]:  # Linux / macOS
        # 在 Unix/Linux/macOS 上：
        # - st_ctime 明确表示文件状态的最后更改时间（如权限、所有者变更等）
        status_changed_at = stat.st_ctime
        custom_updated_at = stat.st_ctime

        # - Windows 上代表的创建时间，在 Unix-like 系统上通常通过 st_birthtime 访问
        #   Python 的 os.stat_result 在某些系统/版本上可能包含 st_birthtime 属性
        if hasattr(stat, "st_birthtime"):
            created_at = stat.st_birthtime
        # 注意：在 Linux 上，st_birthtime 的可用性取决于文件系统（如 ext4）。
        # 如果没有，则 created_at 保持为 None。

    else:
        # 其他系统，如 BSD 等，默认将 st_ctime 视为状态更改时间
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
    本地文件系统存储后端实现。
    """

    name: str = "LocalStorage"
    default_root_path: str = "./data/storage"

    MAX_SEARCH_DEPTH = 5
    MAX_SEARCH_RESULTS = 2000

    def __init__(self, root_path: str = default_root_path):
        self.root_path = Path(root_path).resolve()

        # 确保根目录存在
        if not self.root_path.is_dir():
            self.root_path.mkdir(parents=True, exist_ok=True)
        logger.debug(
            _("LocalStorage initialized, root directory: {}").format(self.root_path)
        )

    def _get_full_path(self, remote_path: str) -> Path:
        """
        将虚拟的远程路径转换为本地的绝对 Path 对象。
        """
        remote_path_str = str(remote_path)
        stripped_remote_path = remote_path_str.lstrip("/")
        full_path = self.root_path / stripped_remote_path

        try:
            full_resolved_path = full_path.resolve(strict=False)
        except OSError as e:
            raise StorageError(
                _("Path parsing failed: {}").format(remote_path), e
            ) from e

        if not full_resolved_path.is_relative_to(self.root_path):
            raise StoragePermissionError(
                _(
                    "Path security check failed, path is outside root directory: {}"
                ).format(remote_path)
            )

        return full_resolved_path

    # 抽象方法实现

    def exists(self, remote_path: str) -> bool:
        full_path = self._get_full_path(remote_path)
        return full_path.exists()

    def get_full_path(self, remote_path: str) -> Path:
        full_path = self._get_full_path(remote_path)

        if not full_path.exists():
            raise StorageFileNotFoundError(
                _("File does not exist, cannot download: {}").format(remote_path)
            )

        return full_path

    async def upload_file(self, file_object: AsyncIterator[bytes], remote_path: str):
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
                _("Permission denied to write file to {}").format(full_path)
            ) from e
        except Exception as e:
            raise StorageError(
                _("Could not write file to {}").format(full_path), e
            ) from e

    def download_file(self, remote_path: str) -> Path:
        return self.get_full_path(remote_path)

    def download_file_with_stream(self, remote_path: str):
        full_path = self._get_full_path(remote_path)

        if not full_path.exists():
            raise StorageFileNotFoundError(
                _("File does not exist, cannot download: {}").format(remote_path)
            )
        if full_path.is_dir():
            raise StorageIsADirectoryError(
                _("Path points to a directory: {}").format(remote_path)
            )

        chunk_size = 8192
        with full_path.open("rb") as src_file:
            while True:
                chunk = src_file.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    def delete_file(self, remote_path: str):
        full_path = self._get_full_path(remote_path)

        if not full_path.exists():
            raise StorageFileNotFoundError(
                _("File does not exist, cannot delete: {}").format(remote_path)
            )
        if full_path.is_dir():
            raise StorageIsADirectoryError(
                _("Path points to a directory, please use delete_directory: {}").format(
                    remote_path
                )
            )

        try:
            full_path.unlink()
        except PermissionError as e:
            raise StoragePermissionError(
                _("Permission denied to delete file: {}").format(remote_path)
            ) from e

    def list_files(self, remote_path: str) -> list[FileMetadata | DirMetadata]:
        full_path = self._get_full_path(remote_path)

        if not full_path.exists():
            raise StorageFileNotFoundError(
                _("Directory does not exist: {}").format(remote_path)
            )
        if not full_path.is_dir():
            raise StorageNotADirectoryError(
                _("Path points to a file, not a directory: {}").format(remote_path)
            )

        metadata_list = []
        try:
            for entry_path in full_path.iterdir():
                # 排除隐藏文件/目录
                if entry_path.name.startswith("."):
                    continue

                entry_remote_path = entry_path.relative_to(self.root_path).as_posix()

                # 获取 stat 信息
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
                _("Permission denied to read directory: {}").format(remote_path)
            ) from e
        except Exception as e:
            raise StorageError(_("Failed to read directory: {}").format(e)) from e

        return metadata_list

    def create_directory(self, remote_path: str):
        full_path = self._get_full_path(remote_path)

        if full_path.is_file():
            # 路径已被文件占用
            raise StorageFileExistsError(
                _("Path is already occupied by a file: {}").format(remote_path)
            )

        try:
            full_path.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise StoragePermissionError(
                _("Permission denied to create directory: {}").format(remote_path)
            ) from e

    def delete_directory(self, remote_path: str):
        full_path = self._get_full_path(remote_path)

        if not full_path.exists():
            raise StorageFileNotFoundError(
                _("Directory does not exist, cannot delete: {}").format(remote_path)
            )
        if full_path.is_file():
            raise StorageNotADirectoryError(
                _("Path points to a file, not a directory: {}").format(remote_path)
            )

        # 递归删除目录及其内容
        try:
            shutil.rmtree(full_path)
        except OSError as e:
            # 捕获权限或其他可能错误
            raise StorageError(_("Failed to delete directory: {}").format(e)) from e

    def move_file(self, src_path: str, dest_path: str):
        src_full_path = self._get_full_path(src_path)
        dest_full_path = self._get_full_path(dest_path)

        if not src_full_path.exists():
            raise StorageFileNotFoundError(
                _("Source file/directory does not exist: {}").format(src_path)
            )

        # 确保目标父目录存在
        dest_full_path.parent.mkdir(parents=True, exist_ok=True)

        # 移动/重命名操作
        try:
            shutil.move(src_full_path, dest_full_path)
        except PermissionError as e:
            raise StoragePermissionError(
                _("Insufficient permissions for move operation: {} -> {}").format(
                    src_path, dest_path
                )
            ) from e
        except Exception as e:
            raise StorageError(_("Move operation failed: {}").format(e)) from e

    def copy_file(self, src_path: str, dest_path: str):
        src_full_path = self._get_full_path(src_path)
        dest_full_path = self._get_full_path(dest_path)

        if not src_full_path.is_file():
            # 复制文件要求源必须是文件
            raise StorageFileNotFoundError(
                _("Source file does not exist or is a directory: {}").format(src_path)
            )

        # 确保目标父目录存在
        dest_full_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(src_full_path, dest_full_path)
        except PermissionError as e:
            raise StoragePermissionError(
                _("Insufficient permissions for copy operation: {} -> {}").format(
                    src_path, dest_path
                )
            ) from e
        except Exception as e:
            raise StorageError(_("Copy operation failed: {}").format(e)) from e

    def get_file_metadata(self, remote_path: str) -> FileMetadata | DirMetadata:
        full_path = self._get_full_path(remote_path)

        if not full_path.exists():
            raise StorageFileNotFoundError(
                _("File or directory does not exist: {}").format(remote_path)
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
        异步递归计算目录大小（字节）
        """
        full_path = self._get_full_path(remote_path)

        if not full_path.exists():
            raise StorageFileNotFoundError(
                _("Directory does not exist: {}").format(remote_path)
            )
        if not full_path.is_dir():
            raise StorageNotADirectoryError(
                _("Path points to a file, not a directory: {}").format(remote_path)
            )

        async def _get_size(path: Path) -> int:
            total_size = 0
            try:
                # listdir 是耗时操作，放到线程池
                entries = await asyncio.to_thread(list, path.iterdir())
            except PermissionError:
                return 0  # 无权限则忽略
            except Exception as e:
                logger.warning(f"Failed to list directory {path}: {e}")
                return 0

            for entry in entries:
                if entry.name.startswith("."):
                    continue  # 忽略隐藏文件
                try:
                    if entry.is_file():
                        stat_info = await asyncio.to_thread(entry.stat)
                        total_size += stat_info.st_size
                    elif entry.is_dir():
                        # 递归调用
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
        同步 BFS 搜索（用于 asyncio.to_thread）
        """
        queue = deque([(start_path, 0)])
        results_count = 0

        if not match_case:
            query = query.lower()

        while queue:
            current_path, depth = queue.popleft()

            if depth > max_depth:
                continue

            try:
                for entry in current_path.iterdir():
                    if entry.name.startswith("."):
                        continue

                    name = entry.name if match_case else entry.name.lower()

                    if query in name:
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
        results = []
        index = 0

        async for item in self.search_iter(
            query,
            remote_path,
            match_case,
            file_only,
        ):
            if index >= offset:
                results.append(item)

            if len(results) >= limit:
                break

            index += 1

        return results
