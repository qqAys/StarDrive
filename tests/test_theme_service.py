import asyncio
from types import SimpleNamespace

import pytest

from app.services import theme_service as module
from app.services.theme_service import (
    CUSTOM_THEME_ID,
    DEFAULT_THEME_ID,
    THEME_SETTING_KEY,
    ThemeConfig,
    ThemeConfigService,
)
from app.ui.theme import theme_colors
from app.ui.theme.default import DefaultTheme, GraphiteTheme


class FakeDBContext:
    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def fake_db_context():
    return FakeDBContext()


class FakeAppSettingCRUD:
    values: dict[str, str] = {}

    @classmethod
    async def get_value(cls, session, key, default=None):
        return cls.values.get(key, default)

    @classmethod
    async def set_value(cls, session, key, value):
        cls.values[key] = value
        return SimpleNamespace(key=key, value=value)


@pytest.fixture(autouse=True)
def fake_theme_dependencies(mocker):
    FakeAppSettingCRUD.values = {}
    applied = []
    mocker.patch.object(module, "get_db_context", fake_db_context)
    mocker.patch.object(module, "AppSettingCRUD", FakeAppSettingCRUD)
    mocker.patch.object(
        module, "set_theme", lambda theme_class: applied.append(theme_class)
    )
    return applied


def test_theme_config_save_persists_and_applies_custom_theme(fake_theme_dependencies):
    async def run_test():
        service = ThemeConfigService()
        saved = await service.save(
            ThemeConfig(
                preset_id=CUSTOM_THEME_ID,
                custom_palette={
                    "primary": "#123abc",
                    "secondary": "#456def",
                    "accent": "#789012",
                },
            )
        )

        assert saved.preset_id == CUSTOM_THEME_ID
        assert saved.custom_palette["primary"] == "#123ABC"
        assert THEME_SETTING_KEY in FakeAppSettingCRUD.values
        assert fake_theme_dependencies[-1]().primary == "#123ABC"

    asyncio.run(run_test())


def test_theme_config_rejects_invalid_custom_color():
    service = ThemeConfigService()

    with pytest.raises(ValueError, match="primary must be a #RRGGBB color"):
        service.normalize(
            ThemeConfig(
                preset_id=CUSTOM_THEME_ID,
                custom_palette={"primary": "blue"},
            )
        )


def test_theme_config_ignores_custom_values_for_builtin_preset():
    service = ThemeConfigService()

    normalized = service.normalize(
        ThemeConfig(
            preset_id="forest",
            custom_palette={"primary": "not-a-color"},
        )
    )

    assert normalized.preset_id == "forest"
    assert normalized.custom_palette == {}


def test_theme_config_load_falls_back_from_invalid_json():
    async def run_test():
        FakeAppSettingCRUD.values[THEME_SETTING_KEY] = "{not-json"
        service = ThemeConfigService()

        await service.load()

        assert service.current_config.preset_id == DEFAULT_THEME_ID

    asyncio.run(run_test())


def test_theme_colors_maps_theme_to_nicegui_brand_keys():
    colors = theme_colors(GraphiteTheme)

    assert colors["primary"] == "#334155"
    assert colors["dark_page"] == "#0F172A"
    assert colors["negative"] == "#DC2626"


def test_default_theme_uses_stardrive_brand_primary():
    assert DefaultTheme().primary == "#7E75F2"
