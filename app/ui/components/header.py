from typing import Optional

from nicegui import ui

from app import globals
from app.config import settings
from app.core.i18n import _
from app.models.user_model import User
from app.services.user_service import UserManager
from app.ui.components.dialog import ConfirmDialog
from app.ui.components.fake_button import fake_button, nav_button
from app.ui.components.notify import notify


async def logout(user: UserManager):
    confirmed = await ConfirmDialog(
        title=_("Logout"),
        message=_("Are you sure you want to logout?"),
        warning=True,
    ).open()

    if not confirmed:
        return

    if await user.logout():
        notify.success(_("Logged out"))
        ui.timer(
            settings.NICEGUI_TIMER_INTERVAL,
            lambda: ui.navigate.to("/login"),
            once=True,
        )
    else:
        notify.error(_("Logout failed"))


class Header:
    def __init__(self):
        self.user_manager = globals.get_user_manager()
        self.header = ui.header
        self.user: Optional[User] = None

    async def render(self, title: Optional[str] = None, *args, **kwargs):
        page_title = f"{title} | {settings.APP_NAME}" if title else settings.APP_NAME
        ui.page_title(page_title)
        current_path = ui.context.client.page.path

        self.user = await self.user_manager.current_user()

        with self.header().classes(
            "fixed h-12 p-2 flex items-center gap-4 z-50"
        ) as header:
            with ui.link(target="/home/").classes("text-white no-underline"):
                ui.label(settings.APP_NAME).classes("font-bold")

            ui.space()

            if self.user:
                nav_button(
                    _("Profile"),
                    icon="account_circle",
                    link="/profile",
                    current_path=current_path,
                )
                if self.user.is_superuser:
                    nav_button(
                        _("Console"),
                        icon="dashboard",
                        link="/console",
                        current_path=current_path,
                    )
                fake_button(
                    _("Logout"), icon="logout", func=lambda: logout(self.user_manager)
                )
            else:
                nav_button(
                    _("Login"), icon="login", link="/login", current_path=current_path
                )

    def get_user(self) -> Optional[User]:
        return self.user
