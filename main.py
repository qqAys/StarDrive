import traceback
from pathlib import Path
from uuid import uuid4

from fastapi.requests import Request
from nicegui import ui, app

import globals
from api import download
from config import settings
from middleware import AuthLoggerMiddleware
from services.file_service import StorageManager

# from services.local_db_service import init_local_db, close_local_db
from storage.local_storage import LocalStorage
from ui.pages import login, browser, console, profile, share
from ui.pages.error_page import render_404, render_50x
from utils import return_file_response, logger, static_path

app.add_middleware(AuthLoggerMiddleware)


@ui.page("/test_raise_error")
def test_raise_error():
    raise Exception("500 TEST")


@app.on_page_exception
def timeout_error_page(exception: Exception) -> None:
    request_uuid = uuid4()
    error_traceback = traceback.format_exc(chain=False)

    logger_text = {
        "request_uuid": str(request_uuid),
        "app_storage": app.storage.user,
        "exception": str(exception),
        "traceback": error_traceback,
    }
    logger.error(logger_text)
    render_50x(str(request_uuid), str(exception))
    return


@app.on_startup
async def on_app_startup():
    # ULID 在 python 字典中作为 key 的性能还是非常好的
    # 同时考虑到 app.storage.general 使用本地文件持久化，所以此处暂时不用数据库存储
    # await init_local_db()
    local_storage_manager = StorageManager()
    local_storage_manager.set_current_backend(LocalStorage.name)
    globals.set_storage_manager(local_storage_manager)

    app.add_static_files("/static", Path(static_path))

    favicon_stuff = {
        "image/x-icon": ["favicon.ico"],
        "image/png": [
            "apple-touch-icon.png",
            "favicon-32x32.png",
            "favicon-16x16.png",
            "android-chrome-192x192.png",
            "android-chrome-512x512.png",
        ],
        "application/manifest+json": ["site.webmanifest"],
    }

    for media_type, files in favicon_stuff.items():
        for file in files:
            app.add_api_route(
                f"/{file}",
                lambda file_=file, media_type_=media_type: return_file_response(
                    Path(static_path / file_), media_type=media_type_
                ),
            )

    app.include_router(login.router)
    app.include_router(browser.router)
    app.include_router(share.router)
    app.include_router(profile.router)
    app.include_router(console.router)

    app.include_router(download.router)

    @ui.page("/{_:path}")
    def not_found_page(request: Request):
        request_uuid = request.state.request_uuid
        logger_text = {
            "request_uuid": str(request_uuid),
            "path": request.url.path,
            "app_storage": app.storage.user,
        }
        logger.info(logger_text)
        render_404(request_uuid)
        return

    logger.info(f"App started at http://{settings.APP_HOST}:{settings.APP_PORT}")


# @app.on_shutdown
# async def on_app_shutdown():
#     await close_local_db()


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        storage_secret=settings.STORAGE_SECRET,
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        title=settings.APP_TITLE,
        favicon=Path(static_path / "favicon.ico"),
        language=settings.APP_DEFAULT_LANGUAGE,
        dark=None,  # None是自动切换
        reload=False,  # 避免每次修改代码时重启
        show=False,  # 防止启动时调用浏览器
        prod_js=True,
        show_welcome_message=False,
        session_middleware_kwargs={
            "session_cookie": settings._PROJECT_NAME_CODE + "_session"
        },  # 防止cookie键名称冲突
        reconnect_timeout=settings.NICEGUI_RECONNECT_TIMEOUT,
        fastapi_docs=settings.DEBUG,
    )
