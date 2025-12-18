from datetime import datetime, timezone

from config import settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def timestamp_to_human_readable(timestamp: float, tz=None) -> str:
    """
    将时间戳转换为人类可读的格式。
    """
    if not timestamp:
        return "None"
    return datetime.fromtimestamp(
        timestamp, tz=tz or settings.SYSTEM_DEFAULT_TIMEZONE
    ).strftime("%Y-%m-%d %H:%M:%S")
