import os

from app.core.paths import NICEGUI_DIR


def setup_environment() -> None:
    os.environ.setdefault(
        "NICEGUI_STORAGE_PATH",
        NICEGUI_DIR.resolve().as_posix(),
    )
