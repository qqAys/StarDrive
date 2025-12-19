from pathlib import Path

from nicegui import app

from app.api import return_file_response
from app.core.paths import STATIC_DIR, STATIC_URL_PREFIX


def setup_static():
    app.add_static_files(STATIC_URL_PREFIX, STATIC_DIR)

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
                lambda f=file, m=media_type: return_file_response(
                    Path(STATIC_DIR / f), media_type=m
                ),
            )
