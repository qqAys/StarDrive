import json
import logging
import time
from logging import StreamHandler
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import settings
from app.core.paths import LOG_DIR, APP_ROOT
from app.utils.time import utc_now

# 配置
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5
LOG_DIR.mkdir(parents=True, exist_ok=True)
TIME_FORMAT = "%Y-%m-%d %H:%M:%S %Z"
SUPPRESS_LOGGERS = ["python_multipart.multipart", "aiosqlite"]


class JsonFormatter(logging.Formatter):
    """JSON 文件日志格式化"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_dir = APP_ROOT

    def format(self, record: logging.LogRecord) -> str:
        file_path = Path(record.pathname).resolve()

        try:
            rel_path = str(file_path.relative_to(self.base_dir))
        except (ValueError, RuntimeError):
            rel_path = record.filename

        log_record = {
            "time": utc_now().strftime(TIME_FORMAT),
            "level": record.levelname,
            "logger": record.name,
            "file": rel_path,
            "line": record.lineno,
        }

        if isinstance(record.msg, dict):
            log_record.update(record.msg)
        else:
            log_record["message"] = record.getMessage()

        if record.exc_info or record.exc_text:
            log_record["stack_trace"] = (
                self.formatException(record.exc_info)
                if record.exc_info
                else record.exc_text
            )

        return json.dumps(log_record, ensure_ascii=False)


def create_file_handler(
    filename: Path, formatter: logging.Formatter
) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        filename,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    return handler


def setup_logging() -> logging.Logger:
    """
    全局日志初始化
    """
    root_logger = logging.getLogger(settings._PROJECT_NAME_CODE)

    # 文件日志
    json_formatter = JsonFormatter()
    file_handler = create_file_handler(LOG_DIR / "app.log", json_formatter)

    # 控制台日志
    console_formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt=TIME_FORMAT
    )
    console_formatter.converter = time.gmtime
    console_handler = StreamHandler()
    console_handler.setFormatter(console_formatter)

    # 日志级别
    root_logger.setLevel(logging.DEBUG if settings.DEBUG else settings.LOG_LEVEL)

    # 屏蔽不必要模块
    for name in SUPPRESS_LOGGERS:
        logging.getLogger(name).setLevel(logging.ERROR)

    # 添加 Handler
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    root_logger._initialized = True
    return root_logger


# 初始化全局 logger
logger = setup_logging()
