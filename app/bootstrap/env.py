import os

from app.core.paths import NICEGUI_DIR


def setup_environment() -> None:
    """
    Configure environment variables required by the application.

    Specifically sets the 'NICEGUI_STORAGE_PATH' to the resolved absolute path
    of the NICEGUI_DIR (as a POSIX-style string), but only if it is not already set.
    This ensures NiceGUI persists user sessions and internal state in the designated
    application data directory, supporting consistent behavior across runs.
    """
    os.environ.setdefault(
        "NICEGUI_STORAGE_PATH",
        NICEGUI_DIR.resolve().as_posix(),
    )
