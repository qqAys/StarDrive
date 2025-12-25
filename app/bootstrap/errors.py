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
    """
    Register global exception handlers for both FastAPI-style exceptions
    and unhandled errors occurring during NiceGUI page rendering.

    - BusinessException: Handled via custom business logic (e.g., user-facing alerts).
    - HTTPException: Standard HTTP error responses (e.g., 404, 403).
    - Exception: Catches all other unhandled exceptions as a safety net.

    Additionally, configures `@app.on_page_exception` to:
      - Generate a unique request ID for traceability.
      - Log full exception details including traceback and current user storage.
      - Render a user-friendly 50x error page with the request ID for support/debugging.
    """
    # Register middleware-style exception handlers for API-like requests
    app.add_exception_handler(BusinessException, business_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Handle exceptions that occur during UI page execution
    @app.on_page_exception
    def page_exception_handler(exception: Exception):
        request_uuid = uuid4()
        logger.error(
            {
                "request_uuid": str(request_uuid),
                "exception": str(exception),
                "traceback": traceback.format_exc(chain=False),
                "app_storage": dict(
                    app.storage.user
                ),  # Serialize to avoid runtime issues
            }
        )
        render_50x(str(request_uuid), str(exception))
