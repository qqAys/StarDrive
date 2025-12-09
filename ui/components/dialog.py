from nicegui import ui

from utils import _


class Dialog:
    dialog_props = 'backdrop-filter="blur(2px) brightness(90%)"'

    def __init__(self):
        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self):
        r = await self.dialog
        return r


class AskDialog(Dialog):

    def __init__(self, title: str, message: str):
        super().__init__()
        self.title = title
        self.message = message

        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self):
        with self.dialog, ui.card():
            ui.label(self.title).classes("text-lg font-bold")
            ui.label(self.message)

            with ui.row():
                ui.button(_("Yes"), on_click=lambda: self.dialog.submit(True))
                ui.button(_("No"), on_click=lambda: self.dialog.submit(False))
        r = await self.dialog
        return r
