from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from config import settings
from models import file_download_model

_ = file_download_model

async_engine = create_async_engine(
    settings.LOCAL_DB_DSN, echo=settings.LOCAL_DB_ECHO, future=True
)
async_session = sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


async def init_local_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def close_local_db():
    await async_engine.dispose()


if __name__ == "__main__":
    pass
