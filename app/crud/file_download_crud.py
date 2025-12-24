from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.file_download_model import FileDownloadInfo
from app.schemas.file_schema import FileType, FileSource


class FileDownloadCRUD:

    # 创建
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

    # 更新URL
    @staticmethod
    async def update_url(
        session: AsyncSession,
        *,
        file_download_id: str,
        url: str,
    ) -> FileDownloadInfo:
        file_download = select(FileDownloadInfo).where(
            FileDownloadInfo.id == file_download_id
        )
        file_download = await session.execute(file_download)
        file_download = file_download.scalar()
        file_download.url = url
        await session.commit()
        await session.refresh(file_download)
        return file_download

    # 读取
    @staticmethod
    async def get(
        session: AsyncSession, *, file_download_id: str
    ) -> Optional[FileDownloadInfo]:
        file_download = select(FileDownloadInfo).where(
            FileDownloadInfo.id == file_download_id
        )
        file_download = await session.execute(file_download)
        file_download = file_download.scalar()
        return file_download

    @staticmethod
    async def get_share(
        session: AsyncSession, *, share_id: str
    ) -> Sequence[FileDownloadInfo]:
        file_download = select(FileDownloadInfo).where(
            FileDownloadInfo.share_id == share_id
        )
        file_download = await session.execute(file_download)
        file_download = file_download.scalars().all()
        return file_download
