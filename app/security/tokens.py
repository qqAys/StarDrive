from datetime import timedelta

import jwt

from app.config import settings
from app.utils.time import utc_now
from .constants import JWT_ALGORITHM


def create_token(data: dict, expires_delta: timedelta) -> str:
    """
    Create a signed JWT token with standard claims.

    Args:
        data: Payload data to include in the token.
        expires_delta: Lifetime of the token from the current time.

    Returns:
        A signed JWT string.
    """
    iat = utc_now()
    expire = iat + expires_delta
    to_encode = {
        **data,
        "iss": settings._PROJECT_NAME_CODE,
        "iat": iat,
        "exp": expire,
    }
    return jwt.encode(
        to_encode,
        settings.APP_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict | None:
    """
    Decode and validate a JWT token.

    Args:
        token: The JWT string to decode.

    Returns:
        The decoded payload as a dictionary if valid; None if invalid or expired.
    """
    try:
        return jwt.decode(
            token,
            settings.APP_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
    except Exception:
        return None


def create_access_token(data: dict, expires_minutes: int = 15) -> str:
    """
    Create a short-lived access token (default: 15 minutes).

    Args:
        data: Payload to include in the token (e.g., user ID).
        expires_minutes: Token lifetime in minutes.

    Returns:
        A signed access JWT.
    """
    return create_token(data, timedelta(minutes=expires_minutes))


def create_refresh_token(data: dict, expires_days: int = 7) -> str:
    """
    Create a long-lived refresh token (default: 7 days).

    Args:
        data: Payload to include in the token (typically minimal user identifier).
        expires_days: Token lifetime in days.

    Returns:
        A signed refresh JWT.
    """
    return create_token(data, timedelta(days=expires_days))
