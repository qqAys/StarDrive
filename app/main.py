from app.bootstrap.env import setup_environment

setup_environment()

if __name__ in {"__main__", "__mp_main__"}:
    from pathlib import Path
    from nicegui import ui

    from app.bootstrap.app import create_app
    from app.bootstrap.logging import setup_logging
    from app.config import settings
    from app.core.logging import logger
    from app.core.paths import STATIC_DIR

    setup_logging()
    create_app()

    logger.info(f"App started at http://{settings.APP_HOST}:{settings.APP_PORT}")

    ui.run(
        storage_secret=settings.STORAGE_SECRET,
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        title=settings.APP_TITLE,
        favicon=Path(STATIC_DIR / "favicon.ico"),
        language=settings.APP_DEFAULT_LANGUAGE,
        dark=None,
        reload=False,
        show=False,
        prod_js=True,
        show_welcome_message=False,
        session_middleware_kwargs={
            "session_cookie": settings._PROJECT_NAME_CODE + "_session"
        },
        reconnect_timeout=settings.NICEGUI_RECONNECT_TIMEOUT,
        fastapi_docs=settings.DEBUG,
    )
