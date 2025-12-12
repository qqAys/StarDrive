from nicegui import ui

from ui.components.notify import notify
from utils import _


class Dialog:
    dialog_props = 'backdrop-filter="blur(2px) brightness(90%)"'

    def __init__(self):
        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self):
        r = await self.dialog
        return r


class ConfirmDialog(Dialog):

    def __init__(self, title: str, message: str | list = None, warning: bool = False):
        super().__init__()
        self.title = title
        self.message = message
        self.warning = warning

        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self):
        with self.dialog, ui.card():
            ui.label(self.title).classes("text-lg font-bold")
            if self.message:
                if isinstance(self.message, str):
                    ui.label(self.message)
                elif isinstance(self.message, list):
                    for message in self.message:
                        ui.label(message)

            with ui.row().classes("w-full justify-between"):
                ui.button(
                    _("Confirm"),
                    on_click=lambda: self.dialog.submit(True),
                    color="red" if self.warning else "green",
                )
                ui.button(_("Cancel"), on_click=lambda: self.dialog.submit(False))

        r = await self.dialog
        return r


class RenameDialog(Dialog):
    def __init__(self, title: str, old_name: str):
        super().__init__()
        self.title = title
        self.old_name = old_name

        self.dialog = ui.dialog().props(self.dialog_props)

    async def open(self):
        with self.dialog, ui.card():
            ui.label(self.title).classes("w-full text-lg font-bold")
            new_name = ui.input(label=_("New name"), value=self.old_name)

            def is_same(a, b):
                return a == b

            def on_confirm():
                if is_same(new_name.value, self.old_name):
                    notify.warning(_("New name cannot be the same as the old name"))
                    return None
                return self.dialog.submit(new_name.value)

            with ui.row().classes("w-full justify-between"):
                ui.button(
                    _("Confirm"),
                    on_click=on_confirm,
                    color="green",
                )
                ui.button(_("Cancel"), on_click=lambda: self.dialog.submit(None))

        r = await self.dialog
        return r