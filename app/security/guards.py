import inspect
from functools import wraps
from typing import Optional, Callable

from nicegui import ui, app

from app import globals
from app.config import settings
from app.core.i18n import _
from app.ui.components.notify import notify


def navigate_to(custom_url: str = None) -> None:
    """
    Redirect the user to a specified URL after a short delay.

    Used to avoid navigation issues during page rendering by deferring the redirect
    via a one-time timer.

    Args:
        custom_url: The target URL. Defaults to "/login" if not provided.
    """
    ui.timer(
        settings.NICEGUI_TIMER_INTERVAL,
        lambda: ui.navigate.to(custom_url or "/login"),
        once=True,
    )


def require_user(
    func: Optional[Callable] = None,
    *,
    superuser: bool = False,
    active: bool = True,
):
    """
    Decorator to enforce user authentication and authorization on NiceGUI page functions.

    This decorator ensures that:
    - The user is signed in.
    - The user account is active (if `active=True`).
    - The user has superuser privileges (if `superuser=True`).

    If any condition fails, an error notification is shown and the user is redirected.

    Usage:
        @require_user
        def my_page(): ...

        @require_user(superuser=True)
        async def admin_page(): ...
    """

    def decorator(page_func: Callable):
        is_async = inspect.iscoroutinefunction(page_func)

        @wraps(page_func)
        async def wrapper(*args, **kwargs):
            # Authentication & Authorization
            user_storage = app.storage.user
            if not user_storage:
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

            # Execute Original Function
            if is_async:
                return await page_func(*args, **kwargs)
            else:
                return page_func(*args, **kwargs)

        return wrapper

    # Support both @require_user and @require_user(...)
    if callable(func):
        return decorator(func)

    return decorator
