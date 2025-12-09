from typing import overload

from nicegui import ui


class Link(ui.link):
    @overload
    def __init__(
        self, href: str, text: str, bold: bool = False, _blank: bool = False
    ): ...

    @overload
    def __init__(self, href: str, icon: str, _blank: bool = False): ...

    def __init__(
        self,
        href: str,
        text: str = None,
        icon: str = None,
        bold: bool = False,
        _blank: bool = False,
    ):
        super().__init__(text, href, _blank)

        self.classes("text-grey-5 items-center no-wrap no-underline")

        if bold:
            self.classes("font-bold")

        if _blank and text:
            with self:
                ui.icon("open_in_new").classes("ml-1 mb-1")
            return

        if icon:
            with self:
                ui.icon(icon)
            return


link = Link
