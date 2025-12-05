from nicegui import ui, app

from ui.components.notify import notify
from utils import _


class Header:

    def __init__(self):
        self.header = ui.header

    @staticmethod
    def logout():
        app.storage.user.update({"authenticated": False})
        notify.success(_("已退出登录"))
        ui.timer(3.0, lambda: ui.navigate.to("/login"), once=True)

    def render(self):
        with self.header().classes("items-center p-1 no-wrap"):
            ui.label("StarDrive")
            ui.button(_("退出"), on_click=self.logout)
