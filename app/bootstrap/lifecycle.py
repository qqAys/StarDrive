from nicegui import app

from app import globals
from app.crud.user_crud import UserCRUD
from app.services.file_service import StorageManager
from app.services.local_db_service import (
    init_local_db,
    close_local_db,
    get_db_context,
)
from app.services.user_service import UserManager
from app.storage.local_storage import LocalStorage


async def on_startup():
    """
    Initialize application services during startup.

    - Sets up the local database connection.
    - Configures the file storage backend (defaults to LocalStorage).
    - Initializes the user management system, including loading or creating default users.
    - Registers shared service instances in the global context for access across the app.
    """
    await init_local_db()

    # Initialize and register the storage manager
    storage = StorageManager()
    storage.set_current_backend(LocalStorage.name)
    globals.set_storage_manager(storage)

    # Initialize and register the user manager
    user_manager = UserManager(
        user_crud=UserCRUD,
        db_context=get_db_context,
    )
    await user_manager.initialize()
    globals.set_user_manager(user_manager)


async def on_shutdown():
    """
    Gracefully shut down application resources.

    Currently closes the local database connection to ensure data integrity.
    """
    await close_local_db()


def setup_lifecycle():
    """
    Register startup and shutdown event handlers with NiceGUI.

    Ensures proper initialization and cleanup of critical services
    aligned with the web application's lifecycle.
    """
    app.on_startup(on_startup)
    app.on_shutdown(on_shutdown)
