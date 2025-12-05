from nicegui import app, ui, APIRouter

from schemas.user_schema import UserLogin
from services import user_service
from ui.components.notify import notify
from utils import _

U = user_service.UserManager()

router = APIRouter(prefix="/login")


@router.page("/")
def login(redirect_to: str = None):

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

    with ui.card().classes("absolute-center"):
        email = ui.input(_("邮箱")).on("keyup.enter", try_login)
        password = ui.input(_("密码"), password=True, password_toggle_button=True).on(
            "keyup.enter", try_login
        )
        ui.button(_("登录"), on_click=try_login)
