from app.ui.theme.base import Theme


class DefaultTheme(Theme):

    # Brand
    primary = "#7E75F2"
    secondary = "#0F766E"
    dark = "#1F2937"
    accent = "#B45309"

    # Status, Notification
    positive = "#16A34A"
    negative = "#DC2626"
    warning = "#D97706"
    info = "#0284C7"

    # Text
    text_primary = "#111827"
    text_secondary = "#4B5563"
    text_muted = "#6B7280"
    text_inverted = "#FFFFFF"

    # Background
    background = "#F9FAFB"
    dark_background = "#111827"


class ForestTheme(DefaultTheme):
    primary = "#15803D"
    secondary = "#0F766E"
    accent = "#A16207"
    info = "#0369A1"


class GraphiteTheme(DefaultTheme):
    primary = "#334155"
    secondary = "#475569"
    accent = "#0F766E"
    dark = "#111827"
    dark_background = "#0F172A"


THEME_PALETTE_FIELDS = (
    "primary",
    "secondary",
    "accent",
    "dark",
    "dark_background",
    "positive",
    "negative",
    "warning",
    "info",
    "text_primary",
    "text_secondary",
    "text_muted",
    "text_inverted",
    "background",
)


def theme_palette(theme_class: type[Theme]) -> dict[str, str]:
    theme_instance = theme_class()
    return {field: getattr(theme_instance, field) for field in THEME_PALETTE_FIELDS}


def build_theme_class(
    name: str,
    base_theme: type[Theme],
    overrides: dict[str, str] | None = None,
) -> type[Theme]:
    palette = theme_palette(base_theme)
    palette.update(overrides or {})
    return type(name, (Theme,), palette)
