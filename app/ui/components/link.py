from typing import overload

from nicegui import ui


class Link(ui.link):
    """
    A customized link component that supports either text or an icon, with optional bold styling
    and an automatic "open in new tab" indicator when needed.

    This class enhances the standard NiceGUI link by:
    - Applying consistent styling (gray color, no underline, etc.)
    - Optionally displaying an 'open_in_new' icon when opening in a new tab
    - Supporting exclusive use of either text or an icon (not both simultaneously)
    """

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
        # Initialize the underlying ui.link with text if provided
        super().__init__(text=text or "", target=href, new_tab=_blank)

        # Apply base styling
        self.classes("text-grey-5 items-center no-wrap no-underline")

        if bold and text:
            self.classes("font-bold")

        # Add 'open_in_new' icon only when opening in a new tab and text is used
        if _blank and text:
            with self:
                ui.icon("open_in_new").classes("ml-1 mb-1")
        # If an icon is specified (and no text), render the icon inside the link
        elif icon:
            with self:
                ui.icon(icon)


link = Link
