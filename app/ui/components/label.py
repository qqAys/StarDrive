from nicegui import ui

from app.ui.theme import theme

dynamic_classes = f"text-[{theme().text_primary}] dark:text-[{theme().text_inverted}]"


def label(text: str, extra_classes: str | None = None):
    ui.label(text).classes(f"{dynamic_classes} {extra_classes}")
