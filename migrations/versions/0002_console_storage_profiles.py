"""Add console storage profiles and user soft delete.

Revision ID: 0002_console_storage_profiles
Revises: 0001_initial_schema
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0002_console_storage_profiles"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "storage_profiles" not in tables:
        op.create_table(
            "storage_profiles",
            sa.Column("id", sa.String(length=26), nullable=False),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("backend_type", sa.String(length=32), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("public_config", sa.JSON(), nullable=True),
            sa.Column("encrypted_secrets", sa.JSON(), nullable=True),
            sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_test_success", sa.Boolean(), nullable=True),
            sa.Column("last_test_message", sa.String(length=512), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=True,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=True,
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    _create_index_if_missing(
        inspector,
        "storage_profiles",
        op.f("ix_storage_profiles_backend_type"),
        ["backend_type"],
    )
    _create_index_if_missing(
        inspector,
        "storage_profiles",
        op.f("ix_storage_profiles_is_active"),
        ["is_active"],
    )

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "deleted_at" not in user_columns:
        op.add_column(
            "users",
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )
    _create_index_if_missing(
        inspector,
        "users",
        op.f("ix_users_deleted_at"),
        ["deleted_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        user_indexes = {index["name"] for index in inspector.get_indexes("users")}
        if op.f("ix_users_deleted_at") in user_indexes:
            op.drop_index(op.f("ix_users_deleted_at"), table_name="users")
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "deleted_at" in user_columns:
            op.drop_column("users", "deleted_at")

    if "storage_profiles" in tables:
        profile_indexes = {
            index["name"] for index in inspector.get_indexes("storage_profiles")
        }
        if op.f("ix_storage_profiles_is_active") in profile_indexes:
            op.drop_index(
                op.f("ix_storage_profiles_is_active"), table_name="storage_profiles"
            )
        if op.f("ix_storage_profiles_backend_type") in profile_indexes:
            op.drop_index(
                op.f("ix_storage_profiles_backend_type"),
                table_name="storage_profiles",
            )
        op.drop_table("storage_profiles")


def _create_index_if_missing(inspector, table_name: str, name: str, columns: list[str]):
    indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if name not in indexes:
        op.create_index(name, table_name, columns, unique=False)
