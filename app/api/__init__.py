from pathlib import Path

from starlette.responses import FileResponse

download_form_browser_url_prefix = "download-form-browser"


def return_file_response(
    path: str | Path,
    media_type: str = None,
    filename: str = None,
    status_code: int = 200,
):
    return FileResponse(
        path=path, media_type=media_type, filename=filename, status_code=status_code
    )
