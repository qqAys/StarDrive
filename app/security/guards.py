from functools import wraps
from typing import Optional, Callable

from nicegui import ui, app

from app import globals
from app.config import settings
from app.core.i18n import _
from app.ui.components.notify import notify


def navigate_to(custom_url: str = None):
    ui.timer(
        settings.NICEGUI_TIMER_INTERVAL,
        lambda: ui.navigate.to(custom_url or "/login"),
        once=True,
    )


def require_user(
    func: Optional[Callable] = None, *, superuser: bool = False, active: bool = True
):

    def decorator(page_func):
        @wraps(page_func)
        async def wrapper(*args, **kwargs):
            if not app.storage.user:
                notify.error(_("You need to sign in to access this page."))
                navigate_to()
                return None

            um = globals.get_user_manager()
            user = await um.current_user()

            if not user:
                notify.error(_("You need to sign in to access this page."))
                navigate_to()
                return None

            if active and not user.is_active:
                notify.error(_("Your account has been disabled."))
                navigate_to()
                return None

            if superuser and not user.is_superuser:
                notify.error(_("You don’t have access to this page."))
                navigate_to("/home/")
                return None

            return await page_func(*args, **kwargs)

        return wrapper

    if callable(func):
        return decorator(func)

    return decorator
