from contextlib import contextmanager

from nicegui import ui


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
