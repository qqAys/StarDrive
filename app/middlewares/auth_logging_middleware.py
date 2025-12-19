from uuid import uuid4

from nicegui import app
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.core.logging import logger
from app.security.routes import is_route_unrestricted


class AuthLoggingMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # NiceGUI 内部资源放行
        if path.startswith("/_nicegui"):
            return await call_next(request)

        # 公共日志信息
        request_uuid = uuid4()
        request.state.request_uuid = request_uuid
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

        # 白名单路由放行
        if is_route_unrestricted(path):
            logger.debug({"auth": "pass", "reason": "unrestricted", **log_ctx})
            return await call_next(request)

        user_storage = app.storage.user
        user_id = user_storage.get("user_id")
        is_authenticated = user_id and user_storage.get("token_version") is not None

        # 没有认证线索
        if not is_authenticated:
            full_ctx = {
                **log_ctx,
                "headers": dict(request.headers),
                "cookies": dict(request.cookies),
            }
            logger.warning({"auth": "fail", "reason": "unauthorized", **full_ctx})
            return RedirectResponse(f"/login/?redirect_to={path}")

        # 已认证通过
        logger.debug({"auth": "pass", "user": user_id, **log_ctx})

        return await call_next(request)
