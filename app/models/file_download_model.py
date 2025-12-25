from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum
from sqlmodel import SQLModel, Field

from app.schemas.file_schema import FileType, FileSource
from app.security.ids import generate_ulid
from app.utils.time import utc_now


class FileDownloadInfo(SQLModel, table=True):
    """
    Represents a file download record in the database.

    This model tracks downloadable files, including user-owned files and shared links.
    It supports expiration, access control via access codes, and multiple file sources.
    """

    __tablename__ = "file_downloads"

    id: str = Field(
        default_factory=lambda: str(generate_ulid()),
        primary_key=True,
        max_length=26,
        description="Unique ULID-based identifier for the download record.",
    )

    name: str = Field(
        max_length=256, description="Original or display name of the file."
    )

    type: FileType = Field(
        sa_column=Column(Enum(FileType, native_enum=False), nullable=False),
        description="Category or MIME-like type of the file (e.g., document, image).",
    )

    path: str = Field(max_length=512, description="Full path to the file on storage.")
    base_path: str = Field(
        max_length=512, description="Root directory or base path for the file."
    )

    user_id: str | None = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        max_length=26,
        description="ID of the user who owns the file. Null if created via share.",
    )

    share_id: str | None = Field(
        default=None,
        foreign_key="file_downloads.id",  # Self-referential for shared copies
        index=True,
        max_length=26,
        description=(
            "ID of the original file download record this entry is shared from. "
            "Used to trace shared links back to their source."
        ),
    )

    access_code: str | None = Field(
        default=None,
        max_length=16,
        description="Optional short code required to access shared files.",
    )

    source: FileSource = Field(
        sa_column=Column(Enum(FileSource, native_enum=False), nullable=False),
        description="Origin of the file (e.g., upload, external URL, system-generated).",
    )

    url: str | None = Field(
        default=None,
        max_length=256,
        description="Public or temporary URL for direct access (if applicable).",
    )

    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), index=True),
        description="UTC timestamp after which the download link is no longer valid.",
    )

    created_at: datetime = Field(
        default_factory=lambda: utc_now(),
        sa_column=Column(DateTime(timezone=True), index=True),
        description="UTC timestamp when this download record was created.",
    )

    @property
    def expires_at_utc(self) -> datetime:
        """
        Returns the expiration time as a timezone-aware datetime in UTC.

        Ensures compatibility by attaching UTC timezone if missing.
        """
        dt = self.expires_at
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    @property
    def created_at_utc(self) -> datetime:
        """
        Returns the creation time as a timezone-aware datetime in UTC.

        Ensures compatibility by attaching UTC timezone if missing.
        """
        dt = self.created_at
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
