import enum
from typing import Optional

from pydantic import BaseModel, Field

from app.core.i18n import _

FILE_NAME_FORBIDDEN_CHARS = r'\/:*?"<>|'


class FileType(str, enum.Enum):
    FILE = "file"
    DIR = "dir"
    MIXED = "mixed"


class FileSource(str, enum.Enum):
    DOWNLOAD = "download"
    SHARE = "share"


# --- Base model for file and directory metadata ---
class FileMetadataBase(BaseModel):
    """
    Base schema for file system metadata.

    Represents common attributes shared by both files and directories.
    Timestamps are in Unix epoch format (seconds since 1970-01-01 UTC).
    """

    name: str = Field(description=_("File or directory name"))
    path: str = Field(description=_("Full path to the item"))
    type: FileType = Field(description=_("Type of the item: file, directory, or mixed"))
    extension: Optional[str] = Field(
        default=None, description=_("File extension (without dot)")
    )
    size: int = Field(default=0, description=_("Size in bytes (0 for directories)"))
    accessed_at: Optional[float] = Field(
        default=None, description=_("Timestamp of last access (Unix epoch)")
    )
    modified_at: Optional[float] = Field(
        default=None, description=_("Timestamp of last modification (Unix epoch)")
    )
    created_at: Optional[float] = Field(
        default=None, description=_("Timestamp of creation (Unix epoch)")
    )
    status_changed_at: Optional[float] = Field(
        default=None, description=_("Timestamp of last metadata change (Unix epoch)")
    )
    custom_updated_at: Optional[float] = Field(
        default=None, description=_("Custom update timestamp (Unix epoch)")
    )

    class Config:
        extra = "ignore"
        from_attributes = True

    @property
    def is_dir(self) -> bool:
        """Returns True if this item is a directory."""
        return self.type == FileType.DIR


# Directory-specific metadata
class DirMetadata(FileMetadataBase):
    """
    Metadata specific to directories.

    Extends the base metadata with a count of immediate children.
    """

    type: FileType = FileType.DIR
    num_children: int = Field(
        default=0, description=_("Number of immediate children in the directory")
    )


# File-specific metadata
class FileMetadata(FileMetadataBase):
    """
    Metadata specific to files.

    Enforces that the type is always 'file'.
    """

    type: FileType = FileType.FILE
