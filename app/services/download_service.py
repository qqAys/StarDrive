from app.models.file_download_model import FileDownloadInfo
from app.security.tokens import decode_token
from app.services.file_service import get_download_info
from app.utils.time import ensure_utc, utc_now


async def verify_download_token(jwt_token: str) -> FileDownloadInfo | None:
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
