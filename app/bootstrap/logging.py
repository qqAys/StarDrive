from logging import getLogger, StreamHandler

from app.config import settings


def setup_logging() -> None:
    init_logger = getLogger(settings._PROJECT_NAME_CODE + "_init")
    init_logger.setLevel("DEBUG")
    init_logger.addHandler(StreamHandler())

    init_logger.info(
        f"{settings._PROJECT_NAME} v{settings.APP_VERSION} {settings.SYSTEM_NAME}"
    )

    if settings.DEBUG:
        init_logger.debug("DEBUG mode is enabled")
