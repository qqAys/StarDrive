import asyncio
import sys
import tarfile
from datetime import datetime, timedelta
from numbers import Number
from pathlib import Path
from typing import (
    Dict,
    Optional,
    Generator,
    AsyncIterator,
    List,
    AsyncGenerator, Any,
)

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from nicegui import app
from sqlalchemy import select

from app.api import download_form_browser_url_prefix
from app.config import settings
from app.core.i18n import _
from app.core.logging import logger
from app.crud.file_download_crud import FileDownloadCRUD
from app.models.file_download_model import FileDownloadInfo
from app.models.user_model import User
from app.schemas.file_schema import FileMetadata, DirMetadata, FileType, FileSource
from app.security.tokens import create_token
from app.services.local_db_service import get_db_context
from app.storage.base import StorageBackend
from app.storage.local_storage import LocalStorage
from app.ui.components.notify import notify
from app.utils.size import bytes_to_human_readable


# storage_key = "temp_public_download_key"


def get_file_icon(type_: str, extension: str):
    if type_ == "dir":
        return "📁"  # Folder
    if not extension:
        return "❓"
    if not extension.strip():
        return "❓"
    else:
        extension = extension.replace(".", "").lower()

        # --- Documents / Text Files ---
        if extension in ["txt", "md", "log", "cfg", "ini", "conf"]:
            return "📄"
        elif extension in ["doc", "docx", "odt", "rtf"]:
            return "📝"
        elif extension == "pdf":
            return "📕"

        # --- Code / Scripts ---
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

        # --- Archives / Compressed Files ---
        elif extension in ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso"]:
            return "📦"

        # --- Images ---
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

        # --- Media Files ---
        elif extension in ["mp4", "avi", "mov", "wmv", "flv", "mkv"]:
            return "🎬"
        elif extension in ["mp3", "wav", "flac", "ogg", "aac", "m4a"]:
            return "🎵"

        # --- Office / Data Files ---
        elif extension in ["xls", "xlsx", "csv", "ods"]:
            return "📈"
        elif extension in ["ppt", "pptx", "odp"]:
            return "🖥️"
        elif extension in ["db", "sqlite", "mdb", "accdb"]:
            return "🗃️"

        # --- Executables / System Files ---
        elif extension in ["exe", "dll", "msi", "app", "apk", "dmg"]:
            return "⚙️"

        # --- Font Files ---
        elif extension in ["ttf", "otf", "woff", "woff2"]:
            return "🅰️"

        # --- Generic / Unknown Files ---
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
    """Exception raised when a storage backend is not found."""


