from datetime import datetime

from sqlalchemy import Column, DateTime, JSON, text
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


class StorageProfile(SQLModel, table=True):
    __tablename__ = "storage_profiles"

    id: str = Field(
        default_factory=lambda: str(generate_ulid()), primary_key=True, max_length=26
    )
    name: str = Field(max_length=64)
    backend_type: str = Field(max_length=32, index=True)
    is_active: bool = Field(default=False, index=True)
    public_config: dict = Field(default_factory=dict, sa_column=Column(JSON))
    encrypted_secrets: dict = Field(default_factory=dict, sa_column=Column(JSON))
    last_tested_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_test_success: bool | None = Field(default=None)
    last_test_message: str | None = Field(default=None, max_length=512)
    created_at: datetime = Field(
        default_factory=lambda: utc_now(),
        sa_column=Column(
            DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
        ),
    )
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
