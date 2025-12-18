from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from core.logging import logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_uuid = uuid4()

        logger.debug(
            {
                "request_uuid": str(request.state.request_uuid),
                "client": f"{request.client.host}:{request.client.port}",
                "method": request.method,
                "url": str(request.url),
                "headers": dict(request.headers),
                "query_params": dict(request.query_params),
                "cookies": dict(request.cookies),
            }
        )

        return await call_next(request)
