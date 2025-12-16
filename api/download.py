import mimetypes
import time
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse, StreamingResponse

import globals
from api import download_form_browser_url_prefix
from security import verify_jwt_secret
from services.file_service import get_download_info, FileDownloadInfo


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

    return download_info


router = APIRouter(prefix="/api")


@router.get("/" + download_form_browser_url_prefix + "/{jwt_token}")
async def download_form_browser_api(
    validated_data: Annotated[FileDownloadInfo, Depends(verify_download_token)],
):
    file_manager = globals.get_storage_manager()

    is_multi_file = isinstance(validated_data.name, list)

    def multi_download(source_is_single_dir: bool = False):
        if source_is_single_dir:
            relative_paths = [validated_data.path]
        else:
            relative_paths = validated_data.path

        if not relative_paths:
            raise HTTPException(status_code=400, detail="No files or folders provided.")

        timestamp = int(time.time())

        if source_is_single_dir:
            filename_as = f"{validated_data.name}_archive_{timestamp}.tar.gz"
        else:
            filename_as = f"bulk_download_{timestamp}.tar.gz"

        quoted_filename_as = quote(filename_as)

        headers = {
            "Content-Disposition": f'attachment; filename="{quoted_filename_as}"',
            "Cache-Control": "no-store",
        }

        return StreamingResponse(
            content=file_manager.download_file_with_compressed_stream(
                relative_paths, validated_data.base_path
            ),
            media_type="application/gzip",
            headers=headers,
        )

    def single_download():
        if not file_manager.exists(str(validated_data.path)):
            raise HTTPException(status_code=404, detail="File not found")

        mime_type, _ = mimetypes.guess_type(validated_data.name)

        return FileResponse(
            path=file_manager.get_full_path(str(validated_data.path)),
            filename=validated_data.name,
            media_type=mime_type or "application/octet-stream",
        )

    if not is_multi_file:
        if validated_data.type == "dir":
            return multi_download(source_is_single_dir=True)
        else:
            return single_download()
    else:
        return multi_download()
