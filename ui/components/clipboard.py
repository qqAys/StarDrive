from nicegui import ui

from ui.components.notify import notify
from utils import _


def copy_share_link_to_clipboard(link: str) -> bool:
    try:
        ui.clipboard.write(link)
        notify.success(_("Share link copied to clipboard."))
    except Exception as e:
        notify.error(_("Failed to copy to clipboard: {}").format(e))
        return False
    return True
