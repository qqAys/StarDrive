from nicegui import ui, app

import globals
from config import settings
from ui.components.dialog import ConfirmDialog
from ui.components.fake_button import fake_button
from ui.components.notify import notify
from utils import _


class Header:

    def __init__(self):
        self.user_manager = globals.get_user_manager()
        ui.colors(primary=settings.APP_PRIMARY_COLOR)

        # favicon
        ui.add_head_html(
            f"""
    <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
    <meta name="apple-mobile-web-app-title" content="StarDrive" />
    <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png" />
    <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png" />
    <link rel="manifest" href="/site.webmanifest" />"""
        )

        self.header = ui.header

    @staticmethod
    async def logout():
        confirm = await ConfirmDialog(
            title=_("Logout"),
            message=_("Are you sure you want to logout?"),
            warning=True,
        ).open()

        if confirm:
            app.storage.user.update({"authenticated": False})
            notify.success(_("Logged out"))
            ui.timer(
                settings.NICEGUI_TIMER_INTERVAL,
                lambda: ui.navigate.to("/login"),
                once=True,
            )

    async def render(self, title=None, *args, **kwargs):
        if title is None:
            title = settings.APP_NAME
        else:
            title = title + " | " + settings.APP_NAME

        ui.page_title(title)

        with self.header().classes(
            "fixed h-12 p-2 flex items-center gap-4 z-50"
        ) as self.header:
            with ui.link(target="/home/").classes("text-white no-underline"):
                ui.label("StarDrive").classes("font-bold")

            ui.space()

            if await self.user_manager.is_superuser():
                fake_button(_("Console"), icon="dashboard", link="/console")
            if await self.user_manager.is_login():
                fake_button(_("Logout"), icon="logout", func=self.logout)
            else:
                fake_button(_("Login"), icon="login", link="/login")

    def inject(self):
        return self.header
