from typing import Literal, Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):

    _PROJECT_NAME: str = "StarDrive"
    _PROJECT_NAME_CODE: str = _PROJECT_NAME.lower()
    _PROJECT_NAME_ENV: str = _PROJECT_NAME.upper()
    _PROJECT_AUTHOR: str = "Jinx"
    _PROJECT_AUTHOR_URL: str = "https://qqays.xyz"
    _PROJECT_AUTHOR_EMAIL: str = "me@qqays.xyz"
    _PROJECT_LICENSE: str = "MIT"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix=f"{_PROJECT_NAME_ENV}_",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # 请勿在生产环境打开DEBUG，将可能暴露文件结构
    DEBUG: bool = False

    APP_NAME: str = _PROJECT_NAME
    APP_VERSION: str = None
    APP_GITHUB_URL: str = "https://github.com/qqAys/StarDrive"

    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8080

    APP_TITLE: str = _PROJECT_NAME
    APP_DEFAULT_LANGUAGE: str = "zh-CN"

    STORAGE_SECRET: str = None
    NICEGUI_RECONNECT_TIMEOUT: int = 5
    NICEGUI_TIMER_INTERVAL: float = 2

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    def __init__(self, **values: Any):
        super().__init__(**values)

        from logging import getLogger, StreamHandler

        init_logger = getLogger(self._PROJECT_NAME_CODE + "_init")
        init_logger.setLevel("DEBUG")
        init_logger.addHandler(StreamHandler())

        init_logger.info(f"{self._PROJECT_NAME} {self.APP_VERSION}")

        if self.DEBUG:
            init_logger.debug("DEBUG mode is enabled, LOG_LEVEL is set to DEBUG.")
            self.LOG_LEVEL = "DEBUG"

        self.LOG_LEVEL = self.LOG_LEVEL.upper()


settings = Config()
