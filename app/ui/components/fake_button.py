from typing import Callable, Any
from nicegui import ui

BASE_BUTTON = [
    "cursor-pointer",
    "font-medium",
    "rounded",
    "px-2",
    "py-1",
    # "transition-colors",
    "duration-200",
    "flex",
    "items-center",
    "gap-1",
    "text-white",
    "no-underline"
]

BUTTON_VARIANTS = {
    "default": [
        "hover:bg-white/20",
    ],
    "active": [
        "bg-white/20",
    ],
}


def fake_button(
        text: str | None = None,
        icon: str | None = None,
        *,
        link: str | None = None,
        func: Callable[[], Any] | None = None,
        variant: str = "default",
        extra_classes: list[str] | None = None,
):
    classes = (
            BASE_BUTTON
            + BUTTON_VARIANTS.get(variant, [])
            + (extra_classes or [])
    )

    with ui.link(target=link).classes(" ".join(classes)) as b:
        if icon:
            ui.icon(icon)
        if text:
            ui.label(text).classes("gt-sm")

    if func and not link:
        b.on("click", func)

    return b


def nav_button(
        text: str,
        *,
        icon: str | None = None,
        link: str,
        current_path: str,
):
    is_active = current_path.rstrip("/") == link.rstrip("/")

    return fake_button(
        text=text,
        icon=icon,
        link=link,
        extra_classes=(
            BUTTON_VARIANTS["active"]
            if is_active
            else None
        ),
    )
