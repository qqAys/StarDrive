from contextlib import asynccontextmanager

from nicegui import ui

from app.config import settings
from app.ui.components import max_w
from app.ui.components.footer import Footer
from app.ui.components.header import Header


class BaseLayout:
    """
    Base layout class for the application UI.

    This class sets up global UI configurations such as theme colors and favicon,
    and provides a reusable rendering context that optionally includes a header and footer.
    """

    def __init__(self):
        # Apply the primary color defined in app settings
        ui.colors(primary=settings.APP_PRIMARY_COLOR)

        # Add favicon and related meta tags to the HTML head
        ui.add_head_html(
            f"""
    <!-- Favicon and PWA icons -->
    <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
    <meta name="apple-mobile-web-app-title" content="{settings.APP_NAME}" />
    <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png" />
    <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png" />
    <link rel="manifest" href="/site.webmanifest" />"""
        )

        self.header_component = Header()
        self.footer_component = Footer()

    @asynccontextmanager
    async def render(
        self, header: bool = False, footer: bool = False, args: dict = None
    ):
        """
        Asynchronous context manager to render the base layout with optional header and footer.

        Args:
            header (bool): Whether to render the header component.
            footer (bool): Whether to render the footer component.
            args (dict): Optional arguments passed to the header and footer render methods.

        Yields:
            tuple: A tuple containing the rendered header and footer components (or None if not rendered).
        """
        if args is None:
            args = {}

        header_el, footer_el = None, None

        if header:
            await self.header_component.render(**args)
            header_el = self.header_component

        if footer:
            self.footer_component.render(**args)
            footer_el = self.footer_component

        try:
            with ui.element().classes("w-full" + max_w):
                yield header_el, footer_el
        finally:
            # No cleanup required at this level; components manage their own lifecycle
            pass
