import asyncio
import sys
import tarfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import (
    Dict,
    Optional,
    Generator,
    AsyncIterator,
    List,
    AsyncGenerator,
)

import ulid
from nicegui import app

from api import download_form_browser_url_prefix
from config import settings
from models.file_download_model import FileDownloadInfo
from schemas.file_schema import FileMetadata, DirMetadata, FileType, FileSource
from security import generate_jwt_secret
from storage.base import StorageBackend
from storage.local_storage import LocalStorage
from ui.components.notify import notify
from utils import logger, _

storage_key = "temp_public_download_key"


def get_file_icon(type_: str, extension: str):
    if type_ == "dir":
        return "📁"  # 文件夹

    if not extension:
        return "❓"

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


class AsyncStreamWriter:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.closed = False

    def write(self, data: bytes):
        if data:
            self.queue.put_nowait(data)

    def flush(self):
        pass

    def close(self):
        self.closed = True

    async def __aiter__(self):
        while not self.closed or not self.queue.empty():
            chunk = await self.queue.get()
            yield chunk


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

    async def download_file_with_compressed_stream(
        self,
        relative_paths: List[str],
        base_dir_path: str,
    ) -> AsyncGenerator[bytes, None]:
        """
        tar.gz 流式压缩下载
        """

        writer = AsyncStreamWriter()
        loop = asyncio.get_running_loop()

        def tar_worker():
            try:
                with tarfile.open(
                    mode="w|gz",
                    fileobj=writer,
                    format=tarfile.PAX_FORMAT,
                    bufsize=settings.STREAM_CHUNK_SIZE,
                ) as tar:

                    base_dir = self.get_full_path(base_dir_path)
                    for rel in relative_paths:
                        if not self.exists(rel):
                            continue

                        full_path = self.get_full_path(rel)
                        arcname = full_path.relative_to(base_dir)
                        tar.add(full_path, arcname=str(arcname), recursive=True)
            finally:
                writer.close()

        # 后台线程执行压缩
        loop.run_in_executor(None, tar_worker)
        # 实时返回
        async for chunk in writer:
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

    async def get_directory_size(self, remote_path: str) -> int:
        backend = self._get_current_backend()
        return await backend.get_directory_size(remote_path)

    async def search(
        self, query: str, remote_path: str, offset: int, limit: int
    ) -> list[FileMetadata | DirMetadata]:
        backend = self._get_current_backend()
        return await backend.search(query, remote_path, offset, limit)


