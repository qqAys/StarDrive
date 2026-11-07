"""Persist the first-login password requirement.

Revision ID: 0003_initial_admin_password
Revises: 0002_console_storage_profiles
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_initial_admin_password"
down_revision = "0002_console_storage_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = sa.inspect(op.get_bind()).get_columns("users")
    if not any(column["name"] == "must_change_password" for column in columns):
        op.add_column(
            "users",
            sa.Column(
                "must_change_password",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    users = sa.table("users", sa.column("must_change_password", sa.Boolean()))
    pending = (
        op.get_bind()
        .execute(
            sa.select(sa.literal(1))
            .select_from(users)
            .where(users.c.must_change_password)
        )
        .first()
    )
    if pending:
        raise RuntimeError("Complete the initial password change before downgrading.")
    op.drop_column("users", "must_change_password")
