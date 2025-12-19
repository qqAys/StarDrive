# app/bootstrap/app.py
from app.bootstrap.errors import setup_error_handlers
from app.bootstrap.lifecycle import setup_lifecycle
from app.bootstrap.middlewares import setup_middlewares
from app.bootstrap.routes import setup_routes
from app.bootstrap.static import setup_static


def create_app() -> None:
    setup_lifecycle()
    setup_middlewares()
    setup_static()
    setup_routes()
    setup_error_handlers()
