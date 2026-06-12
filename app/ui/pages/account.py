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
from app.ui.theme import theme
from app.utils.platform import detect_platform


register_routes = "/register"
forgot_routes = "/forgot-password"
reset_routes = "/reset-password"


@app.get(register_routes)
def register_index():
    return RedirectResponse(f"{register_routes}/")


@app.get(forgot_routes)
def forgot_index():
    return RedirectResponse(f"{forgot_routes}/")


@app.get(reset_routes)
def reset_index():
    return RedirectResponse(f"{reset_routes}/")


register_router = APIRouter(prefix=register_routes)
forgot_router = APIRouter(prefix=forgot_routes)
reset_router = APIRouter(prefix=reset_routes)


def _auth_card():
    return (
        ui.card(align_items="center")
        .classes("absolute-center w-[350px] bg-transparent border-0 shadow-none")
        .props("flat")
    )


def _brand(title: str, subtitle: str):
    ui.image("/android-chrome-512x512.png").classes("w-15 h-15")
    ui.label(settings.APP_NAME).classes(
        f"text-2xl font-bold text-[{theme().text_primary}]"
    )
    ui.label(title).classes(f"text-sm text-[{theme().text_secondary}]")
    ui.label(subtitle).classes(f"text-xs text-[{theme().text_muted}] text-center")


@register_router.page("/")
async def register_page():
    async with BaseLayout().render(
        header=False,
        footer=True,
        args={"from_login_page": True},
    ):
        user_manager = globals.get_user_manager()
        if not await user_manager.is_registration_allowed():
            notify.warning(_("Registration is currently disabled."))
            ui.timer(
                settings.NICEGUI_TIMER_INTERVAL,
                lambda: ui.navigate.to("/login/"),
                once=True,
            )
            return

        async def try_register():
            if password.value != confirm_password.value:
                notify.error(_("Passwords do not match."))
                return
            try:
                await user_manager.register_user(
                    email=email.value, password=password.value
                )
                await user_manager.login(
                    UserLogin(email=email.value, password=password.value)
                )
            except Exception as exc:
                notify.error(str(exc))
                return

            user_timezone = await get_user_timezone_from_browser()
            app.storage.user.update({"timezone": user_timezone})
            platform_info = await detect_platform()
            app.storage.user.update(
                {
                    "is_mac": platform_info.get("is_mac", False),
                    "is_mobile": platform_info.get("is_mobile", False),
                }
            )
            notify.success(_("Account created successfully"))
            ui.timer(
                settings.NICEGUI_TIMER_INTERVAL,
                lambda: ui.navigate.to("/home/"),
                once=True,
            )

        with _auth_card():
            _brand(_("Create account"), _("Register a new StarDrive account."))
            with ui.column().classes("w-full gap-0"):
                email = (
                    ui.input(
                        _("Email"),
                        validation=lambda value: (
                            None
                            if is_valid_email(value)
                            else _("Invalid email address")
                        ),
                    )
                    .on("keyup.enter", try_register)
                    .classes("w-full")
                    .props("autofocus dense")
                )
                password = (
                    ui.input(_("Password"), password=True, password_toggle_button=True)
                    .on("keyup.enter", try_register)
                    .classes("w-full")
                    .props("dense")
                )
                confirm_password = (
                    ui.input(
                        _("Confirm password"),
                        password=True,
                        password_toggle_button=True,
                    )
                    .on("keyup.enter", try_register)
                    .classes("w-full")
                    .props("dense")
                )
            ui.button(_("Create account"), on_click=try_register).classes(
                "w-full mt-6 py-2"
            )
            ui.link(_("Back to sign in"), "/login/").classes("text-sm")


@forgot_router.page("/")
async def forgot_password_page():
    async with BaseLayout().render(
        header=False,
        footer=True,
        args={"from_login_page": True},
    ):
        user_manager = globals.get_user_manager()

        async def submit_reset_request():
            try:
                status = await user_manager.request_password_reset(email=email.value)
            except Exception as exc:
                notify.error(str(exc))
                return

            if status == "not_configured":
                notify.warning(
                    _(
                        "Password reset email is not configured. Contact an administrator."
                    )
                )
            else:
                notify.success(_("If the account exists, a reset email has been sent."))

        with _auth_card():
            _brand(
                _("Reset password"),
                _("Enter your account email to receive a reset link."),
            )
            email = (
                ui.input(
                    _("Email"),
                    validation=lambda value: (
                        None if is_valid_email(value) else _("Invalid email address")
                    ),
                )
                .on("keyup.enter", submit_reset_request)
                .classes("w-full")
                .props("autofocus dense")
            )
            ui.button(_("Send reset link"), on_click=submit_reset_request).classes(
                "w-full mt-6 py-2"
            )
            ui.link(_("Back to sign in"), "/login/").classes("text-sm")


@reset_router.page("/")
async def reset_password_page(token: str | None = None):
    async with BaseLayout().render(
        header=False,
        footer=True,
        args={"from_login_page": True},
    ):
        user_manager = globals.get_user_manager()

        async def submit_new_password():
            if not token:
                notify.error(_("Invalid or expired reset token."))
                return
            if password.value != confirm_password.value:
                notify.error(_("Passwords do not match."))
                return
            try:
                await user_manager.reset_password_with_token(
                    token=token,
                    new_password=password.value,
                )
            except Exception as exc:
                notify.error(str(exc))
                return
            notify.success(_("Password reset successfully"))
            ui.timer(
                settings.NICEGUI_TIMER_INTERVAL,
                lambda: ui.navigate.to("/login/"),
                once=True,
            )

        with _auth_card():
            _brand(_("Set new password"), _("Choose a new password for your account."))
            with ui.column().classes("w-full gap-0"):
                password = (
                    ui.input(
                        _("New password"), password=True, password_toggle_button=True
                    )
                    .on("keyup.enter", submit_new_password)
                    .classes("w-full")
                    .props("autofocus dense")
                )
                confirm_password = (
                    ui.input(
                        _("Confirm password"),
                        password=True,
                        password_toggle_button=True,
                    )
                    .on("keyup.enter", submit_new_password)
                    .classes("w-full")
                    .props("dense")
                )
            ui.button(_("Reset password"), on_click=submit_new_password).classes(
                "w-full mt-6 py-2"
            )
            ui.link(_("Back to sign in"), "/login/").classes("text-sm")
