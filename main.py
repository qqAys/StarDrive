from pathlib import Path

from nicegui import ui

from bootstrap.errors import setup_error_handlers
from bootstrap.lifecycle import setup_lifecycle
from bootstrap.middlewares import setup_middlewares
from bootstrap.routes import setup_routes
from bootstrap.static import setup_static
from config import settings
from core.logging import logger
from core.paths import static_path

setup_lifecycle()
setup_middlewares()
setup_static()
setup_routes()
setup_error_handlers()

logger.info(f"App started at http://{settings.APP_HOST}:{settings.APP_PORT}")

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
