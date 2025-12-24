from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum
from sqlmodel import SQLModel, Field

from app.schemas.file_schema import FileType, FileSource
from app.security.ids import generate_ulid
from app.utils.time import utc_now


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

    user_id: str | None = Field(
        default_factory=None,
        foreign_key="users.id",
        index=True,
        max_length=26,
    )

    share_id: str | None = Field(
        default=None,
        foreign_key="file_downloads.id",  # 指向自身表
        index=True,
        max_length=26,
    )

    access_code: str | None = Field(default_factory=None, max_length=16)

    source: FileSource = Field(
        sa_column=Column(Enum(FileSource, native_enum=False), nullable=False)
    )

    url: str | None = Field(default_factory=None, max_length=256)

    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), index=True))

    created_at: datetime = Field(
        default_factory=lambda: utc_now(),
        sa_column=Column(DateTime(timezone=True), index=True),
    )

    @property
    def expires_at_utc(self) -> datetime | None:
        dt = self.expires_at
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    @property
    def created_at_utc(self) -> datetime:
        dt = self.created_at
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
