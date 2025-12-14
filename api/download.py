import time
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse, StreamingResponse

import globals
from api import download_file_form_browser_url_prefix
from security import verify_jwt_secret
from services.file_service import get_download_info


# 依赖函数：用于解析和验证令牌
async def verify_download_token(jwt_token: str):
    payload = verify_jwt_secret(jwt_token)
    if not payload:
        raise HTTPException(
            status_code=401, detail="Invalid download link or has expired."
        )

    download_info = get_download_info(payload.get("download_id"))

    if not download_info:
        raise HTTPException(
            status_code=401, detail="Invalid download link or has expired."
        )

    file_path = download_info["path"]
    file_name = download_info["name"]
    base_dir_path = download_info["base_path"]

    if not file_path or not file_name:
        raise HTTPException(status_code=401, detail="Download link is invalid.")

    if isinstance(file_path, str) and isinstance(file_name, str):
        is_multi_file = False
    elif isinstance(file_path, list) and isinstance(file_name, list):
        is_multi_file = True
    else:
        raise HTTPException(
            status_code=401, detail="Download link is invalid."
        )

    return is_multi_file, file_path, file_name, base_dir_path


router = APIRouter(prefix="/api")


@router.get("/" + download_file_form_browser_url_prefix + "/{jwt_token}")
async def download_file_form_browser_api(
    validated_data: Annotated[tuple[bool, str | list[str], str | list[str], str], Depends(verify_download_token)],
):
    file_manager = globals.get_storage_manager()

    is_multi_file, full_path, file_name, base_dir_path = validated_data

    if not is_multi_file:
        if not file_manager.exists(str(full_path)):
            raise HTTPException(status_code=404, detail="File not found")

        return FileResponse(
            path=file_manager.get_full_path(str(full_path)),
            filename=file_name,
            media_type="application/octet-stream",
        )
    else:
        relative_paths = full_path
        if not relative_paths:
            raise HTTPException(status_code=400, detail="No files or folders provided.")

        filename_as = f"download_{int(time.time())}.zip"

        headers = {
            "Content-Disposition": f'attachment; filename="{filename_as}"',
            "Content-Type": "application/zip",
        }

        return StreamingResponse(
            content=file_manager.download_file_with_compressed_stream(relative_paths, base_dir_path),
            headers=headers,
            media_type="application/zip"
        )
