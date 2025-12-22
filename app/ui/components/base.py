from contextlib import asynccontextmanager

from nicegui import ui

from app.config import settings
from app.ui.components import max_w
from app.ui.components.footer import Footer
from app.ui.components.header import Header


class BaseLayout:

    def __init__(self):
        ui.colors(primary=settings.APP_PRIMARY_COLOR)

        # favicon
        ui.add_head_html(
            f"""
    <!-- favicon -->
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
            pass
