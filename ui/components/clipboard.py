from nicegui import ui

from ui.components.notify import notify
from utils import _


def copy_to_clipboard(link: str, message: str) -> bool:
    try:
        ui.clipboard.write(link)
        notify.success(message)
    except Exception as e:
        notify.error(_("Failed to copy to clipboard: {}").format(e))
        return False
    return True
