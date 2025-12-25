from app.models.file_download_model import FileDownloadInfo
from app.security.tokens import decode_token
from app.services.file_service import get_download_info
from app.utils.time import ensure_utc, utc_now


async def verify_download_token(jwt_token: str) -> FileDownloadInfo | None:
    """
    Verify a JWT-based download token and return the associated file download record.

    This function:
    - Decodes the provided JWT token.
    - Extracts the `download_id` from the payload.
    - Fetches the corresponding `FileDownloadInfo` from the database.
    - Checks that the download link has not expired.

    Args:
        jwt_token: The JWT string representing a time-limited download authorization.

    Returns:
        A valid `FileDownloadInfo` instance if the token is valid and not expired;
        `None` otherwise.
    """
    payload = decode_token(jwt_token)
    if not payload:
        return None

    download_id = payload.get("download_id")
    if not download_id:
        return None

    download_info = await get_download_info(download_id)
    if not download_info:
        return None

    if ensure_utc(download_info.expires_at_utc) < utc_now():
        return None

    return download_info
