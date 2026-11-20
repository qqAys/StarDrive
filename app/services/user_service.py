import asyncio
import hashlib
import secrets
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from nicegui import app, ui
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import text

from app.config import settings
from app.core.i18n import _
from app.core.logging import logger
from app.crud.system_crud import AppSettingCRUD
from app.crud.user_crud import PasswordResetTokenCRUD, UserCRUD
from app.models.system_model import AppSetting
from app.models.user_model import User
from app.schemas.user_schema import UserLogin, UserModifyPassword
from app.security.constants import INITIAL_PASSWORD_SESSION_KEY
from app.security.hashing import HashingManager
from app.security.password import (
    generate_random_password,
    validate_password,
)
from app.security.tokens import create_access_token, create_refresh_token
from app.utils.time import ensure_utc, utc_now


ALLOW_REGISTRATION_KEY = "allow_registration"
INITIAL_SETUP_KEY = "initial_setup_completed"


class UserManager:
    """
    User management system for NiceGUI applications, backed by a database.
    Handles user authentication, session management, and administrative operations.
    """

    def __init__(
        self,
        *,
        user_crud: type[UserCRUD],
        db_context,
    ):
        self.user_crud = user_crud
        self.db_context = db_context

    async def initialize(self):
        """Initialize policy and permanently close setup for any existing account."""
        async with self.db_context() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            if await session.get(AppSetting, ALLOW_REGISTRATION_KEY) is None:
                session.add(
                    AppSetting(
                        key=ALLOW_REGISTRATION_KEY,
                        value="1" if settings.APP_ALLOW_REGISTRATION else "0",
                    )
                )
            if await self.user_crud.list(session, limit=1, include_deleted=True):
                if await session.get(AppSetting, INITIAL_SETUP_KEY) is None:
                    session.add(AppSetting(key=INITIAL_SETUP_KEY, value="1"))
            await session.commit()

    async def setup_required(self) -> bool:
        async with self.db_context() as session:
            return await self._setup_required(session)

    async def _setup_required(self, session) -> bool:
        # Presence alone closes setup, even if a marker's value is unexpected.
        return await session.get(
            AppSetting, INITIAL_SETUP_KEY
        ) is None and not await self.user_crud.list(
            session, limit=1, include_deleted=True
        )

    async def complete_setup(
        self, *, setup_token: str, email: str, password: str, confirmation: str
    ) -> None:
        configured = settings.APP_SETUP_TOKEN
        expected = configured.get_secret_value() if configured else ""
        if len(expected) < 32 or not secrets.compare_digest(
            hashlib.sha256(setup_token.encode()).digest(),
            hashlib.sha256(expected.encode()).digest(),
        ):
            raise ValueError(
                _("Setup is unavailable or the setup credential is invalid.")
            )
        try:
            email = str(TypeAdapter(EmailStr).validate_python(email))
        except ValidationError:
            raise ValueError(_("Invalid email address")) from None
        if len(email) > 128:
            raise ValueError(_("Invalid email address"))
        if password != confirmation:
            raise ValueError(_("Passwords do not match"))
        valid, message = validate_password(password)
        if not valid:
            raise ValueError(message)
        password_hash = HashingManager.hash_password(password)
        async with self.db_context() as session:
            # Serialize across connections/processes before reading either guard.
            # Do not use CRUD helpers that commit independently.
            await session.execute(text("BEGIN IMMEDIATE"))
            try:
                if not await self._setup_required(session):
                    raise ValueError(_("Initial setup is already complete."))
                session.add(
                    User(
                        email=email,
                        password_hash=password_hash,
                        is_superuser=True,
                        is_active=True,
                        quota_bytes=0,
                        must_change_password=False,
                    )
                )
                session.add(AppSetting(key=INITIAL_SETUP_KEY, value="1"))
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    # Session state
    async def is_login(self) -> bool:
        """Check whether the current user is authenticated."""
        return bool(await self.current_user())

    async def current_user(self):
        """Retrieve the currently logged-in user from session storage."""
        return await self._get_user(None)

    async def _get_user(self, email: EmailStr | None):
        """
        Fetch a user by email (or from session if email is not provided),
        and validate their active status and token version.
        Invalid or outdated sessions are automatically cleared.
        """
        email = email or app.storage.user.get("email")
        if not email:
            return None

        async with self.db_context() as session:
            user = await self.user_crud.get_by_email(session, email)

        if not user:
            app.storage.user.clear()
            return None

        if not user.is_active or user.must_change_password:
            app.storage.user.clear()
            return None

        if app.storage.user.get("token_version") != user.token_version:
            # Revoke outdated session
            app.storage.user.clear()
            return None

        return user

    async def is_active(self, email: EmailStr | None = None) -> bool:
        """Check whether a user (by email or current session) is active."""
        user = await self._get_user(email)
        return bool(user and user.is_active)

    async def is_superuser(self, email: EmailStr | None = None) -> bool:
        """Check whether a user (by email or current session) has superuser privileges."""
        user = await self._get_user(email)
        return bool(user and user.is_superuser)

    # Login / Logout
    async def login(self, user_login: UserLogin):
        """
        Authenticate a user and establish a session with access and refresh tokens.
        Also captures the user's browser timezone for localization.
        """
        async with self.db_context() as session:
            user = await self.user_crud.authenticate(
                session=session,
                email=user_login.email,
                password=user_login.password,
            )

            if not user:
                raise ValueError(_("Invalid email or password"))

            if user.must_change_password:
                app.storage.user.clear()
                app.storage.user[INITIAL_PASSWORD_SESSION_KEY] = {
                    "email": user.email,
                    "token_version": user.token_version,
                }
                return user

            tz = await get_user_timezone_from_browser()

            access_payload = {"sub": user.id}
            access_token = create_access_token(access_payload)

            refresh_payload = access_payload.copy()
            refresh_payload.update({"tv": user.token_version})
            refresh_token = create_refresh_token(refresh_payload)

            app.storage.user.update(
                {
                    "user_id": user.id,
                    "email": user.email,
                    "token_version": user.token_version,
                    "timezone": tz,
                    "access_token": access_token,
                }
            )

            return user

    async def logout(self) -> bool:
        """
        Log out the current user by incrementing their token version (invalidating all sessions)
        and clearing local session storage.
        """
        async with self.db_context() as session:
            try:
                user = await self.current_user()
                if user:
                    user.token_version += 1
                    session.add(user)
                    await session.commit()
                app.storage.user.clear()
                return True
            except Exception:
                return False

    # User management
    async def create_user(
        self,
        *,
        email: str,
        password: str,
        is_superuser: bool = False,
        is_active: bool = True,
        quota_bytes: int | None = None,
    ):
        """
        Create a new user account.
        Raises an error if a user with the same email already exists.
        """
        valid, message = validate_password(password)
        if not valid:
            raise ValueError(message)

        quota = 0 if is_superuser else settings.APP_DEFAULT_USER_QUOTA_BYTES
        if quota_bytes is not None:
            quota = max(0, quota_bytes)

        async with self.db_context() as session:
            existing = await self.user_crud.get_by_email(
                session, email, include_deleted=True
            )
            if existing:
                message = _("User already exists")
                logger.warning(message)
                raise ValueError(message)

            return await self.user_crud.create(
                session=session,
                email=email,
                password=password,
                is_superuser=is_superuser,
                is_active=is_active,
                quota_bytes=quota,
            )

    async def register_user(self, *, email: str, password: str):
        if not await self.is_registration_allowed():
            raise ValueError(_("Registration is currently disabled."))
        return await self.create_user(
            email=email,
            password=password,
            is_superuser=False,
            is_active=True,
            quota_bytes=settings.APP_DEFAULT_USER_QUOTA_BYTES,
        )

    async def list_users(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        query: str | None = None,
        include_deleted: bool = False,
    ):
        async with self.db_context() as session:
            users = await self.user_crud.list(
                session=session,
                offset=offset,
                limit=limit,
                query=query,
                include_deleted=include_deleted,
            )
            total = await self.user_crud.count(
                session=session, query=query, include_deleted=include_deleted
            )
            return list(users), total

    async def is_registration_allowed(self) -> bool:
        if await self.setup_required():
            return False
        async with self.db_context() as session:
            value = await AppSettingCRUD.get_value(
                session,
                ALLOW_REGISTRATION_KEY,
                "1" if settings.APP_ALLOW_REGISTRATION else "0",
            )
            return value == "1"

    async def set_registration_allowed(self, allowed: bool) -> None:
        async with self.db_context() as session:
            await AppSettingCRUD.set_value(
                session, ALLOW_REGISTRATION_KEY, "1" if allowed else "0"
            )

    async def change_password(
        self, *, email: str, user_modify_password: UserModifyPassword
    ) -> bool | None:
        """
        Update a user's password and revoke all existing sessions by incrementing token_version.
        """
        valid, message = validate_password(user_modify_password.new_password)
        if not valid:
            raise ValueError(message)
        async with self.db_context() as session:
            user = await self.user_crud.authenticate(
                session=session,
                email=email,
                password=user_modify_password.current_password,
            )
            if not user:
                message = _("Invalid current password")
                raise ValueError(message)

            await self.user_crud.update_password(
                session=session,
                user=user,
                new_password=user_modify_password.new_password,
                revoke_tokens=True,
            )
            return True

    async def initial_password_email(self) -> str | None:
        pending = app.storage.user.get(INITIAL_PASSWORD_SESSION_KEY)
        if pending is None:
            return None
        async with self.db_context() as session:
            user = await self.user_crud.get_by_email(session, pending["email"])
        if (
            user
            and user.is_active
            and user.must_change_password
            and user.token_version == pending["token_version"]
        ):
            return user.email
        app.storage.user.pop(INITIAL_PASSWORD_SESSION_KEY, None)
        return None

    async def complete_initial_password_change(
        self, credentials: UserModifyPassword
    ) -> None:
        pending = app.storage.user.get(INITIAL_PASSWORD_SESSION_KEY)
        if pending is None:
            raise ValueError(_("Invalid current password"))
        valid, message = validate_password(credentials.new_password)
        if not valid:
            raise ValueError(message)
        if credentials.new_password == credentials.current_password:
            raise ValueError(
                _("Choose a password different from the temporary password.")
            )

        async with self.db_context() as session:
            user = await self.user_crud.authenticate(
                session=session,
                email=pending["email"],
                password=credentials.current_password,
            )
            if (
                not user
                or not user.must_change_password
                or user.token_version != pending["token_version"]
            ):
                raise ValueError(_("Invalid current password"))

            if not await self.user_crud.complete_initial_password_change(
                session=session, user=user, new_password=credentials.new_password
            ):
                raise ValueError(_("Invalid current password"))
        app.storage.user.clear()

    async def set_active(
        self,
        *,
        email: str,
        is_active: bool,
    ) -> None:
        """
        Activate or deactivate a user account.
        """
        async with self.db_context() as session:
            user = await self.user_crud.get_by_email(session, email)
            if not user:
                raise ValueError(_("User does not exist"))

            await self.user_crud.update_status(
                session=session,
                user=user,
                is_active=is_active,
            )

    async def set_superuser(
        self,
        *,
        email: str,
        is_superuser: bool,
    ) -> None:
        """
        Grant or revoke superuser privileges for a user.
        """
        async with self.db_context() as session:
            user = await self.user_crud.get_by_email(session, email)
            if not user:
                raise ValueError(_("User does not exist"))

            await self.user_crud.update_superuser(
                session=session,
                user=user,
                is_superuser=is_superuser,
            )

    async def set_quota(self, *, email: str, quota_bytes: int) -> None:
        async with self.db_context() as session:
            user = await self.user_crud.get_by_email(session, email)
            if not user:
                raise ValueError(_("User does not exist"))

            await self.user_crud.update_quota(
                session=session,
                user=user,
                quota_bytes=quota_bytes,
            )

    async def revoke_sessions(self, *, email: str) -> None:
        async with self.db_context() as session:
            user = await self.user_crud.get_by_email(session, email)
            if not user:
                raise ValueError(_("User does not exist"))

            await self.user_crud.revoke_sessions(session=session, user=user)

    async def soft_delete_user(self, *, email: str) -> None:
        async with self.db_context() as session:
            user = await self.user_crud.get_by_email(session, email)
            if not user:
                raise ValueError(_("User does not exist"))

            await self.user_crud.soft_delete(
                session=session,
                user=user,
                deleted_at=utc_now(),
            )

    async def admin_reset_password(
        self, *, email: str, new_password: str | None = None
    ) -> str:
        password = new_password or generate_random_password(12)
        valid, message = validate_password(password)
        if not valid:
            raise ValueError(message)

        async with self.db_context() as session:
            user = await self.user_crud.get_by_email(session, email)
            if not user:
                raise ValueError(_("User does not exist"))

            await self.user_crud.update_password(
                session=session,
                user=user,
                new_password=password,
                revoke_tokens=True,
            )
        return password

    def _smtp_configured(self) -> bool:
        return bool(settings.SMTP_HOST and settings.SMTP_SENDER)

    @staticmethod
    def _hash_reset_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _build_reset_link(self, token: str) -> str:
        base_url = (
            settings.PASSWORD_RESET_BASE_URL
            or app.storage.general.get("service_url")
            or ""
        ).rstrip("/")
        if base_url:
            return f"{base_url}/reset-password/?token={token}"
        return f"/reset-password/?token={token}"

    async def request_password_reset(self, *, email: str) -> str:
        if not self._smtp_configured():
            return "not_configured"

        async with self.db_context() as session:
            user = await self.user_crud.get_by_email(session, email)
            if not user or not user.is_active or user.must_change_password:
                return "email_sent"

            token = secrets.token_urlsafe(32)
            token_hash = self._hash_reset_token(token)
            expires_at = utc_now() + timedelta(
                minutes=settings.PASSWORD_RESET_TOKEN_TTL_MINUTES
            )
            await PasswordResetTokenCRUD.create(
                session=session,
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires_at,
            )

        reset_link = self._build_reset_link(token)
        await asyncio.to_thread(self._send_password_reset_email, email, reset_link)
        return "email_sent"

    def _send_password_reset_email(self, email: str, reset_link: str) -> None:
        message = EmailMessage()
        message["Subject"] = _("Reset your StarDrive password")
        message["From"] = str(settings.SMTP_SENDER)
        message["To"] = email
        message.set_content(
            _(
                "Use this link to reset your StarDrive password. The link expires soon:\n\n{link}"
            ).format(link=reset_link)
        )

        if settings.SMTP_USE_TLS:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
                smtp.starttls()
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    smtp.login(
                        settings.SMTP_USERNAME,
                        settings.SMTP_PASSWORD.get_secret_value(),
                    )
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    smtp.login(
                        settings.SMTP_USERNAME,
                        settings.SMTP_PASSWORD.get_secret_value(),
                    )
                smtp.send_message(message)

    async def reset_password_with_token(self, *, token: str, new_password: str) -> bool:
        valid, message = validate_password(new_password)
        if not valid:
            raise ValueError(message)

        token_hash = self._hash_reset_token(token)
        async with self.db_context() as session:
            reset_token = await PasswordResetTokenCRUD.get_by_hash(session, token_hash)
            if (
                not reset_token
                or reset_token.used_at is not None
                or ensure_utc(reset_token.expires_at) < utc_now()
            ):
                raise ValueError(_("Invalid or expired reset token."))

            user = await self.user_crud.get_by_id(session, reset_token.user_id)
            if not user or not user.is_active or user.must_change_password:
                raise ValueError(_("Invalid or expired reset token."))

            await self.user_crud.update_password(
                session=session,
                user=user,
                new_password=new_password,
                revoke_tokens=True,
            )
            await PasswordResetTokenCRUD.mark_used(session, reset_token, utc_now())
            return True


async def get_user_timezone_from_browser():
    """
    Retrieve the user's timezone from the browser using JavaScript.
    Falls back to UTC if detection fails.
    """
    try:
        tz = await ui.run_javascript(
            "Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';"
        )
        app.storage.user["timezone"] = tz
        return tz
    except Exception as e:
        logger.error(_("Error getting user timezone: {error}").format(error=e))
        return "UTC"


def get_user_timezone():
    """
    Return the user's timezone as a ZoneInfo object, defaulting to UTC if not set.
    """
    return ZoneInfo(app.storage.user.get("timezone", "UTC"))
