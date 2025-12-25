from nicegui import ui

from app.config import settings


class Notify:
    """
    A wrapper around NiceGUI's notification system to provide consistent, typed notifications.

    This class simplifies showing success, error, warning, and info messages with
    predefined styling, position, and duration based on application settings.
    """

    def __init__(self):
        self.notify = ui.notify
        self.position = "top"
        self.duration = settings.NOTIFY_DURATION

    def success(self, message: str):
        """Show a success notification."""
        self.notify(
            message, type="positive", position=self.position, duration=self.duration
        )

    def error(self, message: str):
        """Show an error notification."""
        self.notify(
            message, type="negative", position=self.position, duration=self.duration
        )

    def warning(self, message: str):
        """Show a warning notification."""
        self.notify(
            message, type="warning", position=self.position, duration=self.duration
        )

    def info(self, message: str):
        """Show an informational notification."""
        self.notify(
            message, type="info", position=self.position, duration=self.duration
        )


notify = Notify()
