import mimetypes
import shutil
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from starlette.background import BackgroundTask

from app.api import router
from app.core.paths import PREVIEW_CACHE_DIR, STORAGE_DIR
from app.security.tokens import create_token, decode_token
from app.services.file_service import create_user_storage_manager

preview_file_url_prefix = "preview-file"


def find_libreoffice_command() -> str | None:
    for command in ("soffice", "libreoffice"):
        found = shutil.which(command)
        if found:
            return found

    macos_app_command = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    if macos_app_command.exists():
        return macos_app_command.as_posix()

    return None


def build_libreoffice_installation_page() -> str:
    """Return a helpful iframe-safe page when Office conversion is unavailable."""
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Office 预览暂不可用</title>
  <style>
    :root { color-scheme: light dark; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px; background: #f8fafc; color: #1e293b; font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    main { width: min(680px, 100%); padding: 36px; border: 1px solid #e2e8f0; border-radius: 20px; background: #fff; box-shadow: 0 18px 45px rgb(15 23 42 / 8%); }
    .icon { width: 52px; height: 52px; display: grid; place-items: center; border-radius: 14px; background: #fff7ed; color: #ea580c; font-size: 28px; }
    h1 { margin: 20px 0 8px; font-size: 24px; line-height: 1.3; }
    p { margin: 0; color: #475569; }
    .notice { margin-top: 24px; padding: 14px 16px; border-radius: 12px; background: #eff6ff; color: #1e40af; }
    h2 { margin: 28px 0 12px; font-size: 16px; }
    ul { margin: 0; padding-left: 20px; color: #475569; }
    li + li { margin-top: 10px; }
    code { display: inline-block; margin-top: 5px; padding: 4px 7px; border-radius: 6px; background: #f1f5f9; color: #0f172a; font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; word-break: break-all; }
    .footer { margin-top: 28px; font-size: 13px; color: #64748b; }
    @media (prefers-color-scheme: dark) {
      body { background: #0f172a; color: #e2e8f0; }
      main { border-color: #334155; background: #1e293b; box-shadow: none; }
      p, ul { color: #cbd5e1; }
      .notice { background: #172554; color: #bfdbfe; }
      code { background: #0f172a; color: #e2e8f0; }
    }
  </style>
</head>
<body>
  <main>
    <div class="icon" aria-hidden="true">⌧</div>
    <h1>暂时无法预览 Office 文件</h1>
    <p>StarDrive 需要服务器上的 LibreOffice 将 Word、Excel、PowerPoint 文件转换为 PDF 后再显示。</p>
    <div class="notice">这是服务器环境缺少组件，不需要在每位访问者的电脑上安装。</div>
    <h2>请由服务器管理员安装 LibreOffice</h2>
    <ul>
      <li>macOS（Homebrew）<br><code>brew install --cask libreoffice</code></li>
      <li>Ubuntu / Debian<br><code>sudo apt update && sudo apt install -y libreoffice libreoffice-calc</code></li>
      <li>Fedora / RHEL<br><code>sudo dnf install -y libreoffice libreoffice-calc</code></li>
      <li>Docker 部署：使用项目当前 Dockerfile 重新构建并部署镜像，镜像已内置 LibreOffice。</li>
    </ul>
    <p class="footer">安装完成后重启 StarDrive 服务，再刷新本页面即可预览该文件。</p>
  </main>
</body>
</html>"""


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


def create_storage_preview_url(
    user_id: str, remote_path: str, office: bool = False
) -> str:
    token = create_token(
        {"user_id": user_id, "remote_path": remote_path, "office": office},
        expires_delta=timedelta(minutes=10),
    )
    return f"/api/{preview_file_url_prefix}/{token}"


@router.get("/" + preview_file_url_prefix + "/{jwt_token}")
async def preview_file(jwt_token: str, request: Request):
    payload = decode_token(jwt_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid preview token.")
    if payload.get("user_id") and payload.get("remote_path") is not None:
        manager = create_user_storage_manager(payload["user_id"])
        remote_path = str(payload["remote_path"])
        if not manager.exists(remote_path):
            raise HTTPException(status_code=404, detail="Preview file not found.")
        metadata = manager.get_file_metadata(remote_path)
        if payload.get("office"):
            converter = find_libreoffice_command()
            if not converter:
                return HTMLResponse(
                    build_libreoffice_installation_page(),
                    status_code=501,
                )
            temp_dir = Path(tempfile.mkdtemp(prefix="stardrive-office-preview-"))
            source = temp_dir / Path(remote_path).name
            try:
                with source.open("wb") as output:
                    for chunk in manager.download_file_with_stream(remote_path):
                        output.write(chunk)
                subprocess.run(
                    [
                        converter,
                        "--headless",
                        "--nologo",
                        "--nofirststartwizard",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        str(temp_dir),
                        str(source),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
                output = next(temp_dir.glob("*.pdf"), None)
                if output is None:
                    raise RuntimeError("No PDF was produced")
            except Exception as exc:
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise HTTPException(
                    status_code=422, detail=f"Office preview failed: {exc}"
                ) from exc
            return FileResponse(
                output,
                media_type="application/pdf",
                background=BackgroundTask(shutil.rmtree, temp_dir, ignore_errors=True),
            )
        start, length, status = 0, metadata.size, 200
        headers = {"Accept-Ranges": "bytes", "Content-Length": str(metadata.size)}
        range_header = request.headers.get("range")
        if range_header and range_header.startswith("bytes="):
            try:
                start_text, end_text = range_header[6:].split("-", 1)
                start = (
                    int(start_text)
                    if start_text
                    else max(0, metadata.size - int(end_text))
                )
                end = min(
                    int(end_text) if end_text else metadata.size - 1, metadata.size - 1
                )
                if start < 0 or end < start or start >= metadata.size:
                    raise ValueError
                length, status = end - start + 1, 206
                headers.update(
                    {
                        "Content-Range": f"bytes {start}-{end}/{metadata.size}",
                        "Content-Length": str(length),
                    }
                )
            except ValueError:
                raise HTTPException(status_code=416, detail="Invalid range")
        return StreamingResponse(
            manager.download_file_with_stream(remote_path, start, length),
            status_code=status,
            media_type=mimetypes.guess_type(remote_path)[0]
            or "application/octet-stream",
            headers=headers,
        )
    if not payload.get("path"):
        raise HTTPException(status_code=401, detail="Invalid preview token.")

    preview_path = _resolve_allowed_preview_path(payload["path"])
    return FileResponse(preview_path)
