import mimetypes
import time
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import StreamingResponse

from app.api import download_form_browser_url_prefix, router
from app.schemas.file_schema import FileType
from app.services.download_service import verify_download_token
from app.services.file_service import FileDownloadInfo, create_user_storage_manager


@router.get("/" + download_form_browser_url_prefix + "/{jwt_token}")
async def download_form_browser_api(
    validated_data: Annotated[FileDownloadInfo, Depends(verify_download_token)],
    request: Request,
):
    if not validated_data:
        raise HTTPException(
            status_code=401, detail="Invalid download link or has expired."
        )

    if not validated_data.user_id:
        raise HTTPException(status_code=400, detail="Download owner is missing.")

    file_manager = create_user_storage_manager(validated_data.user_id)

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
        metadata = file_manager.get_file_metadata(str(validated_data.path))
        start, length, status_code = 0, metadata.size, 200
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(validated_data.name)}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(metadata.size),
            "Cache-Control": "no-store",
        }
        range_header = request.headers.get("range")
        if range_header and range_header.startswith("bytes="):
            try:
                start_text, end_text = range_header[6:].split("=", 1)[0].split("-", 1)
                start = int(start_text) if start_text else max(0, metadata.size - int(end_text))
                end = int(end_text) if end_text else metadata.size - 1
                if start < 0 or end < start or start >= metadata.size:
                    raise ValueError
                end = min(end, metadata.size - 1)
                length, status_code = end - start + 1, 206
                headers["Content-Range"] = f"bytes {start}-{end}/{metadata.size}"
                headers["Content-Length"] = str(length)
            except ValueError:
                raise HTTPException(status_code=416, detail="Invalid range")
        return StreamingResponse(
            file_manager.download_file_with_stream(str(validated_data.path), start, length),
            status_code=status_code,
            media_type=mime_type or "application/octet-stream",
            headers=headers,
        )

    if not is_multi_file:
        if validated_data.type == FileType.DIR:
            return multi_download(source_is_single_dir=True)
        else:
            return single_download()
    else:
        return multi_download()
