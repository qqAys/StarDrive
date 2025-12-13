from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse

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

    if not file_path or not file_name:
        raise HTTPException(status_code=401, detail="Download link is invalid.")

    return Path(file_path), file_name


router = APIRouter(prefix="/api")


@router.get("/" + download_file_form_browser_url_prefix + "/{jwt_token}")
async def download_file_form_browser_api(
    validated_data: Annotated[tuple[Path, str], Depends(verify_download_token)],
):
    file_manager = globals.get_storage_manager()

    full_path, file_name = validated_data

    if not file_manager.exists(str(full_path)):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_manager.get_full_path(str(full_path)),
        filename=file_name,
        media_type="application/octet-stream",  # 通用下载类型
    )
