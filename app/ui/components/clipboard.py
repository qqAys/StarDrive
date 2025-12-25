from nicegui import ui

from app.core.i18n import _
from app.ui.components.notify import notify


def copy_to_clipboard(link: str, message: str) -> bool:
    """
    Copy the given link to the system clipboard and show a success notification.

    If the operation fails (e.g., due to browser restrictions), an error notification is shown.

    Args:
        link (str): The text content to copy to the clipboard.
        message (str): The success message to display if copying succeeds.

    Returns:
        bool: True if the copy operation succeeded, False otherwise.
    """
    try:
        ui.clipboard.write(link)
        notify.success(message)
        return True
    except Exception:
        notify.error(_("Failed to copy to clipboard"))
        return False
