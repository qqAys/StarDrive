import json
import re
from dataclasses import dataclass, field

from app.crud.system_crud import AppSettingCRUD
from app.services.local_db_service import get_db_context
from app.ui.theme import set_theme
from app.ui.theme.base import Theme
from app.ui.theme.default import (
    DefaultTheme,
    ForestTheme,
    GraphiteTheme,
    build_theme_class,
    theme_palette,
)

THEME_SETTING_KEY = "ui.theme"
DEFAULT_THEME_ID = "stardrive"
CUSTOM_THEME_ID = "custom"
THEME_CUSTOM_FIELDS = ("primary", "secondary", "accent")
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True, slots=True)
class ThemePreset:
    id: str
    label: str
    theme_class: type[Theme]


@dataclass(slots=True)
class ThemeConfig:
    preset_id: str = DEFAULT_THEME_ID
    custom_palette: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "preset_id": self.preset_id,
                "custom_palette": self.custom_palette,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )


THEME_PRESETS: dict[str, ThemePreset] = {
    "stardrive": ThemePreset("stardrive", "StarDrive", DefaultTheme),
    "forest": ThemePreset("forest", "Forest", ForestTheme),
    "graphite": ThemePreset("graphite", "Graphite", GraphiteTheme),
}


class ThemeConfigService:
    def __init__(self):
        self.current_config = ThemeConfig()

    async def load(self) -> None:
        async with get_db_context() as session:
            raw = await AppSettingCRUD.get_value(session, THEME_SETTING_KEY)
        self.apply(self.decode(raw))

    async def save(self, config: ThemeConfig) -> ThemeConfig:
        normalized = self.normalize(config)
        async with get_db_context() as session:
            await AppSettingCRUD.set_value(
                session,
                THEME_SETTING_KEY,
                normalized.to_json(),
            )
        self.apply(normalized)
        return normalized

    def apply(self, config: ThemeConfig) -> None:
        normalized = self.normalize(config)
        set_theme(self.theme_class(normalized))
        self.current_config = normalized

    def decode(self, raw: str | None) -> ThemeConfig:
        if not raw:
            return ThemeConfig()
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return ThemeConfig()
        try:
            return self.normalize(
                ThemeConfig(
                    preset_id=str(data.get("preset_id") or DEFAULT_THEME_ID),
                    custom_palette=dict(data.get("custom_palette") or {}),
                )
            )
        except ValueError:
            return ThemeConfig()

    def normalize(self, config: ThemeConfig) -> ThemeConfig:
        preset_id = config.preset_id
        if preset_id not in THEME_PRESETS and preset_id != CUSTOM_THEME_ID:
            preset_id = DEFAULT_THEME_ID

        if preset_id != CUSTOM_THEME_ID:
            return ThemeConfig(preset_id=preset_id, custom_palette={})

        custom_palette = {
            field: value.strip().upper()
            for field, value in (config.custom_palette or {}).items()
            if field in THEME_CUSTOM_FIELDS and str(value).strip()
        }
        for field, value in custom_palette.items():
            if not HEX_COLOR_RE.fullmatch(value):
                raise ValueError(f"{field} must be a #RRGGBB color")

        return ThemeConfig(preset_id=preset_id, custom_palette=custom_palette)

    def theme_class(self, config: ThemeConfig) -> type[Theme]:
        if config.preset_id == CUSTOM_THEME_ID:
            return build_theme_class(
                "CustomTheme",
                DefaultTheme,
                config.custom_palette,
            )
        return THEME_PRESETS[config.preset_id].theme_class

    def palette_for(self, config: ThemeConfig | None = None) -> dict[str, str]:
        normalized = self.normalize(config or self.current_config)
        return theme_palette(self.theme_class(normalized))


theme_config = ThemeConfigService()
