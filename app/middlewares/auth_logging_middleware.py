from uuid import uuid4

from nicegui import app
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.core.logging import logger
from app.security.routes import is_route_unrestricted


class AuthLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce authentication and log access attempts.

    This middleware:
    - Skips authentication for internal NiceGUI routes (`/_nicegui/**`).
    - Allows unrestricted access to public routes (as defined by `is_route_unrestricted`).
    - Checks user authentication status using NiceGUI's user storage.
    - Logs detailed context for both authorized and unauthorized requests.
    - Redirects unauthenticated users to the login page with a `redirect_to` parameter.
    """

    @staticmethod
    def get_browser_language(request: Request) -> str | None:
        accept_language = request.headers.get("accept-language")
        if not accept_language:
            return None
        return accept_language.split(",")[0].strip().replace("-", "_")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip authentication for internal NiceGUI static/assets routes
        if path.startswith("/_nicegui"):
            return await call_next(request)

        # Generate a unique ID for this request for traceability
        request_uuid = uuid4()
        request.state.request_uuid = request_uuid

        # Determine the real client IP address
        client_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or request.headers.get("x-real-ip")
            or request.client.host
        )
        log_ctx = {
            "request_uuid": str(request_uuid),
            "method": request.method,
            "url": str(request.url),
            "client": f"{client_ip}:{request.client.port}",
        }

        # Allow access without authentication for public routes
        if is_route_unrestricted(path):
            logger.debug({"auth": "pass", "reason": "unrestricted", **log_ctx})
            return await call_next(request)

        # Set the language
        if "default_lang" not in app.storage.user:
            app.storage.user["default_lang"] = self.get_browser_language(request)

        # Check authentication state from NiceGUI user storage
        user_storage = app.storage.user
        user_id = user_storage.get("user_id")
        is_authenticated = (
            user_id is not None and user_storage.get("token_version") is not None
        )

        if not is_authenticated:
            # Log full context for debugging unauthorized access
            full_ctx = {
                **log_ctx,
                "headers": dict(request.headers),
                "cookies": dict(request.cookies),
            }
            logger.warning({"auth": "fail", "reason": "unauthorized", **full_ctx})
            # Redirect to login with original path as redirect target
            return RedirectResponse(f"/login/?redirect_to={path}")

        # Authentication succeeded
        logger.debug({"auth": "pass", "user": user_id, **log_ctx})

        return await call_next(request)
