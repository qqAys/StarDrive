import asyncio
import os
import shutil
from pathlib import Path
from typing import AsyncIterator, List, NamedTuple, Optional

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
                        extension=entry_path.suffix if entry_path.suffix else None,
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
                extension=full_path.suffix if full_path.suffix else None,
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

    # 辅助函数：在线程中同步地递归搜索文件
    @staticmethod
    def _synchronous_recursive_search(
        start_path: Path,
        query: str,
        match_case: bool,
        file_only: bool,
    ) -> List[Path]:
        """
        同步递归遍历文件系统，实现带深度限制的搜索。
        该函数设计为在 asyncio.to_thread 中运行。
        """
        found_paths = []

        def traverse(current_path: Path, current_depth: int):

            try:
                # 遍历当前目录下的所有文件和子目录
                for entry_path in current_path.iterdir():

                    # 排除隐藏文件/目录
                    if entry_path.name.startswith("."):
                        continue

                    name_to_match = entry_path.name
                    search_query = query

                    if not match_case:
                        name_to_match = name_to_match.lower()
                        search_query = query.lower()

                    # 1. 检查是否匹配查询
                    # 检查文件名是否包含查询字符串（更像模糊搜索）
                    if search_query in name_to_match:
                        is_dir = entry_path.is_dir()

                        if file_only and is_dir:
                            # 如果只搜索文件，跳过目录
                            pass
                        else:
                            # 匹配成功，添加到结果列表
                            found_paths.append(entry_path)

                    # 2. 如果是目录，继续递归搜索
                    if entry_path.is_dir():
                        traverse(entry_path, current_depth + 1)

            except PermissionError:
                # 忽略没有权限访问的目录
                logger.warning(
                    _("Permission denied accessing directory: {}").format(current_path)
                )
            except Exception as e:
                logger.error(
                    _("Error during sync search in {}: {}").format(current_path, e)
                )

        # 启动递归搜索，初始深度为 0 (相对于 start_path)
        traverse(start_path, 0)
        return found_paths

    async def search(
        self,
        query: str,
        remote_path: str = "/",
        match_case: bool = False,
        file_only: bool = False,
    ) -> List[FileMetadata | DirMetadata]:
        """
        使用 asyncio.to_thread 实现异步非阻塞文件搜索，支持深度限制。

        :param query: 要搜索的文件名模式（模糊匹配，包含）。
        :param remote_path: 开始搜索的虚拟路径（相对于 root_path）。
        :param match_case: 是否区分大小写。
        :param file_only: 是否只返回文件（True）或文件和目录（False）。
        :return: 匹配到的文件元数据列表。
        """
        start_full_path = self._get_full_path(remote_path)

        if not start_full_path.exists():
            raise StorageFileNotFoundError(
                _("Search path does not exist: {}").format(remote_path)
            )

        logger.debug(
            _("Starting deep search from {} with query '{}'").format(
                start_full_path, query
            )
        )

        try:
            # 1. 异步执行同步递归搜索（I/O 阻塞操作）
            # 这将整个文件系统遍历操作移到后台线程中运行，不阻塞主事件循环。
            found_paths = await asyncio.to_thread(
                self._synchronous_recursive_search,
                start_full_path,
                query,
                match_case,
                file_only,
            )

            # 2. 将本地路径转换为元数据（大量 stat() I/O 阻塞）

            # 定义一个辅助函数来获取单个文件的元数据
            def get_single_metadata(path: Path) -> FileMetadata | DirMetadata | None:
                # 安全检查，确保路径在我们定义的根目录内
                if not path.is_relative_to(self.root_path):
                    return None

                remote_path_str = path.relative_to(self.root_path).as_posix()

                try:
                    # stat() 操作是 I/O 阻塞的
                    stat_info = parse_path_stat(path.stat())
                    is_dir = path.is_dir()

                    if is_dir:
                        return DirMetadata(
                            name=path.name,
                            path=remote_path_str,
                            size=0,
                            accessed_at=stat_info.accessed_at,
                            modified_at=stat_info.modified_at,
                            created_at=stat_info.created_at,
                            status_changed_at=stat_info.status_changed_at,
                            custom_updated_at=stat_info.custom_updated_at,
                        )
                    else:
                        return FileMetadata(
                            name=path.name,
                            path=remote_path_str,
                            extension=path.suffix if path.suffix else None,
                            size=stat_info.size,
                            accessed_at=stat_info.accessed_at,
                            modified_at=stat_info.modified_at,
                            created_at=stat_info.created_at,
                            status_changed_at=stat_info.status_changed_at,
                            custom_updated_at=stat_info.custom_updated_at,
                        )
                except Exception as e:
                    # 捕获任何 stat 错误（如文件被删除或权限改变）
                    logger.warning(f"Failed to get metadata for {path}: {e}")
                    return None

            # 3. 并行执行所有元数据获取任务
            # 将所有 stat/metadata 获取请求放入线程池，并行处理，以减少总等待时间。
            metadata_tasks = [
                asyncio.to_thread(get_single_metadata, p) for p in found_paths
            ]

            results = await asyncio.gather(*metadata_tasks)

            # 过滤掉 None 的结果（权限错误、文件丢失等）
            metadata_list = [r for r in results if r is not None]

            return metadata_list

        except StorageError:
            raise
        except Exception as e:
            raise StorageError(
                _("An unexpected error occurred during search: {}").format(e)
            ) from e
