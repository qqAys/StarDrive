import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

APP_ROOT = PROJECT_ROOT / "app"

# i18n / static
LOCALES_DIR = APP_ROOT / "locales"
STATIC_URL_PREFIX = "/static"
STATIC_DIR = APP_ROOT / "static"

# runtime
DATA_ROOT = PROJECT_ROOT / os.environ.get("STARDIVE_APP_DATA_DIR", "app_data")
LOG_DIR = DATA_ROOT / "log"
DB_DIR = DATA_ROOT / "db"
NICEGUI_DIR = DATA_ROOT / "nicegui"
STORAGE_DIR = DATA_ROOT / "storage"

for p in [LOG_DIR, DB_DIR, NICEGUI_DIR, STORAGE_DIR]:
    p.mkdir(parents=True, exist_ok=True)
