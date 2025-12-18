from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.file_download_model import FileDownloadInfo
from models.user_model import User, Role, UserRoleLink
from schemas.file_schema import FileType, FileSource
from security import HashingManager


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
        user: str,
        source: FileSource,
        expires_at: datetime
    ) -> FileDownloadInfo:
        file_download = FileDownloadInfo(
            name=name,
            type=type,
            path=path,
            base_path=base_path,
            user_id=user,
            source=source,
            expires_at=expires_at
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
        session: AsyncSession,
        *,
        file_download_id: str
    ) -> Optional[FileDownloadInfo]:
        file_download = select(FileDownloadInfo).where(
            FileDownloadInfo.id == file_download_id
        )
        file_download = await session.execute(file_download)
        file_download = file_download.scalar()
        return file_download
