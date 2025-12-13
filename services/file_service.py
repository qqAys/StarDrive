from datetime import datetime, timezone
from typing import Dict, Optional, Generator, AsyncIterator
from uuid import uuid4

from nicegui import app

from api import download_file_form_browser_url_prefix
from config import settings
from schemas.file_schema import FileMetadata, DirMetadata
from security import generate_jwt_secret
from storage.base import StorageBackend
from storage.local_storage import LocalStorage
from ui.components.notify import notify
from utils import logger, _

storage_key = "temp_public_download_key"


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
    elif extension in [
        "py",
        "js",
        "ts",
        "html",
        "css",
        "scss",
        "json",
        "xml",
        "yaml",
        "yml",
        "java",
        "c",
        "cpp",
        "h",
        "hpp",
        "go",
        "rb",
        "php",
        "sh",
        "bat",
    ]:
        return "💻"

    # --- 压缩/归档文件 ---
    elif extension in ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso"]:
        return "📦"

    # --- 图像文件 ---
    elif extension in [
        "jpg",
        "jpeg",
        "png",
        "gif",
        "svg",
        "ico",
        "bmp",
        "webp",
        "tiff",
    ]:
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
        self._get_full_path = None
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

    def get_full_path(self, remote_path: str) -> str:
        """获取远程路径的完整路径。"""
        backend = self._get_current_backend()
        return backend.get_full_path(remote_path)

    async def upload_file(
        self, file_object: AsyncIterator[bytes], remote_path: str
    ) -> bool:
        """流式上传文件。"""
        backend = self._get_current_backend()
        await backend.upload_file(file_object, remote_path)
        return True

    def download_file(self, remote_path: str):
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


def generate_download_url(target_path: str, file_name: str) -> str:
    """
    生成下载链接。
    """

    this_url_ttl = datetime.now(timezone.utc) + settings.DEFAULT_DOWNLOAD_LINK_TTL

    download_id = uuid4().hex[:12]
    download_info = {
        "user": app.storage.user["username"],
        "path": target_path,
        "name": file_name,
        "exp": this_url_ttl,
    }

    if storage_key not in app.storage.general:
        app.storage.general[storage_key] = {}

    app.storage.general[storage_key][download_id] = download_info

    payload = {"download_id": download_id, "exp": this_url_ttl}

    return (
        f"/api/{download_file_form_browser_url_prefix}/{generate_jwt_secret(payload)}"
    )


def get_download_info(download_id: str) -> dict | None:
    """
    获取下载链接信息。
    """
    if storage_key not in app.storage.general:
        app.storage.general[storage_key] = {}

    return app.storage.general[storage_key].get(download_id, None)


def clear_expired_download_links():
    """
    清理过期的下载链接。
    """

    if storage_key not in app.storage.general:
        app.storage.general[storage_key] = {}

    download_keys_to_check = list(app.storage.general[storage_key].keys())

    current_time_utc = datetime.now(timezone.utc)

    for download_id in download_keys_to_check:

        if download_id not in app.storage.general[storage_key]:
            continue

        download_info = app.storage.general[storage_key][download_id]

        exp_datetime = datetime.fromisoformat(download_info["exp"])

        if exp_datetime < current_time_utc:
            notify.info(f"清理过期下载链接 (ID: {download_id}, Exp: {download_info['exp']})")

            del app.storage.general[storage_key][download_id]