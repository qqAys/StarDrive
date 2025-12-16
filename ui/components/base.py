from asyncio import iscoroutinefunction
from contextlib import contextmanager
from functools import wraps

from ui.components.footer import Footer
from ui.components.header import Header


def base_layout(**layout_kwargs):
    """
    用于将页面内容包裹在 BaseLayout 的渲染上下文中的装饰器，
    同时支持同步和异步函数。
    """

    def decorator(func):
        # 检查异步调用 (async def)
        if iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                with BaseLayout().render(**layout_kwargs):
                    return await func(*args, **kwargs)

            return async_wrapper
        else:

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                with BaseLayout().render(**layout_kwargs):
                    return func(*args, **kwargs)

            return sync_wrapper

    return decorator


class BaseLayout:

    def __init__(self):
        self.header_component = Header()
        self.footer_component = Footer()

    @contextmanager
    def render(self, header: bool = False, footer: bool = False, args: dict = None):

        if args is None:
            args = {}

        header_el, footer_el = None, None

        if header:
            self.header_component.render(**args)
            header_el = self.header_component

        if footer:
            self.footer_component.render(**args)
            footer_el = self.footer_component

        yield header_el, footer_el
