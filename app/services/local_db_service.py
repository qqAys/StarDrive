from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.config import settings
from app.models import file_download_model

# Prevent unused import warning; this import ensures the model is registered with SQLModel metadata.
_ = file_download_model

# Create an asynchronous SQLAlchemy engine using database settings from the configuration.
async_engine = create_async_engine(
    settings.LOCAL_DB_DSN, echo=settings.LOCAL_DB_ECHO, future=True
)

# Configure a session factory for creating async database sessions.
async_session = sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


async def init_local_db():
    """
    Initialize the local database by creating all tables defined in SQLModel.metadata.
    This function should be called once during application startup.
    """
    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def close_local_db():
    """
    Gracefully dispose of the database engine connection pool.
    This function should be called during application shutdown.
    """
    await async_engine.dispose()


async def get_db() -> AsyncGenerator[Any, Any]:
    """
    Dependency generator for FastAPI-style dependency injection.
    Provides a database session that is automatically closed after use.
    """
    async with async_session() as session:
        yield session


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Asynchronous context manager for manually managing database sessions.
    Ensures proper cleanup and transaction handling when used in async contexts.
    """
    async with async_session() as session:
        yield session


if __name__ == "__main__":
    pass
