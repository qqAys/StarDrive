from datetime import datetime

from sqlalchemy import Column, DateTime, text
from sqlmodel import Field, SQLModel

from app.security.ids import generate_ulid
from app.utils.time import utc_now


class AppSetting(SQLModel, table=True):
    __tablename__ = "app_settings"

    key: str = Field(primary_key=True, max_length=64)
    value: str = Field(max_length=1024)
    updated_at: datetime = Field(
        default_factory=lambda: utc_now(),
        sa_column=Column(
            DateTime(timezone=True),
            onupdate=text("CURRENT_TIMESTAMP"),
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )


class PasswordResetToken(SQLModel, table=True):
    __tablename__ = "password_reset_tokens"

    id: str = Field(
        default_factory=lambda: str(generate_ulid()), primary_key=True, max_length=26
    )
    user_id: str = Field(foreign_key="users.id", index=True, max_length=26)
    token_hash: str = Field(unique=True, index=True, max_length=128)
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), index=True))
    used_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: utc_now(),
        sa_column=Column(
            DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
        ),
    )
