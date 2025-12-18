from nicegui import app

from middlewares.auth_middleware import AuthMiddleware
from middlewares.logging_middleware import RequestLoggingMiddleware


def setup_middlewares():
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(AuthMiddleware)
