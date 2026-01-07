from nicegui import ui, app

from app.config import settings
from app.core.i18n import _
from app.models.file_download_model import FileDownloadInfo
from app.schemas.file_schema import FileType
from app.ui.components.base import BaseLayout
from app.ui.components.notify import notify


async def render_share_access_page(
    share_info: FileDownloadInfo,
    share_by: str | None = None,
):
    item_type = _("Folder") if share_info.type == FileType.DIR else _("File")

    async with BaseLayout().render(
        header=False,
        footer=True,
        args={"from_login_page": True},
    ):

        async def verify_access_code():
            code = access_code.value.strip()
            if not code:
                notify.warning(_("Access code is required"))
                return

            if code != share_info.access_code:
                notify.error(_("Invalid access code"))
                access_code.value = ""
                return

            notify.success(_("Access granted"))
            app.storage.user[f"share:{share_info.id}:access"] = True

            ui.timer(
                settings.NICEGUI_TIMER_INTERVAL,
                lambda: ui.navigate.to(ui.context.client.request.url.path),
                once=True,
            )

        with (
            ui.card(align_items="center")
            .classes("absolute-center w-[350px]")
            .props("flat rounded")
        ):
            # Logo
            ui.image("/android-chrome-512x512.png").classes("w-15 h-15")

            # Title
            ui.label(
                _("Access shared {item_type}").format(item_type=item_type.lower())
            ).classes("text-2xl font-bold")

            # Subtitle
            ui.label(_("Enter the access code to continue")).classes(
                "text-sm text-gray-500 text-center mb-4"
            )

            # Share info (lightweight)
            with ui.column().classes("w-full text-xs text-gray-500 mb-4 gap-1"):
                ui.label(_("Name: {name}").format(name=share_info.name))

                if share_info.user_id and share_by:
                    ui.label(_("Shared by {user}").format(user=share_by))

                ui.label(
                    _("Expires at {time}").format(
                        time=share_info.expires_at_utc.strftime("%Y-%m-%d %H:%M:%S %Z")
                    )
                )

            # Access code input
            access_code = (
                ui.input(
                    _("Access code"),
                )
                .on("keyup.enter", verify_access_code)
                .classes("w-full")
                .props("autofocus dense")
            )

            # Continue button
            ui.button(
                _("Continue"),
                on_click=verify_access_code,
            ).classes(
                "w-full mt-6 py-2"
            )
