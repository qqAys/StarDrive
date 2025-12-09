from typing import Callable, Any

from nicegui import ui

fake_button_style = "text-white font-medium hover:bg-white/20 rounded ring-1 ring-white/10 px-2 py-1 transition-colors duration-200"


def fake_button(text: str, icon: str = None, on_click: Callable[[], Any] = None):

    with ui.link().classes(replace=fake_button_style) as b:
        with ui.row().classes("items-center"):
            if icon:
                ui.icon(icon)
            ui.label(text).classes("gt-sm")

    b.on("click", on_click)

    return b
