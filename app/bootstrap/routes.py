from nicegui import app
from starlette.responses import RedirectResponse

from app.api import auth, download, preview
from app.ui.pages import account
from app.ui.pages import console
from app.ui.pages import login, browser, profile, share


def setup_routes():
    app.include_router(login.router)
    app.include_router(account.register_router)
    app.include_router(account.forgot_router)
    app.include_router(account.reset_router)
    app.include_router(browser.router)
    app.include_router(share.router)
    app.include_router(profile.router)
    app.include_router(console.router)
    app.include_router(download.router)
    app.include_router(preview.router)

    @app.exception_handler(404)
    def not_found_page(*args, **kwargs):
        return RedirectResponse("/404")