async def generate_download_url(
    target_path: str | list[str],
    name: str | list[str],
    type_: FileType,
    source: FileSource,
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

    download_id = ulid.new().str
    download_info = {
        "name": name,
        "type": type_,
        "path": target_path,
        "base_path": app.storage.user["last_path"],
        "user": app.storage.user["username"],
        "source": source,
        "exp": this_url_ttl,
    }

    if storage_key not in app.storage.general:
        app.storage.general[storage_key] = {}

    payload = {"download_id": download_id}
    if this_url_ttl:
        payload.update({"exp": int(this_url_ttl.timestamp())})

    if source == "download":
        url = (
            app.storage.general["service_url"]
            + f"/api/{download_form_browser_url_prefix}/{generate_jwt_secret(payload)}"
        )
    elif source == "share":
        url = (
            app.storage.general["service_url"]
            + f"/share/{generate_jwt_secret(payload)}"
        )
    else:
        raise ValueError(_("Invalid source parameter."))

    download_info.update({"url": url})

    # ULID 在 python 字典中作为 key 的性能还是非常好的
    # 同时考虑到 app.storage.general 使用本地文件持久化，所以此处暂时不用数据库存储
    #
    # download_info_db = FileDownloadInfo(
    #     download_id=download_id,
    #     **download_info,
    # )
    # async with async_session() as session:
    #     async with session.begin():
    #         session.add(download_info_db)

    app.storage.general[storage_key][download_id] = download_info
    return url


def get_download_info(download_id: str) -> Optional[FileDownloadInfo]:
    """
    获取下载链接信息。
    """
    if storage_key not in app.storage.general:
        app.storage.general[storage_key] = {}

    if download_id not in app.storage.general[storage_key]:
        return None

    return FileDownloadInfo(**app.storage.general[storage_key][download_id])


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
            if download_info["source"] == "share":
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


WINDOWS_FORBIDDEN_CHARS = (
    r'<>:"|?*'  # 移除了 /\\，因为 / 和 \ 在 allow_subdirs=True 时是路径分隔符
)
# 针对单个文件名，所有这些字符都是禁止的。
# 但为了路径解析的兼容性，将 : / \ 留给 PurePath 处理
FULL_FORBIDDEN_CHARS = r'<>:"/\\|?*'

WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

MAX_FILENAME_LENGTH = 255


def is_windows_reserved(name_part: str) -> bool:
    """检查是否为 Windows 保留名称 (支持带扩展名的形式)"""
    name_part = name_part.upper().strip()

    # 检查完整的保留名称 (例如 "CON")
    if name_part in WINDOWS_RESERVED_NAMES:
        return True

    # 检查带扩展名的保留名称 (例如 "CON.TXT")
    if "." in name_part:
        # 取点号之前的部分
        base_name = name_part.split(".", 1)[0]
        if base_name in WINDOWS_RESERVED_NAMES:
            return True

    return False


def validate_filename(name: str, allow_subdirs: bool = False) -> tuple[bool, str]:
    """
    跨平台文件/目录名称验证 (完善版)

    :param name: 用户输入的名称
    :param allow_subdirs: 是否允许使用路径分隔符来创建子目录
    :return: (合法性: bool, 提示信息: str)
    """
    # 1. 初始检查
    if not name or not name.strip():
        return False, _("Name cannot be empty or only spaces.")

    name = name.strip()

    # 2. 长度检查
    if len(name) > MAX_FILENAME_LENGTH:
        return False, _("Name is too long (max {} characters).").format(
            MAX_FILENAME_LENGTH
        )

    # 3. 路径解析和穿越检查 (仅当允许子目录时)
    if allow_subdirs:
        # 检查开头是否为路径分隔符
        if name.startswith("/") or name.startswith("\\"):
            return False, _(
                "Name cannot start with a path separator (must be a relative path)."
            )
        try:
            # 使用 Path 而非 PurePath，检查更严格
            path = Path(name)
        except Exception:
            # 处理 Path 无法解析的极端情况 (如空字符)
            return False, _("Invalid path format.")

        # 路径穿越检查
        # 检查是否包含 '..' (相对父目录)
        if ".." in path.parts:
            return False, _("Name cannot contain '..' to traverse directories.")

        # 检查是否为绝对路径 (例如以 / 或 C: 开头)
        if path.is_absolute():
            return False, _(
                "Name cannot start with a path separator or drive letter (must be relative)."
            )

        # 需要检查的名称部分
        parts_to_check = path.parts
        # 确保路径分隔符 (/, \) 本身不被视为待检查的禁用字符
        chars_to_check = WINDOWS_FORBIDDEN_CHARS

    else:
        # 仅检查单个名称
        parts_to_check = [name]
        # 如果不允许子目录，则所有的路径分隔符也是禁用字符
        chars_to_check = FULL_FORBIDDEN_CHARS

    # 4. 核心系统特定检查
    is_win = sys.platform.startswith("win")

    for part in parts_to_check:
        if not part:  # 跳过空部分 (例如 // 或 a//b)
            continue

        # 4.1. Linux/Unix 特定检查 (不允许路径分隔符作为名称的一部分)
        # 注意：当 allow_subdirs=True 时，此检查被跳过
        if not is_win and not allow_subdirs and "/" in part:
            return False, _("Name cannot contain '/' in Linux/Unix.")

        # 4.2. Windows 特定检查
        # if is_win:

        # 禁用字符检查
        if any(char in part for char in chars_to_check):
            return False, _("Name cannot contain any of these characters: {}").format(
                chars_to_check
            )

        # 保留名称检查 (完善后的函数)
        if is_windows_reserved(part):
            return False, _("Name segment '{}' is a reserved system name.").format(part)

        # 结尾检查
        if part.endswith(".") or part.endswith(" "):
            return False, _("Name segment cannot end with a dot or space.")

        # Windows 不允许 : 字符 (除了作为驱动器分隔符 C:)
        # 注意: 如果 name 是 "a:b"，Path() 会把它解释为驱动器，导致 path.parts 只有一个元素 "a:b"
        # 这里依赖 FULL_FORBIDDEN_CHARS 包含了 ":" 来处理单文件名的禁止。
        # 如果 allow_subdirs=True，: 也不在 WINDOWS_FORBIDDEN_CHARS 中，Path(C:/a) 才是合法的驱动器。
        # 这里不再重复检查 :，因为它已被 Path 解析或被 FULL_FORBIDDEN_CHARS 包含。

    return True, _("Name is valid.")
