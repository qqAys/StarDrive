from fastapi.requests import Request
from nicegui import ui, app

from app.api import download
from app.core.logging import logger
from app.ui.pages import console
from app.ui.pages import login, browser, profile, share
from app.ui.pages.error_page import render_404


def setup_routes():
    app.include_router(login.router)
    app.include_router(browser.router)
    app.include_router(share.router)
    app.include_router(profile.router)
    app.include_router(console.router)
    app.include_router(download.router)

    @ui.page("/{_:path}")
    def not_found_page(request: Request):
        request_uuid = request.state.request_uuid
        logger.info(
            {
                "request_uuid": str(request_uuid),
                "path": request.url.path,
                "app_storage": app.storage.user,
            }
        )
        render_404(request.state.request_uuid)
        return
