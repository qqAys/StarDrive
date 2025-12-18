from nicegui import app
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

from core.i18n import _
from core.logging import logger
from security.routes import is_route_unrestricted


class AuthMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        path = request.url.path

        # NiceGUI 内部资源直接放行
        if path.startswith("/_nicegui"):
            return await call_next(request)

        # 白名单路由直接放行
        if is_route_unrestricted(path):
            return await call_next(request)

        # 判断是否存在“登录态线索”
        has_user_id = app.storage.user.get("user_id") is not None
        has_token_version = app.storage.user.get("token_version") is not None

        if not has_user_id or not has_token_version:
            logger.warning(
                _("Unauthorized access to {}, request_uuid: {}").format(
                    path,
                    getattr(request.state, "request_uuid", "unknown"),
                )
            )
            return RedirectResponse(f"/login/?redirect_to={path}")

        # 后续由页面装饰器判断访问权限
        return await call_next(request)
