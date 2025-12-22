from nicegui import app
from starlette.responses import RedirectResponse

from app.api import download
from app.ui.pages import console
from app.ui.pages import login, browser, profile, share


def setup_routes():
    app.include_router(login.router)
    app.include_router(browser.router)
    app.include_router(share.router)
    app.include_router(profile.router)
    app.include_router(console.router)
    app.include_router(download.router)

    @app.exception_handler(404)
    def not_found_page(*args, **kwargs):
        return RedirectResponse("/404")
