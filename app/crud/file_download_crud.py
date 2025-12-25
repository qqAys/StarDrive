from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.file_download_model import FileDownloadInfo
from app.schemas.file_schema import FileType, FileSource


class FileDownloadCRUD:
    """
    CRUD operations for managing file download records.
    """

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        name: str,
        type: FileType,
        path: str,
        base_path: str,
        source: FileSource,
        expires_at: datetime,
        user: str = None,
        share_id: str = None,
        access_code: str = None,
    ) -> FileDownloadInfo:
        """
        Creates a new file download record.

        Args:
            session: The asynchronous database session.
            name: Display name of the file.
            type: The categorized type of the file.
            path: Relative path to the file.
            base_path: Base storage path for the file.
            source: Origin source of the file (e.g., upload, sync).
            expires_at: Expiration timestamp for the download link.
            user: Optional ID of the user who owns or requested the file.
            share_id: Optional ID linking this file to a shared resource.
            access_code: Optional code required to access the file.

        Returns:
            The created FileDownloadInfo instance.
        """
        file_download = FileDownloadInfo(
            name=name,
            type=type,
            path=path,
            base_path=base_path,
            user_id=user,
            share_id=share_id,
            access_code=access_code,
            source=source,
            expires_at=expires_at,
        )
        session.add(file_download)
        await session.commit()
        await session.refresh(file_download)
        return file_download

    @staticmethod
    async def update_url(
        session: AsyncSession,
        *,
        file_download_id: str,
        url: str,
    ) -> FileDownloadInfo:
        """
        Updates the public URL for an existing file download record.

        Args:
            session: The asynchronous database session.
            file_download_id: Unique identifier of the file download record.
            url: The new public download URL.

        Returns:
            The updated FileDownloadInfo instance.
        """
        stmt = select(FileDownloadInfo).where(FileDownloadInfo.id == file_download_id)
        result = await session.execute(stmt)
        file_download = result.scalar_one()
        file_download.url = url
        await session.commit()
        await session.refresh(file_download)
        return file_download

    @staticmethod
    async def get(
        session: AsyncSession, *, file_download_id: str
    ) -> Optional[FileDownloadInfo]:
        """
        Retrieves a file download record by its ID.

        Args:
            session: The asynchronous database session.
            file_download_id: Unique identifier of the file download record.

        Returns:
            The FileDownloadInfo instance if found, otherwise None.
        """
        stmt = select(FileDownloadInfo).where(FileDownloadInfo.id == file_download_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_share(
        session: AsyncSession, *, share_id: str
    ) -> Sequence[FileDownloadInfo]:
        """
        Retrieves all file download records associated with a given share ID.

        Args:
            session: The asynchronous database session.
            share_id: Identifier of the shared resource.

        Returns:
            A sequence of FileDownloadInfo instances linked to the share.
        """
        stmt = select(FileDownloadInfo).where(FileDownloadInfo.share_id == share_id)
        result = await session.execute(stmt)
        return result.scalars().all()
