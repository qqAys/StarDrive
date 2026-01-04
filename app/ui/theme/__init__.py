from nicegui import ui
from nicegui.events import ValueChangeEventArguments

from app.ui.theme.default import DefaultTheme
from app.ui.theme.base import Theme

_current_theme = DefaultTheme


def set_theme(theme):
    global _current_theme
    _current_theme = theme

    ui.colors(
        primary=theme().primary,
        secondary=theme().secondary,
        accent=theme().accent,
        dark=theme().dark,
        dark_page=theme().dark_background,
        positive=theme().positive,
        negative=theme().negative,
        warning=theme().warning,
        info=theme().info,
    )


def theme():
    return _current_theme

