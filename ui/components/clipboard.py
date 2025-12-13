from nicegui import ui

from ui.components.notify import notify
from utils import _


def copy_text_clipboard(text: str) -> bool:
    try:
        ui.clipboard.write(text)
        notify.success(_("Copied to clipboard"))
    except Exception as e:
        notify.error(_("Failed to copy to clipboard: {}").format(e))
        return False
    return True