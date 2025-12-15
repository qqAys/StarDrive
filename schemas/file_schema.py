from typing import Literal, Optional

from pydantic import BaseModel, Field

from utils import _

FILE_NAME_FORBIDDEN_CHARS = r'\/:*?"<>|'


# --- 文件元数据的基类 ---
class FileMetadataBase(BaseModel):
    name: str = Field(description=_("File name or Directory name"))
    path: str = Field(description=_("Path"))
    type: Literal["file", "dir", "link"] = Field(description=_("File type"))
    extension: Optional[str] = Field(default=None, description=_("File extension"))
    size: int = Field(default=0, description=_("File size (bytes)"))
    created_at: Optional[float] = Field(
        default=None, description=_("Creation timestamp")
    )
    updated_at: Optional[float] = Field(
        default=None, description=_("Last update timestamp")
    )

    class Config:
        extra = "ignore"
        from_attributes = True

    @property
    def is_dir(self) -> bool:
        return self.type == "dir"


# 目录元数据
class DirMetadata(FileMetadataBase):
    type: Literal["dir"] = "dir"
    num_children: int = Field(
        default=0, description=_("Number of children in the directory")
    )


# 文件元数据
class FileMetadata(FileMetadataBase):
    type: Literal["file"] = "file"
