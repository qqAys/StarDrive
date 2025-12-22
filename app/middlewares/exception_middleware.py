from fastapi import Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse

from app.core.exceptions import BusinessException
from app.core.logging import logger
from app.core.response import APIResponse


async def business_exception_handler(
    request: Request,
    exc: BusinessException,
):
    return JSONResponse(
        status_code=exc.http_status,
        content=APIResponse(
            code=exc.code,
            message=exc.message,
            data=None,
        ).model_dump(),
    )


async def http_exception_handler(
    request: Request,
    exc: FastAPIHTTPException,
):
    detail = exc.detail

    if isinstance(detail, dict):
        return JSONResponse(
            status_code=exc.status_code,
            content=detail,
        )

    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse(
            code=exc.status_code,
            message=str(detail),
            data=None,
        ).model_dump(),
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
):
    logger.exception("Unhandled exception", exc_info=exc)

    return JSONResponse(
        status_code=500,
        content=APIResponse(
            code=9000,
            message="Internal server error",
            data=None,
        ).model_dump(),
    )
