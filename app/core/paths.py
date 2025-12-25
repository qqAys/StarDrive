import os
from pathlib import Path

# Determine the absolute project root (three levels up from this file)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Application source root
APP_ROOT = PROJECT_ROOT / "app"

# Internationalization and static assets
LOCALES_DIR = APP_ROOT / "locales"  # Translation files (.mo/.po)
STATIC_URL_PREFIX = "/static"  # URL prefix for static files
STATIC_DIR = APP_ROOT / "static"  # Directory serving static assets

# Runtime data directories (configurable via environment variable)
DATA_ROOT = PROJECT_ROOT / os.environ.get("STARDIVE_APP_DATA_DIR", "app_data")
LOG_DIR = DATA_ROOT / "log"  # Application logs
DB_DIR = DATA_ROOT / "db"  # Database files (e.g., SQLite)
NICEGUI_DIR = DATA_ROOT / "nicegui"  # NiceGUI internal storage (e.g., user sessions)
STORAGE_DIR = DATA_ROOT / "storage"  # General persistent app data

# Ensure all runtime directories exist
for directory in [LOG_DIR, DB_DIR, NICEGUI_DIR, STORAGE_DIR]:
    directory.mkdir(parents=True, exist_ok=True)
