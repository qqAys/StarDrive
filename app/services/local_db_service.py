from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
import shutil
from typing import Any, AsyncGenerator

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import make_url
from sqlmodel import SQLModel

from app.config import settings
from app import models

# Ensure all model modules are imported before migration checks inspect metadata.
_ = models

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_BASELINE_REVISION = "0001_initial_schema"


class DatabaseMigrationError(RuntimeError):
    """Raised when an existing database cannot be safely identified or migrated."""


def _alembic_config() -> AlembicConfig:
    return AlembicConfig((PROJECT_ROOT / "alembic.ini").as_posix())


def _sqlite_path(database_url: str) -> Path:
    url = make_url(database_url)
    if (
        url.get_backend_name() != "sqlite"
        or not url.database
        or url.database == ":memory:"
    ):
        raise DatabaseMigrationError(
            "StarDrive automatic migrations support file-based SQLite databases only"
        )
    return Path(url.database).expanduser().resolve()


def _sync_database_url(database_url: str) -> str:
    return database_url.replace("sqlite+aiosqlite://", "sqlite://", 1)


def _backup_legacy_database(database_path: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = database_path.with_name(f"{database_path.name}.bak.{timestamp}")
    shutil.copy2(database_path, backup_path)
    return backup_path


def migrate_database(database_url: str) -> None:
    """Upgrade an empty or Alembic-managed database without risking legacy data.

    Databases created before Alembic are recognized only when every table in the
    current baseline is present. They are copied before being stamped at the
    baseline revision; partial schemas are rejected for manual recovery.
    """
    database_path = _sqlite_path(database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    config = _alembic_config()
    expected_tables = set(SQLModel.metadata.tables)
    engine = create_engine(_sync_database_url(database_url))

    try:
        with engine.begin() as connection:
            tables = set(inspect(connection).get_table_names())
            config.attributes["connection"] = connection
            if "alembic_version" in tables:
                command.upgrade(config, "head")
                return

            existing_tables = tables & expected_tables
            if not existing_tables:
                command.upgrade(config, "head")
                return

            if expected_tables.issubset(tables):
                _backup_legacy_database(database_path)
                command.stamp(config, ALEMBIC_BASELINE_REVISION)
                command.upgrade(config, "head")
                return

            missing_tables = ", ".join(sorted(expected_tables - tables))
            raise DatabaseMigrationError(
                "Existing database has an incomplete legacy schema. "
                f"Missing tables: {missing_tables}. Restore from backup or migrate manually."
            )
    finally:
        engine.dispose()


# Create an asynchronous SQLAlchemy engine using database settings from the configuration.
async_engine = create_async_engine(
    settings.LOCAL_DB_DSN, echo=settings.LOCAL_DB_ECHO, future=True
)

# Configure a session factory for creating async database sessions.
async_session = sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


async def init_local_db():
    """
    Upgrade the local SQLite database to the current Alembic revision.

    This function should be called once during application startup. Legacy
    databases are backed up and stamped only when their full baseline schema is
    recognized; malformed databases fail safely instead of being altered.
    """
    migrate_database(settings.LOCAL_DB_DSN)


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
