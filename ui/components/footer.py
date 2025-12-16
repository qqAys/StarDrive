from nicegui import ui

from config import settings
from ui.components.link import link


class Footer:

    def __init__(self):
        self.footer = ui.footer

        self.content_container = None

    @staticmethod
    def app_info():
        with ui.row().classes(
            "w-full h-full flex justify-end items-center pr-4 gap-4 text-sm text-gray-500"
        ):
            ui.label(f"{settings.APP_NAME} v{settings.APP_VERSION}").classes(
                "text-grey-5 font-bold"
            )
            link(settings.APP_GITHUB_URL, text="GitHub", bold=True, _blank=True)

    def render(self, from_login_page: bool = False, *args, **kwargs):
        bg_class = "bg-transparent" if from_login_page else ""
        with self.footer().classes(f"fixed bottom-0 left-0 right-0 p-2 {bg_class} "):
            self.content_container = ui.element().classes(
                "absolute inset-y-0 left-0 right-50 px-4 flex items-center gap-4"
            )
            self.app_info()

    def inject(self):
        return self.content_container
