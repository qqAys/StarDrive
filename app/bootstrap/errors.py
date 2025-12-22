import traceback
from uuid import uuid4

from fastapi import HTTPException
from nicegui import app

from app.core.exceptions import BusinessException
from app.core.logging import logger
from app.middlewares.exception_middleware import (
    business_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
)
from app.ui.pages.error_page import render_50x


def setup_error_handlers():
    app.add_exception_handler(BusinessException, business_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

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
