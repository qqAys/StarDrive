from datetime import datetime

from sqlmodel import SQLModel


class UserLogin(SQLModel):
    email: str
    password: str


class UserRegister(SQLModel):
    email: str
    password: str


class UserModifyPassword(SQLModel):
    current_password: str
    new_password: str


class UserResetPasswordRequest(SQLModel):
    email: str


class UserResetPasswordConfirm(SQLModel):
    token: str
    new_password: str


class UserRead(SQLModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_superuser: bool
    created_at: datetime


class UserUpdate(SQLModel):
    username: str | None = None
    email: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None
