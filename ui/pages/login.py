from nicegui import app, ui, APIRouter

from config import settings
from schemas.user_schema import UserLogin
from services import user_service
from ui.components.base import base_layout
from ui.components.notify import notify
from utils import _, is_valid_email

U = user_service.UserManager()

router = APIRouter(prefix="/login")


@router.page("/")
@base_layout(header=False, footer=True, footer_args={"from_login_page": True})
def login_page(redirect_to: str = None):

    if app.storage.user.get("authenticated", False):
        if redirect_to:
            ui.navigate.to(redirect_to)
        else:
            ui.navigate.to("/home")

    with ui.card(align_items="center").classes("absolute-center w-max"):
        with ui.card_section().classes("w-full"):
            with ui.column().classes("mb-4"):
                with ui.row().classes("text-3xl"):
                    ui.image("/android-chrome-512x512.png").classes("w-8 h-8")
                    ui.label(settings.APP_NAME).classes("text-2xl font-bold")
                ui.label(_("欢迎使用 {}").format(settings.APP_NAME)).classes("text-xs")

            def try_login():
                pre_login_user = UserLogin(email=email.value, password=password.value)
                login_user = U.login(pre_login_user)
                if not login_user:
                    notify.warning(_("用户不存在"))
                    return

                app.storage.user.update(
                    {"username": email.value, "authenticated": True}
                )

                notify.success(_("登录成功"))

                if redirect_to:
                    ui.navigate.to(redirect_to)
                else:
                    ui.timer(
                        settings.NICEGUI_TIMER_INTERVAL,
                        lambda: ui.navigate.to("/home"),
                        once=True,
                    )
                return

            email = (
                ui.input(
                    _("邮箱"),
                    validation=lambda value: (
                        None if is_valid_email(value) else _("邮箱格式错误")
                    ),
                )
                .on("keyup.enter", try_login)
                .classes("w-full")
            )
            password = (
                ui.input(_("密码"), password=True, password_toggle_button=True)
                .on("keyup.enter", try_login)
                .classes("w-full")
            )

            ui.button(_("登录"), on_click=try_login, icon="login").classes(
                "w-full mt-4"
            )
