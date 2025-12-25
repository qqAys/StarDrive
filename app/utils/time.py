from datetime import datetime, timezone

from app.config import settings


def utc_now() -> datetime:
    """Return the current time as an aware datetime object in UTC."""
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    """
    Ensure the given datetime object is timezone-aware and converted to UTC.

    If the input datetime is naive (no timezone info), it is assumed to be in UTC.
    Otherwise, it is converted to UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def timestamp_to_human_readable(timestamp: float, tz=None) -> str:
    """
    Convert a Unix timestamp to a human-readable date and time string.

    The output format is: "YYYY-MM-DD HH:MM:SS TZ".
    If no timezone is provided, the system default timezone is used.
    Returns "None" if the timestamp is falsy (e.g., 0 or None).
    """
    if not timestamp:
        return "None"
    return datetime.fromtimestamp(
        timestamp, tz=tz or settings.SYSTEM_DEFAULT_TIMEZONE
    ).strftime("%Y-%m-%d %H:%M:%S %Z")


def datetime_to_human_readable(dt: datetime, tz=None) -> str:
    """
    Convert a datetime object to a human-readable date and time string.

    The output format is: "YYYY-MM-DD HH:MM:SS TZ".
    If no timezone is provided, the system default timezone is used.
    Returns "None" if the datetime is falsy (e.g., None).
    """
    if not dt:
        return "None"
    return dt.astimezone(tz or settings.SYSTEM_DEFAULT_TIMEZONE).strftime(
        "%Y-%m-%d %H:%M:%S %Z"
    )