class StorageManager:
    """
    Storage Manager: responsible for registering, switching, and delegating all storage operations
    to the currently active backend.
    """

    def __init__(self):
        # Store all registered backend instances
        self._get_full_path = None
        self._backends: Dict[str, StorageBackend] = {}
        # Name of the currently active storage backend
        self._current_backend_name: Optional[str] = None
        # Register the local storage backend by default
        self.register_backend(LocalStorage.name, LocalStorage())

    def register_backend(self, name: str, backend_instance: StorageBackend):
        """
        Register a new storage backend.

        :param name: Unique identifier for the storage backend.
        :param backend_instance: Instance implementing the StorageBackend interface.
        """
        if not isinstance(backend_instance, StorageBackend):
            raise TypeError(
                _(
                    "The object '{class_name}' does not implement the StorageBackend interface."
                ).format(class_name=backend_instance.__class__.__name__)
            )
        if name in self._backends:
            raise ValueError(
                _("Storage backend '{name}' already exists.").format(name=name)
            )
        self._backends[name] = backend_instance
        logger.debug(
            _("Storage backend '{name}' has been registered.").format(name=name)
        )

    def list_backends(self) -> list[str]:
        """Return a list of names of all registered storage backends."""
        return list(self._backends.keys())

    def set_current_backend(self, name: str):
        """
        Switch to the specified storage backend as the current one.
        Raises BackendNotFoundError if the backend is not registered.
        """
        if name in self._backends:
            self._current_backend_name = name
            logger.debug(
                _("Current storage backend has been switched to '{name}'.").format(
                    name=name
                )
            )
        else:
            raise BackendNotFoundError(
                _("Storage backend '{name}' is not registered.").format(name=name)
            )

    def _get_current_backend(self) -> StorageBackend:
        """
        Retrieve the currently active storage backend instance.
        Raises BackendNotFoundError if no valid backend is set.
        """
        if (
            not self._current_backend_name
            or self._current_backend_name not in self._backends
        ):
            raise BackendNotFoundError(
                _(
                    "The current storage backend is not set or cannot be found. "
                    "Please call set_current_backend() first."
                )
            )
        return self._backends[self._current_backend_name]

    # Proxy methods

    def exists(self, remote_path: str) -> bool:
        """Check whether the given remote path (file or directory) exists."""
        backend = self._get_current_backend()
        return backend.exists(remote_path)

    def get_full_path(self, remote_path: str) -> Path:
        """Get the full local path corresponding to the given remote path."""
        backend = self._get_current_backend()
        return backend.get_full_path(remote_path)

    async def upload_file(
        self, file_object: AsyncIterator[bytes], remote_path: str
    ) -> bool:
        """Upload a file using a streaming approach."""
        backend = self._get_current_backend()
        await backend.upload_file(file_object, remote_path)
        return True

    def download_file(self, remote_path: str):
        """Download a file."""
        backend = self._get_current_backend()
        return backend.download_file(remote_path)

    def download_file_with_stream(
        self, remote_path: str
    ) -> Generator[bytes, None, None]:
        """Stream-download a file in chunks."""
        backend = self._get_current_backend()
        for chunk in backend.download_file_with_stream(remote_path):
            yield chunk

    async def download_file_with_compressed_stream(
        self,
        relative_paths: List[str],
        base_dir_path: str,
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream-compress and download multiple files as a tar.gz archive.
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

        # Run compression in a background thread
        loop.run_in_executor(None, tar_worker)

        # Yield compressed chunks as they become available
        async for chunk in writer:
            yield chunk

    def delete_file(self, remote_path: str) -> bool:
        """Delete a remote file."""
        backend = self._get_current_backend()
        backend.delete_file(remote_path)
        return True

    def list_files(self, remote_path: str) -> list[FileMetadata | DirMetadata]:
        """List metadata of files and directories under the given remote path."""
        backend = self._get_current_backend()
        return backend.list_files(remote_path)

    def create_directory(self, remote_path: str) -> bool:
        """Create a remote directory."""
        backend = self._get_current_backend()
        backend.create_directory(remote_path)
        return True

    def delete_directory(self, remote_path: str) -> bool:
        """Delete a remote directory."""
        backend = self._get_current_backend()
        backend.delete_directory(remote_path)
        return True

    def move_file(self, src_path: str, dest_path: str) -> bool:
        """Move a file or directory."""
        backend = self._get_current_backend()
        backend.move_file(src_path, dest_path)
        return True

    def copy_file(self, src_path: str, dest_path: str) -> bool:
        """Copy a file."""
        backend = self._get_current_backend()
        backend.copy_file(src_path, dest_path)
        return True

    def get_file_metadata(self, remote_path: str) -> FileMetadata | DirMetadata:
        """Retrieve metadata for a single file or directory."""
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
    current_user: User = None,
    expire_datetime_utc: Optional[datetime] = None,
    expire_days: Optional[int] = None,
    share_id: str = None,
    access_code: str = None,
    base_path: str = None,
) -> str | None:
    """
    Generate a secure, time-limited download URL for a file or folder.
    """
    if not app.storage.general.get("service_url", None):
        notify.error(
            _(
                "Service URL is not configured. Please set it in the console before sharing files."
            )
        )
        return None

    current_time_utc = datetime.now(settings.SYSTEM_DEFAULT_TIMEZONE)
    this_url_ttl: Optional[datetime] = None

    if isinstance(expire_days, int) and expire_days > 0:
        this_url_ttl = current_time_utc + timedelta(days=expire_days)
    elif isinstance(expire_datetime_utc, datetime):
        this_url_ttl = expire_datetime_utc
    elif expire_datetime_utc is None and expire_days is None:
        # Use default TTL from config for regular downloads
        this_url_ttl = current_time_utc + settings.DEFAULT_DOWNLOAD_LINK_TTL

    async with get_db_context() as session:
        download_info = await FileDownloadCRUD.create(
            session=session,
            name=name,
            type=type_,
            path=target_path,
            base_path=base_path or app.storage.user.get("last_path", ""),
            user=current_user.id if current_user else None,
            share_id=share_id,
            access_code=access_code,
            source=source,
            expires_at=this_url_ttl,
        )

        payload = {"download_id": download_info.id}
        expires_delta = None
        if this_url_ttl:
            expires_delta = this_url_ttl - current_time_utc

        server_url_prefix = app.storage.general["service_url"]

        if source == FileSource.DOWNLOAD:
            token = create_token(
                payload,
                expires_delta=expires_delta or settings.DEFAULT_DOWNLOAD_LINK_TTL,
            )
            url = f"{server_url_prefix}/api/{download_form_browser_url_prefix}/{token}"
        elif source == FileSource.SHARE:
            token = create_token(
                payload,
                expires_delta=expires_delta,
            )
            url = f"{server_url_prefix}/share/{token}"
        else:
            raise ValueError("Invalid source")

        await FileDownloadCRUD.update_url(
            session=session, file_download_id=download_info.id, url=url
        )

        return url


