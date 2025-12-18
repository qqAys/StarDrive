from nicegui import app

import globals
from crud.user_crud import UserCRUD
from services.file_service import StorageManager
from services.local_db_service import (
    init_local_db,
    close_local_db,
    get_db_context,
)
from services.user_service import UserManager
from storage.local_storage import LocalStorage


async def on_startup():
    await init_local_db()

    storage = StorageManager()
    storage.set_current_backend(LocalStorage.name)
    globals.set_storage_manager(storage)

    user_manager = UserManager(
        user_crud=UserCRUD,
        db_context=get_db_context,
    )
    await user_manager.initialize()
    globals.set_user_manager(user_manager)


async def on_shutdown():
    await close_local_db()


def setup_lifecycle():
    app.on_startup(on_startup)
    app.on_shutdown(on_shutdown)
