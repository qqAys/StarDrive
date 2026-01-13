from fastapi.responses import RedirectResponse
from nicegui import ui, APIRouter, app

from app import globals
from app.config import settings
from app.core.i18n import _, APP_DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES_MAP
from app.schemas.user_schema import UserModifyPassword
from app.security.guards import require_user
from app.ui.components import max_w
from app.ui.components.base import BaseLayout
from app.ui.components.base import logout
from app.ui.components.notify import notify

this_page_routes = "/account"


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
        args={"title": _("Account")},
    ):

        user_manager = globals.get_user_manager()

        with ui.element().classes("w-full " + max_w + " space-y-6"):

            # =============================
            # Account Info Card
            # =============================
            with ui.card().classes("w-full"):
                ui.label(_("Account Information")).classes("text-lg font-semibold mb-4")

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
            # Preferences / Language Card
            # =============================
            with ui.card().classes("w-full"):
                ui.label(_("Preferences")).classes("text-lg font-semibold mb-4")

                current_lang = app.storage.user.get(
                    "default_lang", APP_DEFAULT_LANGUAGE
                )

                ui.label(_("Language")).classes("text-sm text-gray-500 mb-2")

                language_select = ui.select(
                    options=SUPPORTED_LANGUAGES_MAP,
                    value=current_lang,
                ).classes("w-full")

                async def handle_change_language():
                    new_lang = language_select.value
                    if new_lang == current_lang:
                        notify.info(_("Language unchanged"))
                        return

                    app.storage.user["default_lang"] = new_lang
                    notify.success(_("Language changed"))

                    ui.timer(
                        settings.NICEGUI_TIMER_INTERVAL,
                        lambda: ui.navigate.to(this_page_routes),
                        once=True,
                    )

                ui.button(
                    _("Save language"),
                    on_click=handle_change_language,
                ).classes("mt-4")

            # =============================
            # Danger Zone
            # =============================
            with ui.card().classes("w-full border border-red-300"):

                ui.label(_("Security")).classes("text-lg font-semibold mb-4 text-red-600")

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

                ui.separator()

                ui.label(_("Account")).classes("text-lg font-semibold mb-4 text-red-600")

                async def handle_logout():
                    await logout(user_manager)

                with ui.row().classes("justify-between items-center"):
                    ui.label(_("Log out from this account"))
                    ui.button(
                        _("Logout"),
                        on_click=handle_logout,
                        color="negative",
                    )