async def get_download_info(download_id: str) -> Optional[FileDownloadInfo]:
    """Retrieve information about a download link by its ID."""
    async with get_db_context() as session:
        return await FileDownloadCRUD.get(session=session, file_download_id=download_id)


async def delete_download_link(download_id: str):
    """Delete a download or share link by its ID."""
    async with get_db_context() as session:
        share_objs = await FileDownloadCRUD.get_share(
            session=session, share_id=download_id
        )
        if share_objs:
            for share_obj in share_objs:
                await session.delete(share_obj)
            await session.commit()

        obj = await FileDownloadCRUD.get(session=session, file_download_id=download_id)
        if obj:
            await session.delete(obj)
            await session.commit()
            return True
        return False


async def get_user_share_links(
    current_user: User, file_name: str | None = None
) -> list[FileDownloadInfo]:
    """Fetch all share links created by the current user, optionally filtered by file name."""
    async with get_db_context() as session:
        query = select(FileDownloadInfo).where(
            FileDownloadInfo.user_id == current_user.id,
            FileDownloadInfo.source == FileSource.SHARE,
        )
        if file_name:
            query = query.where(FileDownloadInfo.name == file_name)

        share_links_db = await session.execute(query)
        return share_links_db.scalars().all()


def set_user_last_path(path):
    """Record the last accessed path for the current user."""
    app.storage.user["last_path"] = str(path)


def get_user_last_path() -> str | None:
    """Retrieve the last accessed path for the current user."""
    return app.storage.user.get("last_path", None)


WINDOWS_FORBIDDEN_CHARS = r'<>:"|?*'
# Note: '/' and '\' are excluded here because they serve as path separators when `allow_subdirs=True`.

# For single filenames, all these characters are forbidden.
# However, for path parsing compatibility, ':' and path separators are handled separately by PurePath.
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
    """
    Check if a filename component matches a Windows-reserved name (with or without extension).
    """
    name_part = name_part.upper().strip()
    # Check exact reserved names (e.g., "CON")
    if name_part in WINDOWS_RESERVED_NAMES:
        return True
    # Check reserved names with extensions (e.g., "CON.TXT")
    if "." in name_part:
        base_name = name_part.split(".", 1)[0]
        if base_name in WINDOWS_RESERVED_NAMES:
            return True
    return False


def validate_filename(name: str, allow_subdirs: bool = False) -> tuple[bool, str]:
    """
    Cross-platform validation for file or directory names.

    :param name: User-provided name.
    :param allow_subdirs: Whether to allow path separators to create subdirectories.
    :return: A tuple (is_valid: bool, message: str).
    """
    # 1. Basic checks
    if not name or not name.strip():
        return False, _("Name cannot be empty or consist only of spaces.")
    name = name.strip()

    # 2. Length check
    if len(name) > MAX_FILENAME_LENGTH:
        return False, _("Name is too long (maximum {max_length} characters).").format(
            max_length=MAX_FILENAME_LENGTH
        )

    # 3. Path parsing and traversal checks (only if subdirectories are allowed)
    if allow_subdirs:
        if name.startswith("/") or name.startswith("\\"):
            return False, _(
                "Name must be a relative path and cannot start with a path separator."
            )
        try:
            path = Path(name)
        except Exception:
            return False, _("Invalid path format.")

        # Prevent directory traversal
        if ".." in path.parts:
            return False, _(
                "Name cannot contain '..' to navigate outside the base directory."
            )

        # Prevent absolute paths
        if path.is_absolute():
            return False, _(
                "Name must be a relative path and cannot start with a path separator or drive letter."
            )

        parts_to_check = path.parts
        chars_to_check = WINDOWS_FORBIDDEN_CHARS
    else:
        parts_to_check = [name]
        chars_to_check = FULL_FORBIDDEN_CHARS

    # 4. Platform-specific validation
    is_win = sys.platform.startswith("win")

    for part in parts_to_check:
        if not part:
            continue  # Skip empty parts (e.g., from "a//b")

        # Linux/Unix: disallow '/' in single filenames
        if not is_win and not allow_subdirs and "/" in part:
            return False, _("Name cannot contain '/' on Linux/Unix systems.")

        # Windows: forbidden characters
        if is_win:
            if any(char in part for char in chars_to_check):
                return False, _(
                    "Name cannot contain any of the following characters: {forbidden_chars}"
                ).format(forbidden_chars=chars_to_check)

            # Reserved names
            if is_windows_reserved(part):
                return False, _(
                    "The name segment '{segment}' is a reserved system name on Windows."
                ).format(segment=part)

            # Cannot end with space or dot
            if part.endswith(".") or part.endswith(" "):
                return False, _(
                    "Name segments cannot end with a space or a dot on Windows."
                )

    return True, _("Name is valid.")

