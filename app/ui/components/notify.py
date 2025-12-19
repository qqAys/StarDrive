from nicegui import ui

from app.config import settings


class Notify:
    """
    封装 Notify 组件
    """

    def __init__(self):
        self.notify = ui.notify
        self.position = "top"
        self.duration = settings.NOTIFY_DURATION

    def success(self, message: str):
        self.notify(
            message, type="positive", position=self.position, duration=self.duration
        )

    def error(self, message: str):
        self.notify(
            message, type="negative", position=self.position, duration=self.duration
        )

    def warning(self, message: str):
        self.notify(
            message, type="warning", position=self.position, duration=self.duration
        )

    def info(self, message: str):
        self.notify(
            message, type="info", position=self.position, duration=self.duration
        )


notify = Notify()
