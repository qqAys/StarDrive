from datetime import timedelta
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.api import router
from app.core.paths import PREVIEW_CACHE_DIR, STORAGE_DIR
from app.security.tokens import create_token, decode_token

preview_file_url_prefix = "preview-file"


def _resolve_allowed_preview_path(path: str | Path) -> Path:
    resolved = Path(path).resolve()
    allowed_roots = (STORAGE_DIR.resolve(), PREVIEW_CACHE_DIR.resolve())
    if not any(resolved.is_relative_to(root) for root in allowed_roots):
        raise HTTPException(status_code=403, detail="Preview path is not allowed.")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="Preview file not found.")
    return resolved


def create_preview_file_url(path: str | Path) -> str:
    resolved = _resolve_allowed_preview_path(path)
    token = create_token(
        {"path": resolved.as_posix()},
        expires_delta=timedelta(minutes=10),
    )
    return f"/api/{preview_file_url_prefix}/{token}"


@router.get("/" + preview_file_url_prefix + "/{jwt_token}")
async def preview_file(jwt_token: str):
    payload = decode_token(jwt_token)
    if not payload or not payload.get("path"):
        raise HTTPException(status_code=401, detail="Invalid preview token.")

    preview_path = _resolve_allowed_preview_path(payload["path"])
    return FileResponse(preview_path)
