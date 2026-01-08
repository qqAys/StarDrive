from contextlib import contextmanager

from nicegui import ui

from app.ui.components.label import label, dynamic_classes


@contextmanager
def disable(button: ui.button):
    """
    Context manager to temporarily disable a button during an operation.

    This function disables the provided button for the duration of the context,
    ensuring that it is re-enabled afterward, regardless of whether an exception occurs.

    Args:
        button (ui.button): The button to be disabled/enabled.

    Yields:
        None: The function yields control back to the context where it's used.
    """
    button.disable()
    try:
        yield
    finally:
        button.enable()


def custom_button(
    text: str | None = None,
    icon: str | None = None,
    on_click=None,
    tooltip: str | None = None,
    disabled: bool = False,
):
    props = "no-caps flat dense"
    if disabled:
        props += " disable"

    with ui.button(on_click=on_click).props(props) as btn:
        if icon:
            ui.icon(icon).classes(dynamic_classes)
        if text:
            label(text)
        if tooltip:
            ui.tooltip(tooltip)

    return btn
