import json
import logging
import time
from logging import StreamHandler
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import settings
from app.core.paths import LOG_DIR, APP_ROOT
from app.utils.time import utc_now

# Logging configuration constants
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per log file
LOG_BACKUP_COUNT = 5  # Keep up to 5 rotated files
LOG_DIR.mkdir(parents=True, exist_ok=True)
TIME_FORMAT = "%Y-%m-%d %H:%M:%S %Z"

# List of logger names to suppress (reduce noise in logs)
SUPPRESS_LOGGERS = ["python_multipart.multipart", "aiosqlite"]


class JsonFormatter(logging.Formatter):
    """
    Custom formatter that outputs log records as structured JSON.

    Includes relative file path (relative to project root), line number,
    timestamp in UTC, logger name, log level, and optional exception stack trace.
    If the log message is already a dictionary, it's merged into the record;
    otherwise, the message is stored under the 'message' key.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_dir = APP_ROOT.resolve()

    def format(self, record: logging.LogRecord) -> str:
        # Resolve absolute path and compute relative path to project root
        file_path = Path(record.pathname).resolve()
        try:
            rel_path = str(file_path.relative_to(self.base_dir))
        except (ValueError, RuntimeError):
            rel_path = record.filename  # fallback if not under project root

        # Build structured log entry
        log_record = {
            "time": utc_now().strftime(TIME_FORMAT),
            "level": record.levelname,
            "logger": record.name,
            "file": rel_path,
            "line": record.lineno,
        }

        # Handle message content
        if isinstance(record.msg, dict):
            log_record.update(record.msg)
        else:
            log_record["message"] = record.getMessage()

        # Include exception info if present
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
    """
    Create a rotating file handler with specified formatter.
    Ensures UTF-8 encoding and proper rotation settings.
    """
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
    Initialize and configure the application's root logger.

    - Sets log level based on DEBUG mode or explicit LOG_LEVEL setting.
    - Adds both JSON-formatted file output and human-readable console output.
    - Suppresses verbose logs from third-party modules listed in SUPPRESS_LOGGERS.
    - Marks the logger as initialized to prevent reconfiguration.
    """
    root_logger = logging.getLogger(settings._PROJECT_NAME_CODE)

    # Avoid duplicate setup
    if getattr(root_logger, "_initialized", False):
        return root_logger

    # Formatters
    json_formatter = JsonFormatter()
    console_formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt=TIME_FORMAT,
    )
    console_formatter.converter = time.gmtime  # Use UTC for console timestamps

    # Handlers
    file_handler = create_file_handler(LOG_DIR / "app.log", json_formatter)
    console_handler = StreamHandler()
    console_handler.setFormatter(console_formatter)

    # Set log level
    log_level = (
        logging.DEBUG
        if settings.DEBUG
        else getattr(logging, settings.LOG_LEVEL, logging.INFO)
    )
    root_logger.setLevel(log_level)

    # Suppress noisy third-party loggers
    for name in SUPPRESS_LOGGERS:
        logging.getLogger(name).setLevel(logging.ERROR)

    # Attach handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Mark as initialized
    root_logger._initialized = True
    return root_logger


# Initialize and export global logger instance
logger = setup_logging()
