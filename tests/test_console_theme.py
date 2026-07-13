from app.ui.pages.console import _readable_text_color


def test_theme_color_picker_button_uses_readable_text_color():
    assert _readable_text_color("#FFFFFF") == "black"
    assert _readable_text_color("#7E75F2") == "white"
    assert _readable_text_color("#111827") == "white"
