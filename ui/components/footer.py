from nicegui import ui

from config import settings
from ui.components.link import link


class Footer:

    def __init__(self):
        self.footer = ui.footer

    @staticmethod
    def app_info():
        with ui.row().classes("items-center w-full no-wrap"):
            ui.space()

            ui.label(f"{settings.APP_NAME} v{settings.APP_VERSION}").classes(
                "text-grey-5 font-bold"
            )
            link(settings.APP_GITHUB_URL, text="GitHub", bold=True, _blank=True)

    def render(self, from_login_page: bool = False, *args, **kwargs):
        with self.footer().classes("bg-transparent" if from_login_page else "p-2"):
            self.app_info()
