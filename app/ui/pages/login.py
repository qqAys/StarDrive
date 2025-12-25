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
    """Redirect the base login route to its index page."""
    return RedirectResponse(f"{this_page_routes}/")


router = APIRouter(prefix=this_page_routes)


@router.page("/")
async def login_page(redirect_to: str | None = None):
    """
    Render the user login page.

    If the user is already authenticated, they are redirected to the home page (or the provided 'redirect_to' URL).
    Otherwise, a login form with email and password fields is displayed.
    """
    async with BaseLayout().render(
        header=False,
        footer=True,
        args={"from_login_page": True},
    ):
        user_manager = globals.get_user_manager()

        def redirect():
            """Redirect the user after successful login."""
            ui.timer(
                settings.NICEGUI_TIMER_INTERVAL,
                lambda: ui.navigate.to(redirect_to or "/home"),
                once=True,
            )

        # Early redirect if already logged in
        if await user_manager.is_login():
            notify.success(_("You are already signed in"))
            redirect()
            return

        # Login form UI
        with ui.card(align_items="center").classes("absolute-center w-max"):
            with ui.card_section().classes("w-full"):
                # App branding
                with ui.column().classes("mb-4"):
                    with ui.row().classes("text-3xl items-center gap-2"):
                        ui.image("/android-chrome-512x512.png").classes("w-8 h-8")
                        ui.label(settings.APP_NAME).classes("text-2xl font-bold")
                    ui.label(
                        _("Welcome to {app_name}").format(app_name=settings.APP_NAME)
                    ).classes("text-xs")

                async def try_login():
                    """Attempt to log in the user with the provided credentials."""
                    credentials = UserLogin(
                        email=email.value,
                        password=password.value,
                    )
                    try:
                        login_user = await user_manager.login(credentials)
                    except Exception as e:
                        notify.error(str(e))
                        return

                    if not login_user:
                        notify.warning(_("Account not found"))
                        return

                    notify.success(_("Signed in successfully"))

                    # Store user's timezone from browser
                    user_timezone = await get_user_timezone_from_browser()
                    app.storage.user.update({"timezone": user_timezone})

                    redirect()

                # Email input with validation
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

                # Password input
                password = (
                    ui.input(
                        _("Password"),
                        password=True,
                        password_toggle_button=True,
                    )
                    .on("keyup.enter", try_login)
                    .classes("w-full")
                )

                # Sign-in button
                ui.button(
                    _("Sign in"),
                    on_click=try_login,
                    icon="login",
                ).classes("w-full mt-4")
