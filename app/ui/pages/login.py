from nicegui import app, ui, APIRouter
from starlette.responses import RedirectResponse

from app import globals
from app.config import settings
from app.core.i18n import _
from app.schemas.user_schema import UserLogin
from app.security.validators import is_valid_email
from app.services.user_service import get_user_timezone_from_browser
from app.ui.components.base import BaseLayout
from app.ui.components.notify import notify

this_page_routes = "/login"


@app.get(this_page_routes)
def login_index():
    return RedirectResponse(this_page_routes + "/")


router = APIRouter(prefix=this_page_routes)


@router.page("/")
async def login_page(redirect_to: str = None):
    async with BaseLayout().render(
        header=False, footer=True, args={"from_login_page": True}
    ):
        user_manager = globals.get_user_manager()

        def redirect():
            ui.timer(
                settings.NICEGUI_TIMER_INTERVAL,
                lambda: ui.navigate.to(redirect_to if redirect_to else "/home"),
                once=True,
            )

        if await user_manager.is_login():
            notify.success(_("Logged in"))
            redirect()
            return

        with ui.card(align_items="center").classes("absolute-center w-max"):
            with ui.card_section().classes("w-full"):
                with ui.column().classes("mb-4"):
                    with ui.row().classes("text-3xl"):
                        ui.image("/android-chrome-512x512.png").classes("w-8 h-8")
                        ui.label(settings.APP_NAME).classes("text-2xl font-bold")
                    ui.label(_("Welcome to {}").format(settings.APP_NAME)).classes(
                        "text-xs"
                    )

                async def try_login():
                    pre_login_user = UserLogin(
                        email=email.value, password=password.value
                    )
                    try:
                        login_user = await user_manager.login(pre_login_user)
                    except Exception as e:
                        notify.error(e)
                        return
                    if not login_user:
                        notify.warning(_("User not found"))
                        return

                    notify.success(_("Login successful"))

                    # 获取用户时区
                    user_timezone = await get_user_timezone_from_browser()
                    app.storage.user.update({"timezone": user_timezone})

                    # 跳转
                    redirect()

                email = (
                    ui.input(
                        _("Email"),
                        validation=lambda value: (
                            None
                            if is_valid_email(value)
                            else _("Invalid email address")
                        ),
                    )
                    .on("keyup.enter", try_login)
                    .classes("w-full")
                )
                password = (
                    ui.input(_("Password"), password=True, password_toggle_button=True)
                    .on("keyup.enter", try_login)
                    .classes("w-full")
                )

                ui.button(_("Login"), on_click=try_login, icon="login").classes(
                    "w-full mt-4"
                )
