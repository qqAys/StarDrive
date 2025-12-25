from nicegui import ui, app

from app.config import settings
from app.core.i18n import _
from app.models.file_download_model import FileDownloadInfo
from app.schemas.file_schema import FileType
from app.ui.components.base import BaseLayout
from app.ui.components.notify import notify


async def render_share_access_page(
    share_info: FileDownloadInfo, share_by: str | None = None
):
    """
    Render a page prompting the user to enter an access code to view a protected shared item.

    This page is shown when a share link requires an access code and the user hasn't yet provided it.
    Upon successful verification, the user is granted temporary access and redirected back to the share page.
    """
    item_type = _("Folder") if share_info.type == FileType.DIR else _("File")

    async with BaseLayout().render(
        header=False, footer=True, args={"from_login_page": True}
    ):
        with ui.card(align_items="center").classes("absolute-center w-max"):
            with ui.card_section().classes("w-full"):
                # App branding and instruction
                with ui.column().classes("mb-4 items-center"):
                    with ui.row().classes("text-3xl items-center gap-2"):
                        ui.image("/android-chrome-512x512.png").classes("w-8 h-8")
                        ui.label(settings.APP_NAME).classes("text-2xl font-bold")
                    ui.label(
                        _("Enter the access code to view this {item_type}").format(
                            item_type=item_type
                        )
                    ).classes("text-xs text-gray-500 text-center")

                # Shared item summary
                with ui.card().classes("w-full mb-4 p-3"):
                    ui.label(_("Shared item")).classes("text-sm font-bold mb-2")
                    ui.label(_("Name: {name}").format(name=share_info.name)).classes(
                        "text-xs"
                    )

                    if share_info.user_id and share_by:
                        ui.label(_("Shared by {user}").format(user=share_by)).classes(
                            "text-xs"
                        )

                    ui.label(
                        _("Expires at {time}").format(
                            time=share_info.expires_at_utc.strftime(
                                "%Y-%m-%d %H:%M:%S %Z"
                            )
                        )
                    ).classes("text-xs")

                # Access code input field
                access_code_input = (
                    ui.input(
                        _("Access code"),
                        placeholder=_("Enter access code"),
                    )
                    .classes("w-full")
                    .props("autofocus")
                )

                async def verify_access_code():
                    """Validate the entered access code against the expected value."""
                    code_entered = access_code_input.value.strip()
                    if not code_entered:
                        notify.warning(_("Access code is required"))
                        return

                    if code_entered == share_info.access_code:
                        notify.success(_("Access granted"))
                        # Store access grant in user session
                        app.storage.user[f"share:{share_info.id}:access"] = True
                        # Redirect back to the same share URL after a short delay
                        ui.timer(
                            settings.NICEGUI_TIMER_INTERVAL,
                            lambda: ui.navigate.to(ui.context.client.request.url.path),
                            once=True,
                        )
                    else:
                        notify.error(_("Invalid access code"))
                        access_code_input.value = ""

                # Submit on Enter key
                access_code_input.on("keyup.enter", verify_access_code)

                # Continue button
                ui.button(
                    _("Continue"),
                    on_click=verify_access_code,
                    icon="check",
                ).classes("w-full mt-4")
