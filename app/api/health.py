from app.api import router
from app.config import settings
from app.core.response import ok


@router.get("/healthz")
async def health_check():
    """Unauthenticated liveness endpoint for container orchestrators."""
    return ok({"status": "ok", "version": settings.APP_VERSION})
