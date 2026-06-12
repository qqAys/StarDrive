from pathlib import Path

from app.ui.components.dialog import (
    CODE_PREVIEW_CSS,
    MAX_HIGHLIGHT_LINE_CHARS,
    MAX_JSON_HIGHLIGHT_CHARS,
    MediaType,
    build_office_preview_cache_path,
    detect_highlight_language,
    detect_preview_media_type,
    should_highlight_text,
)


def test_detect_preview_media_type_for_common_formats():
    assert detect_preview_media_type(".jpg") == MediaType.IMAGE
    assert detect_preview_media_type(".MP4") == MediaType.VIDEO
    assert detect_preview_media_type(".m4a") == MediaType.AUDIO
    assert detect_preview_media_type(".pdf") == MediaType.PDF
    assert detect_preview_media_type(".md") == MediaType.MARKDOWN
    assert detect_preview_media_type(".csv") == MediaType.CSV
    assert detect_preview_media_type(".py") == MediaType.TEXT
    assert detect_preview_media_type(".tsx") == MediaType.TEXT
    assert detect_preview_media_type(".jsonc") == MediaType.TEXT
    assert detect_preview_media_type(".properties") == MediaType.TEXT
    assert detect_preview_media_type(".env") == MediaType.TEXT
    assert detect_preview_media_type(".gitignore") == MediaType.TEXT
    assert detect_preview_media_type("Dockerfile") == MediaType.TEXT
    assert detect_preview_media_type(".ppt") == MediaType.OFFICE
    assert detect_preview_media_type(".abc") == MediaType.UNSUPPORTED


def test_detect_highlight_language_for_code_and_config_files():
    assert detect_highlight_language(Path("main.py")) == "python"
    assert detect_highlight_language(Path("component.tsx")) == "typescript"
    assert detect_highlight_language(Path("settings.yaml")) == "yaml"
    assert detect_highlight_language(Path("pyproject.toml")) == "ini"
    assert detect_highlight_language(Path(".env")) == "properties"
    assert detect_highlight_language(Path("Dockerfile")) == "dockerfile"


def test_should_skip_expensive_text_highlighting():
    assert should_highlight_text(Path("main.py"), "print('ok')\n", truncated=False)
    assert should_highlight_text(Path("settings.json"), '{"ok": true}\n', truncated=False)

    large_json = '{"items": [' + ("1," * MAX_JSON_HIGHLIGHT_CHARS) + "0]}"
    assert not should_highlight_text(Path("settings.json"), large_json, truncated=False)
    assert not should_highlight_text(
        Path("settings.json"),
        "a" * (MAX_HIGHLIGHT_LINE_CHARS + 1),
        truncated=False,
    )
    assert not should_highlight_text(Path("main.py"), "print('ok')\n", truncated=True)
    assert not should_highlight_text(Path("unknown.txt"), "plain text\n", truncated=False)


def test_code_preview_style_supports_wrap_and_dark_mode():
    assert ".stardrive-code-preview-wrap code" in CODE_PREVIEW_CSS
    assert "white-space: pre-wrap" in CODE_PREVIEW_CSS
    assert ".body--dark .stardrive-code-preview pre" in CODE_PREVIEW_CSS


def test_office_preview_cache_key_changes_when_source_changes(tmp_path):
    source = tmp_path / "deck.ppt"
    source.write_bytes(b"first")
    first_cache_path = build_office_preview_cache_path(source)

    source.write_bytes(b"second version")
    second_cache_path = build_office_preview_cache_path(source)

    assert first_cache_path != second_cache_path
    assert first_cache_path.suffix == ".pdf"
    assert second_cache_path.suffix == ".pdf"
