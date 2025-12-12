from typing import Callable, Any, overload

from nicegui import ui

fake_button_style = "cursor-pointer text-white font-medium hover:bg-white/20 rounded ring-1 ring-white/10 px-2 py-1 transition-colors duration-200"


@overload
def fake_button(text: str, icon: str = None, func: Callable[[], Any] = None): ...


@overload
def fake_button(text: str, icon: str = None, link: str = None): ...


@overload
def fake_button(text: str = None, link: str = None): ...


@overload
def fake_button(text: str = None, func: Callable[[], Any] = None): ...


@overload
def fake_button(icon: str = None, link: str = None): ...


@overload
def fake_button(icon: str = None, func: Callable[[], Any] = None): ...


def fake_button(
    text: str = None,
    icon: str = None,
    func: Callable[[], Any] = None,
    link: str = None,
    text_primary: bool = False,
):
    with ui.link(target=link).classes(replace=fake_button_style) as b:
        with ui.row().classes("items-center"):
            if icon:
                ui.icon(icon)
            if text:
                ui.label(text).classes(
                    f"gt-sm{" text-primary" if text_primary else ""}"
                )

    if func and not link:
        b.on("click", func)

    return b
