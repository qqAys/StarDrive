"""Rotate the configured initial administrator's password from a local terminal."""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.engine import make_url

from app.config import settings
from app.crud.user_crud import UserCRUD
from app.models.system_model import PasswordResetToken
from app.security.password import (
    generate_random_password,
    open_password_terminal,
    show_initial_password,
)
from app.services.local_db_service import close_local_db, get_db_context, init_local_db


async def recover_initial_admin(terminal: int) -> None:
    database = make_url(settings.LOCAL_DB_DSN).database
    if not database or not Path(database).expanduser().is_file():
        raise ValueError("The configured SQLite database does not exist.")

    await init_local_db()
    try:
        async with get_db_context() as session:
            user = await UserCRUD.get_by_email(session, settings.APP_INIT_USER)
            if not user or not user.is_active or not user.is_superuser:
                raise ValueError("The configured initial administrator is not active.")
            password = generate_random_password(24)
            user.must_change_password = True
            await session.execute(
                delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
            )
            await UserCRUD.update_password(session, user=user, new_password=password)
            show_initial_password(terminal, user.email, password)
    finally:
        await close_local_db()


if __name__ == "__main__":
    if not sys.stdin.isatty():
        sys.exit("Run recovery in a private, interactive terminal.")
    try:
        with open_password_terminal() as terminal:
            asyncio.run(recover_initial_admin(terminal))
    except OSError as exc:
        sys.exit(f"Administrator recovery could not complete: {exc}")
    except ValueError as exc:
        sys.exit(str(exc))
