import gettext
import json
import logging
import re
from datetime import datetime
from logging import getLogger, StreamHandler
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi.responses import FileResponse
from nicegui import app

from config import settings

app_root = Path(__file__).parent
data_dir = app_root / "data"
static_dir = "/static"
static_path = app_root / "static"

# --- 日志 ---

LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5
LOG_DATE_FMT = "%Y-%m-%d %H:%M:%S"

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

# 添加 Handler
root_logger.addHandler(stream_handler)
root_logger.addHandler(app_file_handler)

# APP LOGGER
logger = getLogger(settings._PROJECT_NAME_CODE)

# --- 本地化 ---

LOCALE_DIR = "locales"

# 支持的语言列表
# 从 locales 目录下加载
SUPPORTED_LANGUAGES = [
    item.name for item in Path(LOCALE_DIR).iterdir() if item.is_dir()
]
logger.debug(f"Supported languages: {SUPPORTED_LANGUAGES}")

# 存储所有语言的 Translation 对象
translations = {}


def load_translations(
    localedir=LOCALE_DIR, domain="messages", supported_languages=None
):
    """
    加载所有支持语言的 Translation 对象到字典中。
    """
    if supported_languages is None:
        supported_languages = SUPPORTED_LANGUAGES
    for lang_code in supported_languages:
        try:
            # 创建特定语言的 Translation 对象
            t = gettext.translation(domain, localedir=localedir, languages=[lang_code])
            translations[lang_code] = t
        except FileNotFoundError:
            logger.warning(f"Translation file not found for language: {lang_code}")
            translations[lang_code] = gettext.NullTranslations()


load_translations()


def dynamic_gettext(message: str, lang_code: str = None) -> str:
    """
    根据给定的语言代码返回翻译后的消息。
    """
    if lang_code is None:
        try:
            # 尝试从 NiceGUI 用户存储中获取
            lang_code = app.storage.user.get("default_lang", "en_US")
        except RuntimeError:
            # 如在初始化时，使用默认语言
            lang_code = "en_US"
    # 查找对应的 Translation 对象
    translator = translations.get(lang_code)

    if translator:
        # 使用该对象的 gettext 方法进行翻译
        return translator.gettext(message)
    else:
        return message


_ = dynamic_gettext


# --- 工具函数 ---


def bytes_to_human_readable(num_bytes: int) -> str:
    """
    将字节数转换为人类可读的字符串。
    """
    for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} YB"


def timestamp_to_human_readable(timestamp: float) -> str:
    """
    将时间戳转换为人类可读的格式。
    """
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def return_file_response(
    path: str | Path,
    media_type: str = None,
    filename: str = None,
    status_code: int = 200,
):
    return FileResponse(
        path=path, media_type=media_type, filename=filename, status_code=status_code
    )


EMAIL_REGEX = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"


def is_valid_email(email):
    """
    判断邮箱格式是否有效
    """
    if re.fullmatch(EMAIL_REGEX, email):
        return True
    return False
