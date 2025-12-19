from nicegui import ui

from app.core.i18n import _
from app.ui.components.notify import notify


def copy_to_clipboard(link: str, message: str) -> bool:
    try:
        ui.clipboard.write(link)
        notify.success(message)
    except Exception as e:
        notify.error(_("Failed to copy to clipboard: {}").format(e))
        return False
    return True
