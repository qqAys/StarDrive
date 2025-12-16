# 文件下载信息
from datetime import datetime

from sqlalchemy import Column, Enum, DateTime
from sqlmodel import SQLModel, Field

from schemas.file_schema import FileType, FileSource


class FileDownloadInfo(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    download_id: str = Field(index=True, unique=True, max_length=26)
    name: str = Field(max_length=256)
    type: FileType = Field(sa_column=Column(Enum(FileType), nullable=False))
    path: str = Field(max_length=512)
    base_path: str = Field(max_length=512)
    user: str = Field(max_length=64)
    source: FileSource = Field(sa_column=Column(Enum(FileSource)))
    exp: datetime = Field(sa_column=Column(DateTime(timezone=True), index=True))
    url: str = Field(max_length=256)


#
# class FileDownloadInfo(SQLModel, table=True):
#     id: int | None = Field(default=None, primary_key=True)
#     download_id: str = Field(index=True, unique=True, max_length=26)
#
#     name: str = Field(max_length=256)
#     type: FileType = Field(sa_column=Column(Enum(FileType), nullable=False))
#
#     path: str = Field(max_length=512)
#     base_path: str = Field(max_length=512)
#
#     user_id: str = Field(index=True, max_length=64)
#     user_display: str = Field(max_length=128)
#
#     source: FileSource = Field(sa_column=Column(Enum(FileSource)))
#
#     expires_at: datetime = Field(
#         sa_column=Column(DateTime(timezone=True), index=True)
#     )
#
#     created_at: datetime = Field(
#         default_factory=datetime.now(datetime.UTC),
#         sa_column=Column(DateTime(timezone=True), index=True)
#     )
