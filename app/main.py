from app.bootstrap.env import setup_environment

setup_environment()

if __name__ in {"__main__", "__mp_main__"}:
    from pathlib import Path
    from nicegui import ui

    from app.bootstrap.app import create_app
    from app.config import settings
    from app.core.logging import logger
    from app.core.paths import STATIC_DIR

    create_app()

    # Construct user-friendly startup message
    host = settings.APP_HOST if settings.APP_HOST != "0.0.0.0" else "localhost"
    url = f"http://{host}:{settings.APP_PORT}"

    if settings.DEBUG:
        logger.warning(
            "Debug mode is enabled. Do not use this setting in production—it may expose sensitive information."
        )

    logger.info(f"Application is running at {url}")

    ui.run(
        storage_secret=settings.APP_SECRET,
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        title=settings.APP_NAME,
        favicon=Path(STATIC_DIR / "favicon.ico"),
        language=settings.APP_DEFAULT_LANGUAGE,
        dark=None,
        reload=False,
        show=False,
        prod_js=True,
        show_welcome_message=False,
        session_middleware_kwargs={
            "session_cookie": f"{settings.APP_NAME.lower().replace(' ', '_')}_session"
        },
        reconnect_timeout=settings.NICEGUI_RECONNECT_TIMEOUT,
        fastapi_docs=settings.DEBUG,
    )
