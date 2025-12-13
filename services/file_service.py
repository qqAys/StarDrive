from typing import Dict, Optional, BinaryIO, Generator

from schemas.file_schema import FileMetadata, DirMetadata
from storage.base import StorageBackend
from storage.local_storage import LocalStorage
from utils import logger, _


def get_file_icon(type_: str, extension: str):
    if type_ == "dir":
        return "📁"  # 文件夹

    if not extension.strip():
        return "❓"
    else:
        extension = extension.replace(".", "")

    # --- 文档/文本文件 ---
    if extension in ["txt", "md", "log", "cfg", "ini"]:
        return "📄"
    elif extension in ["doc", "docx", "odt", "rtf"]:
        return "📝"
    elif extension == "pdf":
        return "📕"

    # --- 代码/脚本 ---
    elif extension in ["py", "js", "ts", "html", "css", "scss", "json", "xml", "yaml", "yml", "java", "c", "cpp", "h",
                       "hpp", "go", "rb", "php", "sh", "bat"]:
        return "💻"

    # --- 压缩/归档文件 ---
    elif extension in ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso"]:
        return "📦"

    # --- 图像文件 ---
    elif extension in ["jpg", "jpeg", "png", "gif", "svg", "ico", "bmp", "webp", "tiff"]:
        return "🖼️"

    # --- 媒体文件 ---
    elif extension in ["mp4", "avi", "mov", "wmv", "flv", "mkv"]:
        return "🎬"
    elif extension in ["mp3", "wav", "flac", "ogg", "aac", "m4a"]:
        return "🎵"

    # --- 办公/数据文件 ---
    elif extension in ["xls", "xlsx", "csv", "ods"]:
        return "📈"
    elif extension in ["ppt", "pptx", "odp"]:
        return "🖥️"
    elif extension in ["db", "sqlite", "mdb", "accdb"]:
        return "🗃️"

    # --- 可执行/系统文件 ---
    elif extension in ["exe", "dll", "msi", "app", "apk", "dmg"]:
        return "⚙️"

    # --- 字体文件 ---
    elif extension in ["ttf", "otf", "woff", "woff2"]:
        return "🅰️"

    # --- 通用/未知文件---
    else:
        return "❓"


class BackendNotFoundError(Exception):
    """存储后端未找到的异常。"""

    pass


class StorageManager:
    """
    存储管理器：负责注册、切换和代理所有存储操作给当前活跃的后端。
    """

    def __init__(self):
        # 存储所有已注册的后端实例
        self._backends: Dict[str, StorageBackend] = {}
        # 当前正在使用的存储后端名称
        self._current_backend_name: Optional[str] = None

        # 注册本地存储后端
        self.register_backend(LocalStorage.name, LocalStorage())

    def register_backend(self, name: str, backend_instance: StorageBackend):
        """
        注册一个新的存储后端。
        :param name: 存储后端的唯一标识。
        :param backend_instance: 实现了 StorageBackend 接口的实例。
        """
        if not isinstance(backend_instance, StorageBackend):
            raise TypeError(
                _("Object {} does not implement the StorageBackend interface.").format(
                    backend_instance.__class__.__name__
                )
            )

        if name in self._backends:
            raise ValueError(_("Storage backend '{}' already exists.").format(name))

        self._backends[name] = backend_instance
        logger.debug(_("Storage backend '{}' has been registered.").format(name))

    def list_backends(self) -> list[str]:
        """返回已注册的所有存储后端名称。"""
        return list(self._backends.keys())

    def set_current_backend(self, name: str):
        """
        切换当前活跃的存储后端。失败时抛出 BackendNotFoundError。
        """
        if name in self._backends:
            self._current_backend_name = name
            logger.debug(_("Current storage has been switched to '{}'.").format(name))
        else:
            raise BackendNotFoundError(
                _("Storage backend '{}' is not registered.").format(name)
            )

    def _get_current_backend(self) -> StorageBackend:
        """获取当前活跃的存储后端实例。失败时抛出 BackendNotFoundError。"""
        if (
            not self._current_backend_name
            or self._current_backend_name not in self._backends
        ):
            raise BackendNotFoundError(
                _(
                    "The current storage backend is not set or cannot be found. Please call set_current_backend() first."
                )
            )
        return self._backends[self._current_backend_name]

    # 代理方法

    def exists(self, remote_path: str) -> bool:
        """检查远程路径（文件或目录）是否存在。"""
        backend = self._get_current_backend()
        return backend.exists(remote_path)

    def upload_file(self, file_object: BinaryIO, remote_path: str) -> bool:
        """流式上传文件。"""
        backend = self._get_current_backend()
        backend.upload_file(file_object, remote_path)
        return True

    def upload_file_from_path(self, local_path: str, remote_path: str) -> bool:
        """从本地路径上传文件。"""
        backend = self._get_current_backend()
        backend.upload_file_from_path(local_path, remote_path)
        return True

    def download_file(self, remote_path: str) -> bytes:
        """下载文件。"""
        backend = self._get_current_backend()
        return backend.download_file(remote_path)

    def download_file_with_stream(
        self, remote_path: str
    ) -> Generator[bytes, None, None]:
        """流式下载文件。"""
        backend = self._get_current_backend()
        for chunk in backend.download_file_with_stream(remote_path):
            yield chunk

    def delete_file(self, remote_path: str) -> bool:
        """删除远程文件。"""
        backend = self._get_current_backend()
        backend.delete_file(remote_path)
        return True

    def list_files(self, remote_path: str) -> list[FileMetadata | DirMetadata]:
        """列出目录下的文件元数据。"""
        backend = self._get_current_backend()
        return backend.list_files(remote_path)

    def create_directory(self, remote_path: str) -> bool:
        """创建远程目录。"""
        backend = self._get_current_backend()
        backend.create_directory(remote_path)
        return True

    def delete_directory(self, remote_path: str) -> bool:
        """删除远程目录。"""
        backend = self._get_current_backend()
        backend.delete_directory(remote_path)
        return True

    def move_file(self, src_path: str, dest_path: str) -> bool:
        """移动文件或目录。"""
        backend = self._get_current_backend()
        backend.move_file(src_path, dest_path)
        return True

    def copy_file(self, src_path: str, dest_path: str) -> bool:
        """复制文件。"""
        backend = self._get_current_backend()
        backend.copy_file(src_path, dest_path)
        return True

    def get_file_metadata(self, remote_path: str) -> FileMetadata | DirMetadata:
        """获取单个文件或目录的元数据。"""
        backend = self._get_current_backend()
        return backend.get_file_metadata(remote_path)
