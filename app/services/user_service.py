from zoneinfo import ZoneInfo

from nicegui import app, ui
from pydantic import EmailStr

from app.config import settings
from app.core.i18n import _
from app.core.logging import logger
from app.crud.user_crud import UserCRUD
from app.schemas.user_schema import UserLogin
from app.security.password import generate_random_password
from app.security.tokens import create_access_token, create_refresh_token


class UserManager:
    """
    NiceGUI 用户管理（DB 驱动）
    """

    def __init__(
        self,
        *,
        user_crud: type[UserCRUD],
        db_context,
    ):
        self.user_crud = user_crud
        self.db_context = db_context

    # --------------------------
    # 初始化：创建初始管理员
    # --------------------------
    async def initialize(self):
        async with self.db_context() as session:
            users = await self.user_crud.list(session=session, limit=1)
            if users:
                return

            email = settings.APP_INIT_USER
            password = generate_random_password()

            await self.user_crud.create(
                session=session,
                email=email,
                password=password,
                is_superuser=True,
            )

            logger.warning(
                _("Administrator account created. Email: {}, Password: {}").format(
                    email, password
                )
            )

    # --------------------------
    # 会话状态
    # --------------------------
    async def is_login(self) -> bool:
        return bool(await self.current_user())

    async def current_user(self):
        return await self._get_user(None)

    async def _get_user(self, email: EmailStr | None):
        email = email or app.storage.user.get("email")
        if not email:
            return None

        async with self.db_context() as session:
            user = await self.user_crud.get_by_email(session, email)

        if not user:
            return None

        if not user.is_active:
            app.storage.user.clear()
            return None

        if app.storage.user.get("token_version") != user.token_version:
            # 吊销会话
            app.storage.user.clear()
            return None

        return user

    async def is_active(self, email: EmailStr | None = None) -> bool:
        user = await self._get_user(email)
        return bool(user and user.is_active)

    async def is_superuser(self, email: EmailStr | None = None) -> bool:
        user = await self._get_user(email)
        return bool(user and user.is_superuser)

    # --------------------------
    # 登录 / 登出
    # --------------------------
    async def login(self, user_login: UserLogin):
        async with self.db_context() as session:
            user = await self.user_crud.authenticate(
                session=session,
                email=user_login.email,
                password=user_login.password,
            )

            if not user:
                raise ValueError(_("Invalid email or password"))

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

    # --------------------------
    # 用户管理
    # --------------------------
    async def create_user(
        self,
        *,
        email: str,
        password: str,
        is_superuser: bool = False,
    ):
        async with self.db_context() as session:
            existing = await UserCRUD.get_by_email(session, email)
            if existing:
                message = _("User already exists")
                logger.warning(message)
                raise ValueError(message)

            return await UserCRUD.create(
                session=session,
                email=email,
                password=password,
                is_superuser=is_superuser,
            )

    async def change_password(
        self,
        *,
        email: str,
        new_password: str,
    ) -> None:
        async with self.db_context() as session:
            user = await UserCRUD.get_by_email(session, email)
            if not user:
                message = _("User does not exist")
                logger.warning(message)
                raise ValueError(message)

            await UserCRUD.update_password(
                session=session,
                user=user,
                new_password=new_password,
                revoke_tokens=True,
            )

    async def set_active(
        self,
        *,
        email: str,
        is_active: bool,
    ) -> None:
        async with self.db_context() as session:
            user = await UserCRUD.get_by_email(session, email)
            if not user:
                raise ValueError(_("User does not exist"))

            await UserCRUD.update_status(
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
        async with self.db_context() as session:
            user = await UserCRUD.get_by_email(session, email)
            if not user:
                raise ValueError(_("User does not exist"))

            user.is_superuser = is_superuser
            session.add(user)
            await session.commit()


async def get_user_timezone_from_browser():
    try:
        tz = await ui.run_javascript(
            "Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';"
        )
        app.storage.user["timezone"] = tz
        return tz
    except Exception as e:
        logger.error(_("Error getting user timezone: {}").format(e))
        return "UTC"


def get_user_timezone():
    return ZoneInfo(app.storage.user.get("timezone", "UTC"))
