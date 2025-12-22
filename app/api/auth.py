from app.api import auth_url_prefix, router
from app.core.exceptions import BusinessException
from app.core.i18n import _
from app.core.response import ok
from app.schemas.user_schema import UserLogin


@router.post("/" + auth_url_prefix + "/login")
async def login_api(user_login: UserLogin):
    user = await authenticate(user_login)
    if not user:
        raise BusinessException(
            code=2001,
            message=_("Invalid username or password"),
            http_status=401,
        )

    return ok(
        {
            "access_token": "...",
            "refresh_token": "...",
            "expires_in": 900,
        }
    )