def bytes_to_human_readable(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def rational_to_float(value):
    """EXIF Rational / number → float | None"""
    if value is None:
        return None
    try:
        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            return value.numerator / value.denominator if value.denominator else None
        if isinstance(value, Number):
            return float(value)
    except Exception:
        pass
    return None


def format_exposure_time(value):
    t = rational_to_float(value)
    if not t or t <= 0:
        return None
    if t >= 1:
        return f"{t:.1f} s"
    return f"1/{round(1 / t)} s"


# ============================================================
# GPS helpers
# ============================================================

def dms_to_decimal(dms, ref):
    """(deg, min, sec) + N/S/E/W → decimal degrees"""
    if not dms or not ref:
        return None
    try:
        deg, minute, sec = dms
        value = float(deg) + float(minute) / 60 + float(sec) / 3600
        if ref in ("S", "W"):
            value = -value
        return round(value, 6)
    except Exception:
        return None


def extract_gps_coordinates(gps: dict) -> tuple[float | None, float | None]:
    lat = dms_to_decimal(
        gps.get("GPSLatitude"),
        gps.get("GPSLatitudeRef"),
    )
    lon = dms_to_decimal(
        gps.get("GPSLongitude"),
        gps.get("GPSLongitudeRef"),
    )
    return lat, lon


def bearing_to_text(deg):
    if deg is None:
        return None
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[int((deg + 22.5) // 45) % 8]


def gps_to_ui_fields(gps: dict) -> dict:
    lat, lon = extract_gps_coordinates(gps)

    direction = gps.get("GPSImgDirection")
    direction_text = bearing_to_text(direction)

    ui = {
        "Latitude": lat,
        "Longitude": lon,
        "Altitude": (
            f"{float(gps.get('GPSAltitude')):.1f} m"
            if gps.get("GPSAltitude") is not None else None
        ),
        "Speed": (
            f"{float(gps.get('GPSSpeed')):.1f} km/h"
            if gps.get("GPSSpeed") is not None else None
        ),
        "Direction": (
            f"{float(direction):.1f}° ({direction_text})"
            if direction is not None else None
        ),
        "Position accuracy": (
            f"±{float(gps.get('GPSHPositioningError')):.1f} m"
            if gps.get("GPSHPositioningError") is not None else None
        ),
    }

    return {k: v for k, v in ui.items() if v not in (None, "", {}, [])}


# ============================================================
# Main
# ============================================================

def get_image_info(image_path: Path, display_name: str) -> dict:
    image_path = Path(image_path)

    info: Dict[str, Any] = {
        "File name": image_path.name,
        "Path": display_name,
        "File size": bytes_to_human_readable(image_path.stat().st_size),
    }

    try:
        with Image.open(image_path) as img:
            # 基础图像信息
            info.update({
                "Format": img.format,
                "Size": f"{img.width} × {img.height}",
                "Color mode": img.mode,
            })

            if "dpi" in img.info:
                info["DPI"] = img.info["dpi"]

            exif_raw = img.getexif()
            if not exif_raw:
                return info

            # EXIF → 可读字典
            exif = {
                TAGS.get(tag_id, tag_id): value
                for tag_id, value in exif_raw.items()
            }

            # 拍摄信息
            info.update({
                "Camera make": exif.get("Make"),
                "Camera model": exif.get("Model"),
                "Lens model": exif.get("LensModel"),
                "Software": exif.get("Software"),
                "Date taken": exif.get("DateTimeOriginal"),
                "Date modified": exif.get("DateTime"),
            })

            # 曝光参数
            info.update({
                "Exposure time": format_exposure_time(exif.get("ExposureTime")),
                "F number": (
                    f"f/{rational_to_float(exif.get('FNumber'))}"
                    if exif.get("FNumber") else None
                ),
                "ISO": exif.get("ISOSpeedRatings"),
                "Focal length": (
                    f"{rational_to_float(exif.get('FocalLength'))} mm"
                    if exif.get("FocalLength") else None
                ),
                "Exposure bias": rational_to_float(exif.get("ExposureBiasValue")),
                "Metering mode": exif.get("MeteringMode"),
                "Flash": exif.get("Flash"),
                "White balance": exif.get("WhiteBalance"),
            })

            # GPS（原始 + UI 友好）
            try:
                gps_ifd = exif_raw.get_ifd(0x8825)
                if gps_ifd:
                    gps_raw = {
                        GPSTAGS.get(k, k): v
                        for k, v in gps_ifd.items()
                    }
                    info["GPS"] = gps_to_ui_fields(gps_raw)
            except Exception:
                pass

    except Exception as e:
        info["Error"] = str(e)

    # UI 友好：清理空值
    return {
        k: v for k, v in info.items()
        if v not in (None, "", {}, [])
    }