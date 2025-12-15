import asyncio
import shutil
from pathlib import Path
from typing import AsyncIterator

import aiofiles

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
                stat_info = entry_path.stat()
                is_dir = entry_path.is_dir()

                if is_dir:
                    metadata = DirMetadata(
                        name=entry_path.name,
                        path=entry_remote_path,
                        size=0,
                        created_at=stat_info.st_birthtime,
                        updated_at=stat_info.st_ctime,
                        num_children=len(list(entry_path.iterdir())),
                    )
                else:
                    metadata = FileMetadata(
                        name=entry_path.name,
                        path=entry_remote_path,
                        extension=entry_path.suffix,
                        size=stat_info.st_size,
                        created_at=stat_info.st_birthtime,
                        updated_at=stat_info.st_ctime,
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

        stat_info = full_path.stat()
        is_dir = full_path.is_dir()

        if is_dir:
            return DirMetadata(
                name=full_path.name,
                path=remote_path,
                size=0,
                created_at=stat_info.st_birthtime,
                updated_at=stat_info.st_ctime,
                num_children=len(list(full_path.iterdir())),
            )
        else:
            return FileMetadata(
                name=full_path.name,
                path=remote_path,
                extension=full_path.suffix,
                size=stat_info.st_size,
                created_at=stat_info.st_birthtime,
                updated_at=stat_info.st_ctime,
            )
