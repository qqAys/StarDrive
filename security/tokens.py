from datetime import timedelta

import jwt

from config import settings
from utils.time import utc_now
from .constants import JWT_ALGORITHM


def create_token(data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = utc_now() + expires_delta
    to_encode["exp"] = expire

    return jwt.encode(
        to_encode,
        settings.STORAGE_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token,
            settings.STORAGE_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
    except Exception:
        return None


def create_access_token(data: dict, expires_minutes: int = 15):
    return create_token(data, timedelta(minutes=expires_minutes))


def create_refresh_token(data: dict, expires_days: int = 7):
    return create_token(data, timedelta(days=expires_days))
