from fastapi.responses import RedirectResponse
from nicegui import ui, APIRouter, app

from app import globals
from app.config import settings
from app.core.i18n import _, SUPPORTED_LANGUAGES
from app.schemas.user_schema import UserModifyPassword
from app.security.guards import require_user
from app.ui.components import max_w
from app.ui.components.base import BaseLayout
from app.ui.components.header import logout
from app.ui.components.notify import notify

this_page_routes = "/profile"


@app.get(this_page_routes)
def browser_index():
    return RedirectResponse(this_page_routes + "/")


router = APIRouter(prefix=this_page_routes)


@router.page("/")
@require_user
async def index():
    async with BaseLayout().render(
        header=True,
        footer=True,
        args={"title": _("Profile")},
    ):

        user_manager = globals.get_user_manager()

        # =============================
        # Language switch
        # =============================
        def change_language(lang_code: str):
            current_lang_code = app.storage.user.get("default_lang", "en_US")
            if current_lang_code != lang_code:
                app.storage.user["default_lang"] = lang_code
                notify.success(_("Language changed to {}").format(lang_code))
                ui.timer(
                    settings.NICEGUI_TIMER_INTERVAL,
                    lambda: ui.navigate.to(this_page_routes),
                )

        with ui.element().classes("w-full " + max_w + " space-y-6"):

            # =============================
            # Header actions
            # =============================
            with ui.row().classes("w-full items-center justify-end"):
                with ui.dropdown_button(icon="translate", auto_close=True):
                    for lang in SUPPORTED_LANGUAGES:
                        ui.item(
                            lang,
                            on_click=lambda l=lang: change_language(l),
                        )

            # =============================
            # Profile Info Card
            # =============================
            with ui.card().classes("w-full"):
                ui.label(_("Profile Information")).classes("text-lg font-semibold mb-4")

                with ui.column().classes("gap-2"):
                    with ui.row().classes("justify-between"):
                        ui.label(_("ID"))
                        ui.label(app.storage.user.get("user_id")).classes(
                            "text-gray-600"
                        )
                    with ui.row().classes("justify-between"):
                        ui.label(_("Username"))
                        ui.label(app.storage.user.get("email")).classes("text-gray-600")

            # =============================
            # Change Password Card
            # =============================
            with ui.card().classes("w-full"):
                ui.label(_("Security")).classes("text-lg font-semibold mb-4")

                old_password = ui.input(
                    _("Current password"),
                    password=True,
                    password_toggle_button=True,
                ).classes("w-full")
                new_password = ui.input(
                    _("New password"),
                    password=True,
                    password_toggle_button=True,
                ).classes("w-full")
                confirm_password = ui.input(
                    _("Confirm new password"),
                    password=True,
                    password_toggle_button=True,
                ).classes("w-full")

                async def handle_change_password():
                    if new_password.value != confirm_password.value:
                        notify.error(_("Passwords do not match"))
                        return

                    try:
                        await user_manager.change_password(
                            email=app.storage.user.get("email"),
                            user_modify_password=UserModifyPassword(
                                current_password=old_password.value,
                                new_password=new_password.value,
                            ),
                        )
                        notify.success(_("Password changed successfully"))
                        old_password.clear()
                        new_password.clear()
                        confirm_password.clear()
                        ui.timer(
                            settings.NICEGUI_TIMER_INTERVAL,
                            lambda: ui.navigate.to("/login"),
                            once=True,
                        )
                    except Exception as e:
                        notify.error(str(e))

                ui.button(
                    _("Change password"),
                    on_click=handle_change_password,
                ).classes("mt-4")

            # =============================
            # Danger Zone
            # =============================
            with ui.card().classes("w-full border border-red-300"):
                ui.label(_("Danger Zone")).classes(
                    "text-lg font-semibold text-red-600 mb-4"
                )

                async def handle_logout():
                    await logout(user_manager)

                with ui.row().classes("justify-between items-center"):
                    ui.label(_("Log out from this account"))
                    ui.button(
                        _("Logout"),
                        on_click=handle_logout,
                        color="negative",
                    )
