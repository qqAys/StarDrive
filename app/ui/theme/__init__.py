from nicegui import app, ui

from app.ui.theme.base import Theme
from app.ui.theme.default import DefaultTheme

_current_theme = DefaultTheme


def set_theme(theme: type[Theme]):
    global _current_theme
    _current_theme = theme

    app.colors(**theme_colors(theme))


def apply_page_theme() -> None:
    ui.colors(**theme_colors(_current_theme))


def theme_colors(theme: type[Theme]) -> dict[str, str]:
    theme_instance = theme()
    return dict(
        primary=theme_instance.primary,
        secondary=theme_instance.secondary,
        accent=theme_instance.accent,
        dark=theme_instance.dark,
        dark_page=theme_instance.dark_background,
        positive=theme_instance.positive,
        negative=theme_instance.negative,
        warning=theme_instance.warning,
        info=theme_instance.info,
    )


def theme() -> type[Theme]:
    return _current_theme
