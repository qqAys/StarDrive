# 文件下载信息
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, Enum, text
from sqlmodel import SQLModel, Field, Relationship

from security import generate_ulid
from schemas.file_schema import FileType, FileSource


class FileDownloadInfo(SQLModel, table=True):
    __tablename__ = "file_downloads"

    id: str = Field(
        default_factory=lambda: str(generate_ulid()),
        primary_key=True,
        max_length=26,
    )

    name: str = Field(max_length=256)
    type: FileType = Field(
        sa_column=Column(Enum(FileType, native_enum=False), nullable=False)
    )

    path: str = Field(max_length=512)
    base_path: str = Field(max_length=512)

    user_id: str = Field(
        foreign_key="users.id",
        index=True,
        max_length=26,
    )

    source: FileSource = Field(
        sa_column=Column(Enum(FileSource, native_enum=False), nullable=False)
    )

    url: str | None = Field(default_factory=None, max_length=256)

    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), index=True)
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            index=True,
        ),
    )
