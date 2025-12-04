from nicegui import ui, app

import globals
from storage.local_storage import LocalStorage
from storage.manager import StorageManager
from ui.pages import login, browser


@app.on_startup
def on_app_startup():
    M = StorageManager()
    M.set_current_backend(LocalStorage.name)
    globals.set_storage_manager(M)

    app.include_router(login.router)
    app.include_router(browser.router)


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        host="0.0.0.0",
        port=8080,
        reload=False,
        storage_secret="THIS_NEEDS_TO_BE_CHANGED",
        show=False,
    )
