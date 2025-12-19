import traceback
from uuid import uuid4

from nicegui import app

from app.core.logging import logger
from app.ui.pages.error_page import render_50x


def setup_error_handlers():

    @app.on_page_exception
    def page_exception_handler(exception: Exception):
        request_uuid = uuid4()
        logger.error(
            {
                "request_uuid": str(request_uuid),
                "exception": str(exception),
                "traceback": traceback.format_exc(chain=False),
                "app_storage": app.storage.user,
            }
        )
        render_50x(str(request_uuid), str(exception))
