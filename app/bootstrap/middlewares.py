from nicegui import app

from app.middlewares.auth_logging_middleware import AuthLoggingMiddleware


def setup_middlewares():
    app.add_middleware(AuthLoggingMiddleware)
