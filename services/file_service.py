import asyncio
import io
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional, Generator, AsyncIterator, Literal, List, AsyncGenerator
from uuid import uuid4

from nicegui import app

import storage
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
    if extension in ["txt", "md", "log", "cfg", "ini", "conf"]:
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
        "toml",
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
        return "📜"

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

    def _add_to_zip(self, zip_file: zipfile.ZipFile, path: str, base_dir_path: str):
        """
        【递归辅助函数】: 将文件或目录添加到 ZIP 归档中。
        """
        # 计算文件在 ZIP 包内的路径 (arcname)。例如: BASE_DIR/img/a.jpg -> img/a.jpg
        full_path = self.get_full_path(path)
        base_dir_path = self.get_full_path(base_dir_path)
        arcname = full_path.relative_to(base_dir_path)

        if full_path.is_file():
            zip_file.write(full_path, arcname=arcname)

        elif full_path.is_dir():
            zip_file.write(full_path, arcname=arcname)
            for item in full_path.iterdir():
                self._add_to_zip(zip_file, str(item), str(base_dir_path))
        else:
            logger.warning(f"Skipping non-file/non-dir item: {arcname}")

    def _perform_zip_creation(self, zip_buffer: io.BytesIO, relative_paths: List[str], base_dir_path: str):
        """
        【同步辅助函数】: 在单独的线程中执行 ZIP 文件的创建，支持文件和文件夹。
        """
        logger.debug("Starting synchronous ZIP file creation...")

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zip_file:

            for relative_path_str in relative_paths:

                if not self.exists(relative_path_str):
                    logger.debug(f"Path not permitted or not found: {relative_path_str}. Skipping.")
                    continue

                try:
                    self._add_to_zip(zip_file, relative_path_str, base_dir_path)
                except Exception as e:
                    logger.error(f"Error processing item {relative_path_str}: {e}")
                    continue

        logger.debug("Synchronous ZIP file creation completed.")

    # 代理方法

    def exists(self, remote_path: str) -> bool:
        """检查远程路径（文件或目录）是否存在。"""
        backend = self._get_current_backend()
        return backend.exists(remote_path)

    def get_full_path(self, remote_path: str) -> Path:
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

    async def download_file_with_compressed_stream(self, relative_paths: List[str], base_dir_path: str) -> AsyncGenerator[bytes, None]:
        """ZIP 压缩流式返回"""
        zip_buffer = io.BytesIO()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._perform_zip_creation, zip_buffer, relative_paths, base_dir_path)

        zip_buffer.seek(0)

        while True:
            chunk = await loop.run_in_executor(None, zip_buffer.read, settings.STREAM_CHUNK_SIZE)

            if not chunk:
                break
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


def generate_download_url(
    target_path: str | list[str],
    file_name: str | list[str],
    from_: Literal["download", "share"],
    expire_datetime_utc: Optional[datetime] = None,
    expire_days: Optional[int] = None,
) -> str | None:
    """
    生成下载链接。
    """
    if not app.storage.general.get("service_url", None):
        notify.error(
            _(
                "Service URL is not set. Please set it in the console panel before sharing files."
            )
        )
        return None
    current_time_utc = datetime.now(settings.SYSTEM_DEFAULT_TIMEZONE)
    this_url_ttl: Optional[datetime] = None

    if isinstance(expire_days, int) and expire_days > 0:
        this_url_ttl = current_time_utc + timedelta(days=expire_days)

    elif isinstance(expire_datetime_utc, datetime):
        # 传入了具体的 datetime 对象
        this_url_ttl = expire_datetime_utc

    elif expire_datetime_utc is None and expire_days is None:
        # 既没有指定时间，也没有指定天数，使用配置文件中的默认 TTL
        this_url_ttl = current_time_utc + settings.DEFAULT_DOWNLOAD_LINK_TTL

    download_id = uuid4().hex[:12]
    download_info = {
        "user": app.storage.user["username"],
        "base_path": app.storage.user["last_path"],
        "path": target_path,
        "name": file_name,
        "from": from_,
        "exp": this_url_ttl.isoformat() if this_url_ttl else None,
    }

    if storage_key not in app.storage.general:
        app.storage.general[storage_key] = {}

    payload = {"download_id": download_id}
    if this_url_ttl:
        payload.update({"exp": int(this_url_ttl.timestamp())})

    if from_ == "download":
        url = (
            app.storage.general["service_url"]
            + f"/api/{download_file_form_browser_url_prefix}/{generate_jwt_secret(payload)}"
        )
    elif from_ == "share":
        url = (
            app.storage.general["service_url"]
            + f"/share/{generate_jwt_secret(payload)}"
        )
    else:
        raise ValueError(_("Invalid from parameter."))

    download_info.update({"url": url})
    app.storage.general[storage_key][download_id] = download_info
    return url


def get_download_info(download_id: str) -> dict | None:
    """
    获取下载链接信息。
    """
    if storage_key not in app.storage.general:
        app.storage.general[storage_key] = {}

    return app.storage.general[storage_key].get(download_id, None)


def delete_download_link(download_id: str):
    """
    删除下载链接。
    """
    if storage_key not in app.storage.general:
        app.storage.general[storage_key] = {}

    if download_id in app.storage.general[storage_key]:
        del app.storage.general[storage_key][download_id]


def clear_expired_download_links():
    """
    清理过期的下载链接。
    """

    if storage_key not in app.storage.general:
        app.storage.general[storage_key] = {}

    download_keys_to_check = list(app.storage.general[storage_key].keys())

    current_time_utc = datetime.now(timezone.utc)

    result = {
        "expired": [],
        "valid": [],
    }

    for download_id in download_keys_to_check:
        if download_id not in app.storage.general[storage_key]:
            continue

        download_info = app.storage.general[storage_key][download_id]
        exp_datetime = datetime.fromisoformat(download_info["exp"])

        if exp_datetime < current_time_utc:
            result["expired"].append(download_id)

            delete_download_link(download_id)
        else:
            result["valid"].append(download_id)

    notify.info(
        _("Cleaned up expired download links, Valid: {}, Expired: {}").format(
            len(result["valid"]), len(result["expired"])
        )
    )


def get_user_share_links(file_name: str | None = None) -> list[dict]:
    """
    获取用户分享链接。
    """
    if storage_key not in app.storage.general:
        app.storage.general[storage_key] = {}

    share_links = []

    for download_id, download_info in app.storage.general[storage_key].items():
        if app.storage.user["username"] == download_info["user"]:
            if download_info["from"] == "share":
                if file_name is None or file_name == download_info["name"]:
                    share_links.append({"id": download_id, "info": download_info})

    return share_links


def set_user_last_path(path):
    """
    设置用户最近一次访问的路径。
    """
    app.storage.user["last_path"] = str(path)


def get_user_last_path() -> str | None:
    """
    获取用户最近一次访问的路径。
    """
    return app.storage.user.get("last_path", None)
