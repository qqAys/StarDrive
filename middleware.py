from uuid import uuid4

from nicegui import app
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

from security import is_route_unrestricted
from utils import logger, _


class AuthLoggerMiddleware(BaseHTTPMiddleware):
    """
    中间件，用于处理日志记录与用户认证
    如果用户未登录，则跳转到登录页面
    """

    async def dispatch(self, request: Request, call_next):
        request.state.request_uuid = uuid4()

        request_data = {
            "request_uuid": str(request.state.request_uuid),
            "client": f"{request.client.host}:{request.client.port}",
            "method": request.method,
            "url": str(request.url),
            "headers": dict(request.headers),
            "query_params": dict(request.query_params),
            "cookies": dict(request.cookies),
            # "body": await request.body(),
        }
        logger.debug(request_data)

        if not app.storage.user.get("authenticated", False):
            if not request.url.path.startswith(
                "/_nicegui"
            ) and not is_route_unrestricted(request.url.path):
                logger.warning(
                    _("Unauthorized access to {}, request_uuid: {}").format(
                        request.url, str(request.state.request_uuid)
                    )
                )
                return RedirectResponse(f"/login/?redirect_to={request.url.path}")

        return await call_next(request)
