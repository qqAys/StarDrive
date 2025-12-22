from typing import Generic, Optional, TypeVar

from fastapi import HTTPException
from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "OK"
    data: Optional[T] = None


def ok(data=None, message: str = "OK") -> APIResponse:
    return APIResponse(code=0, message=message, data=data)


def fail(
    *,
    code: int,
    message: str,
    http_status: int = 400,
) -> None:
    raise HTTPException(
        status_code=http_status,
        detail={
            "code": code,
            "message": message,
            "data": None,
        },
    )
