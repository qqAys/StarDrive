"""Create the schema used by StarDrive before Alembic was introduced.

Revision ID: 0001_initial_schema
Revises: None
"""

from alembic import op
from sqlmodel import SQLModel

from app import models  # noqa: F401  Ensure every table is registered.

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    SQLModel.metadata.create_all(op.get_bind())


def downgrade() -> None:
    SQLModel.metadata.drop_all(op.get_bind())
