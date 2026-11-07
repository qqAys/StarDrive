from nicegui import app, ui, APIRouter
from starlette.responses import RedirectResponse

from app import globals
from app.config import settings
from app.core.i18n import _
from app.schemas.user_schema import UserLogin, UserModifyPassword
from app.security.validators import is_valid_email
from app.services.user_service import get_user_timezone_from_browser
from app.ui.components.base import BaseLayout
from app.ui.components.notify import notify
from app.ui.theme import theme
from app.utils.platform import detect_platform

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

        if await user_manager.initial_password_email():
            with ui.card(align_items="center").classes("absolute-center w-[350px]"):
                ui.label(
                    _(
                        "Change your temporary password in the browser before signing in."
                    )
                )
                current = ui.input(
                    _("Current password"), password=True, password_toggle_button=True
                ).classes("w-full")
                new = ui.input(
                    _("New password"), password=True, password_toggle_button=True
                ).classes("w-full")
                confirm = ui.input(
                    _("Confirm new password"),
                    password=True,
                    password_toggle_button=True,
                ).classes("w-full")

                async def change_initial_password():
                    if new.value != confirm.value:
                        notify.error(_("Passwords do not match"))
                        return
                    try:
                        await user_manager.complete_initial_password_change(
                            UserModifyPassword(
                                current_password=current.value, new_password=new.value
                            )
                        )
                    except ValueError as exc:
                        notify.error(str(exc))
                        return
                    notify.success(_("Password changed successfully"))
                    ui.navigate.to("/login/")

                confirm.on("keyup.enter", change_initial_password)
                ui.button(_("Change password"), on_click=change_initial_password)

                async def cancel_initial_password_change():
                    await user_manager.logout()
                    ui.navigate.to("/login/")

                ui.button(_("Logout"), on_click=cancel_initial_password_change).props(
                    "flat"
                )
            return

        # Early redirect if already logged in
        if await user_manager.is_login():
            notify.success(_("You are already signed in"))
            redirect()
            return

        # Login form UI
        with (
            ui.card(align_items="center")
            .classes("absolute-center w-[350px] bg-transparent border-0 shadow-none")
            .props("flat")
        ):
            # App branding
            ui.image("/android-chrome-512x512.png").classes("w-15 h-15")
            ui.label(settings.APP_NAME).classes(
                f"text-2xl font-bold text-[{theme().text_primary}]"
            )

            ui.label(_("Sign in to your account")).classes(
                f"text-sm text-[{theme().text_secondary}]"
            )

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

                if login_user.must_change_password:
                    ui.navigate.to("/login/")
                    return

                notify.success(_("Signed in successfully"))

                # Store user's timezone from browser
                user_timezone = await get_user_timezone_from_browser()
                app.storage.user.update({"timezone": user_timezone})

                # Store user's platform
                platform_info = await detect_platform()
                app.storage.user.update(
                    {
                        "is_mac": platform_info.get("is_mac", False),
                        "is_mobile": platform_info.get("is_mobile", False),
                    }
                )

                redirect()

            with ui.column().classes("w-full gap-0"):
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
                    .props("autofocus dense")
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
                    .props("dense")
                )

            # Sign-in button
            ui.button(
                _("Sign in"),
                on_click=try_login,
            ).classes("w-full mt-6 py-2")

            with ui.row().classes("w-full justify-between text-sm"):
                if await user_manager.is_registration_allowed():
                    ui.link(_("Create account"), "/register/")
                ui.link(_("Forgot password?"), "/forgot-password/")
