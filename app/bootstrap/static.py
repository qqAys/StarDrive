from nicegui import app

from app.api import return_file_response
from app.core.paths import STATIC_DIR, STATIC_URL_PREFIX


def setup_static():
    """
    Configure static file serving for the NiceGUI application.

    1. Registers a static file route under `/static` pointing to the `static/` directory.
    2. Explicitly maps common favicon and web manifest files to their respective MIME types
       using API routes, ensuring correct content-type headers for browser compatibility.

    This is necessary because some browsers request favicon assets at the root path (e.g., `/favicon.ico`),
    and NiceGUI’s default static file handler does not serve them unless explicitly routed.
    """
    # Serve general static assets (CSS, JS, images, etc.)
    app.add_static_files(STATIC_URL_PREFIX, STATIC_DIR)

    # Define favicon-related files and their MIME types
    favicon_routes = {
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

    # Register individual API routes for each favicon asset
    for media_type, filenames in favicon_routes.items():
        for filename in filenames:
            # Capture `filename` and `media_type` in lambda defaults to avoid late binding
            app.add_api_route(
                f"/{filename}",
                lambda f=filename, m=media_type: return_file_response(
                    STATIC_DIR / f, media_type=m
                ),
            )
