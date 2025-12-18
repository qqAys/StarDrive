import json
import logging
from logging import getLogger, StreamHandler
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import settings
from core.paths import data_dir

LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5

APP_LOG_PATH = data_dir / "log"
APP_LOG_PATH.mkdir(parents=True, exist_ok=True)


class CustomFormatter(logging.Formatter):
    """
    自定义 Formatter，用于处理日志中的占位符。
    """

    def format(self, record: logging.LogRecord):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "file": record.pathname,
            "line": record.lineno,
        }

        if record.exc_info:
            log_record["stack_trace"] = self.formatException(record.exc_info)
        elif record.exc_text:
            log_record["stack_trace"] = record.exc_text

        return json.dumps(log_record, ensure_ascii=False)


def create_handler(filename: Path, formatter: logging.Formatter) -> RotatingFileHandler:
    file_handler = RotatingFileHandler(
        filename,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    return file_handler


no_need_output_log = ["python_multipart.multipart", "aiosqlite"]

# 创建 Handler
shared_formatter = CustomFormatter()
stream_handler = StreamHandler()
stream_handler.setFormatter(shared_formatter)
app_file_handler = create_handler(APP_LOG_PATH / "app.log", shared_formatter)

# 获取根 logger
root_logger = logging.getLogger()

# 移除所有已有的 Handler
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# 设置级别
root_logger.setLevel(settings.LOG_LEVEL)
for logger in no_need_output_log:
    logging.getLogger(logger).setLevel(logging.ERROR)

# 添加 Handler
root_logger.addHandler(stream_handler)
root_logger.addHandler(app_file_handler)

# APP LOGGER
logger = getLogger(settings._PROJECT_NAME_CODE)
