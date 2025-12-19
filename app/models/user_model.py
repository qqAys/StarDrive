from datetime import datetime
from typing import Optional, List

from sqlalchemy import Column, DateTime, text
from sqlmodel import SQLModel, Field, Relationship

from app.security.ids import generate_ulid
from app.utils.time import utc_now


class RolePermissionLink(SQLModel, table=True):
    __tablename__ = "role_permission_links"

    role_id: str = Field(foreign_key="roles.id", primary_key=True)
    permission_id: str = Field(foreign_key="permissions.id", primary_key=True)


class UserRoleLink(SQLModel, table=True):
    __tablename__ = "user_role_links"

    user_id: str = Field(foreign_key="users.id", primary_key=True)
    role_id: str = Field(foreign_key="roles.id", primary_key=True)


class Role(SQLModel, table=True):
    __tablename__ = "roles"

    id: str = Field(
        default_factory=lambda: str(generate_ulid()), primary_key=True, max_length=26
    )
    name: str = Field(
        unique=True, index=True, max_length=32
    )  # 例如: "admin", "editor", "user"
    description: Optional[str] = Field(default=None, max_length=255)

    users: List["User"] = Relationship(back_populates="roles", link_model=UserRoleLink)
    permissions: List["Permission"] = Relationship(
        back_populates="roles", link_model=RolePermissionLink
    )


class Permission(SQLModel, table=True):
    __tablename__ = "permissions"
    id: str = Field(
        default_factory=lambda: str(generate_ulid()), primary_key=True, max_length=26
    )
    name: str = Field(unique=True, max_length=64)  # 例如: "file:upload", "user:delete"
    description: Optional[str] = None

    roles: List["Role"] = Relationship(
        back_populates="permissions", link_model=RolePermissionLink
    )


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(
        default_factory=lambda: str(generate_ulid()), primary_key=True, max_length=26
    )
    email: str = Field(max_length=128, unique=True, index=True)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    token_version: int = Field(default=0)
    password_hash: str = Field(max_length=128)
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

    roles: List[Role] = Relationship(back_populates="users", link_model=UserRoleLink)
    profile: Optional["UserProfile"] = Relationship(back_populates="user")


class UserProfile(SQLModel, table=True):
    __tablename__ = "user_profile"

    user_id: str = Field(foreign_key="users.id", primary_key=True)

    display_name: str | None = None
    avatar_url: str | None = None
    description: str | None = None
    website: str | None = None
    updated_at: datetime = Field(
        default_factory=lambda: utc_now(),
        sa_column=Column(DateTime(timezone=True), onupdate=text("CURRENT_TIMESTAMP")),
    )
    user: "User" = Relationship(back_populates="profile")
