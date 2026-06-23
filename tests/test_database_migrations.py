import sqlite3

import pytest
from sqlalchemy import create_engine, inspect
from sqlmodel import SQLModel

from app.services.local_db_service import DatabaseMigrationError, migrate_database


def database_url(path):
    return f"sqlite+aiosqlite:///{path}"


def test_empty_database_is_migrated_to_head(tmp_path):
    path = tmp_path / "local.db"

    migrate_database(database_url(path))

    engine = create_engine(f"sqlite:///{path}")
    assert "alembic_version" in inspect(engine).get_table_names()
    assert set(SQLModel.metadata.tables).issubset(inspect(engine).get_table_names())
    engine.dispose()


def test_complete_legacy_database_is_backed_up_and_stamped(tmp_path):
    path = tmp_path / "local.db"
    engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(engine)
    engine.dispose()

    migrate_database(database_url(path))

    engine = create_engine(f"sqlite:///{path}")
    assert "alembic_version" in inspect(engine).get_table_names()
    engine.dispose()
    assert list(tmp_path.glob("local.db.bak.*"))


def test_partial_legacy_database_is_rejected_without_backup(tmp_path):
    path = tmp_path / "local.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE users (id TEXT PRIMARY KEY)")

    with pytest.raises(DatabaseMigrationError, match="incomplete legacy schema"):
        migrate_database(database_url(path))

    assert not list(tmp_path.glob("local.db.bak.*"))
