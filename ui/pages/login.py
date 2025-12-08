from nicegui import app, ui, APIRouter, html

from config import settings
from schemas.user_schema import UserLogin
from services import user_service
from ui.components.header import Header
from ui.components.notify import notify
from utils import _

U = user_service.UserManager()

router = APIRouter(prefix="/login")


@router.page("/")
def login(redirect_to: str = None):
    Header()

    def try_login():
        pre_login_user = UserLogin(email=email.value, password=password.value)
        login_user = U.login(pre_login_user)
        if not login_user:
            notify.warning(_("用户不存在"))
            return

        app.storage.user.update({"username": email.value, "authenticated": True})

        notify.success(_("登录成功"))

        if redirect_to:
            ui.navigate.to(redirect_to)
        else:
            ui.timer(3.0, lambda: ui.navigate.to("/home"), once=True)
        return

    if app.storage.user.get("authenticated", False):
        if redirect_to:
            ui.navigate.to(redirect_to)
        else:
            ui.navigate.to("/home")

    with ui.card(align_items="center").classes("absolute-center w-max"):
        with ui.card_section():
            with ui.column().classes("mb-4"):
                with ui.row().classes("text-3xl"):
                    ui.image("/android-chrome-512x512.png").classes("w-8 h-8")
                    ui.label(settings.APP_NAME).classes("text-2xl font-bold")
                ui.label(_("欢迎使用 {}").format(settings.APP_NAME)).classes("text-xs")
            email = ui.input(_("邮箱")).on("keyup.enter", try_login)
            password = ui.input(
                _("密码"), password=True, password_toggle_button=True
            ).on("keyup.enter", try_login)
            ui.button(_("登录"), on_click=try_login, icon="login").classes(
                "w-full mt-4"
            )

    with ui.footer().classes("bg-grey-7 text-s"):
        with ui.row().classes("items-center w-full no-wrap"):
            ui.label(f"{settings.APP_NAME} v{settings.APP_VERSION}").classes(
                "text-grey-5"
            )

            ui.space()

            # github链接
            with ui.link(target=settings.APP_GITHUB_URL).classes("text-grey-5 text-xl"):
                ui.icon("eva-github")
