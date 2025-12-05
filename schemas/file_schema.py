from typing import Literal, Optional

from pydantic import BaseModel, Field

from utils import _


# --- 文件元数据的基类 ---
class FileMetadataBase(BaseModel):
    name: str = Field(description=_("文件名或目录名"))
    path: str = Field(description=_("路径"))
    type: Literal["file", "dir", "link"] = Field(description=_("文件类型"))
    size: int = Field(default=0, description=_("文件大小（字节）"))
    created_at: Optional[float] = Field(default=None, description=_("创建时间戳"))

    class Config:
        extra = "ignore"
        from_attributes = True


# 目录元数据
class DirMetadata(FileMetadataBase):
    type: Literal["dir"] = "dir"
    num_children: int = Field(default=0, description=_("目录下的子项数量"))


# 文件元数据
class FileMetadata(FileMetadataBase):
    type: Literal["file"] = "file"


# 符号链接
class Symlink(FileMetadataBase):
    type: Literal["link"] = "link"
    target_path: str = Field(description=_("符号链接的目标路径"))
