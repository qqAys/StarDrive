from contextlib import contextmanager
from nicegui import ui


@contextmanager
def disable(button: ui.button):
    button.disable()
    try:
        yield
    finally:
        button.enable()
