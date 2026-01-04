import platform
from datetime import timedelta, timezone
from typing import Literal, Any, ClassVar

from pydantic import EmailStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import DB_DIR


class Config(BaseSettings):

    _PROJECT_NAME: str = "StarDrive"
    _PROJECT_NAME_CODE: str = _PROJECT_NAME.lower()
    _PROJECT_NAME_ENV: str = _PROJECT_NAME.upper()
    _PROJECT_AUTHOR: str = "Jinx"
    _PROJECT_AUTHOR_URL: str = "https://qqays.xyz"
    _PROJECT_AUTHOR_EMAIL: str = "me@qqays.xyz"
    _PROJECT_LICENSE: str = "MIT"

    _SYSTEM_NAME: str = platform.system()

    APP_DATA_DIR: str = "app_data"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix=f"{_PROJECT_NAME_ENV}_",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )
    SYSTEM_NAME: str = _SYSTEM_NAME

    # 请勿在生产环境打开DEBUG，将可能暴露文件结构
    DEBUG: bool = False

    APP_NAME: str = _PROJECT_NAME
    APP_VERSION: str = None
    APP_GITHUB_URL: ClassVar[str] = "https://github.com/qqAys/StarDrive"

    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8080

    APP_SECRET: str = None

    APP_DEFAULT_LANGUAGE: str = "en-US"

    APP_INIT_USER: EmailStr = "admin@stardrive.abc"

    LOCAL_DB_DSN: str = f"sqlite+aiosqlite:///{(DB_DIR / "local.db").as_posix()}"
    LOCAL_DB_ECHO: bool = DEBUG

    NICEGUI_RECONNECT_TIMEOUT: int = 5
    NICEGUI_TIMER_INTERVAL: float = 2

    DEFAULT_DOWNLOAD_LINK_TTL: ClassVar[timedelta] = timedelta(seconds=30)

    SYSTEM_DEFAULT_TIMEZONE: ClassVar[timezone] = timezone.utc

    NOTIFY_DURATION: ClassVar[int] = 3000
    MULTIPARTPARSER_SPOOL_MAX_SIZE: ClassVar[int] = 1024 * 1024 * 5
    STREAM_CHUNK_SIZE: ClassVar[int] = 1024 * 10

    USE_MISANS: ClassVar[bool] = True

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    def __init__(self, **values: Any):
        super().__init__(**values)


settings = Config()
