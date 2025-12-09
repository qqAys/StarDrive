from nicegui import ui

from config import settings
from ui.components.link import link


class Footer:

    def __init__(self):
        self.footer = ui.footer

    def render(self, from_login_page: bool = False):
        if from_login_page:
            with self.footer().classes("bg-transparent"):
                with ui.row().classes("items-center w-full no-wrap"):
                    ui.space()

                    ui.label(f"{settings.APP_NAME} v{settings.APP_VERSION}").classes(
                        "text-grey-5 font-bold"
                    )
                    link(settings.APP_GITHUB_URL, text="GitHub", bold=True, _blank=True)
        else:
            pass
