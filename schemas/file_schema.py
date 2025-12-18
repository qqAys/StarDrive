import enum
from typing import Optional

from pydantic import BaseModel, Field

from core.i18n import _

FILE_NAME_FORBIDDEN_CHARS = r'\/:*?"<>|'


class FileType(str, enum.Enum):
    FILE = "file"
    DIR = "dir"
    MIXED = "mixed"


class FileSource(str, enum.Enum):
    DOWNLOAD = "download"
    SHARE = "share"


# --- 文件元数据的基类 ---
class FileMetadataBase(BaseModel):
    name: str = Field(description=_("File name or Directory name"))
    path: str = Field(description=_("Path"))
    type: FileType = Field(description=_("File type"))
    extension: Optional[str] = Field(default=None, description=_("File extension"))
    size: int = Field(default=0, description=_("File size (bytes)"))
    accessed_at: Optional[float] = Field(
        default=None, description=_("Last access timestamp")
    )
    modified_at: Optional[float] = Field(
        default=None, description=_("Last modified timestamp")
    )
    created_at: Optional[float] = Field(
        default=None, description=_("Creation timestamp")
    )
    status_changed_at: Optional[float] = Field(
        default=None, description=_("Last status change timestamp")
    )
    custom_updated_at: Optional[float] = Field(
        default=None, description=_("Custom update timestamp")
    )

    class Config:
        extra = "ignore"
        from_attributes = True

    @property
    def is_dir(self) -> bool:
        return self.type == FileType.DIR


# 目录元数据
class DirMetadata(FileMetadataBase):
    type: FileType = FileType.DIR
    num_children: int = Field(
        default=0, description=_("Number of children in the directory")
    )


# 文件元数据
class FileMetadata(FileMetadataBase):
    type: FileType = FileType.FILE
