from asyncio import iscoroutinefunction
from contextlib import asynccontextmanager
from functools import wraps

from ui.components.footer import Footer
from ui.components.header import Header


class BaseLayout:

    def __init__(self):
        self.header_component = Header()
        self.footer_component = Footer()

    @asynccontextmanager
    async def render(self, header: bool = False, footer: bool = False, args: dict = None):

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
            yield header_el, footer_el
        finally:
            pass
