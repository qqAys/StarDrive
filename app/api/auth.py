from app.api import auth_url_prefix, router
from app.core.exceptions import BusinessException
from app.core.i18n import _
from app.core.response import ok
from app.crud.user_crud import UserCRUD
from app.schemas.user_schema import (
    UserLogin,
    UserRegister,
    UserResetPasswordConfirm,
    UserResetPasswordRequest,
)
from app.security.tokens import create_access_token, create_refresh_token
from app.services.local_db_service import get_db_context


@router.post("/" + auth_url_prefix + "/login")
async def login_api(user_login: UserLogin):
    async with get_db_context() as session:
        user = await UserCRUD.authenticate(
            session=session,
            email=user_login.email,
            password=user_login.password,
        )

    if not user:
        raise BusinessException(
            code=2001,
            message=_("Invalid username or password"),
            http_status=401,
        )

    access_payload = {"sub": user.id}
    refresh_payload = {
        **access_payload,
        "tv": user.token_version,
    }

    return ok(
        {
            "access_token": create_access_token(access_payload),
            "refresh_token": create_refresh_token(refresh_payload),
            "expires_in": 900,
        }
    )


@router.post("/" + auth_url_prefix + "/register")
async def register_api(user_register: UserRegister):
    from app import globals

    user_manager = globals.get_user_manager()
    try:
        user = await user_manager.register_user(
            email=user_register.email,
            password=user_register.password,
        )
    except ValueError as exc:
        raise BusinessException(
            code=2002,
            message=str(exc),
            http_status=400,
        ) from exc

    return ok({"id": user.id, "email": user.email})


@router.post("/" + auth_url_prefix + "/forgot-password")
async def forgot_password_api(request: UserResetPasswordRequest):
    from app import globals

    user_manager = globals.get_user_manager()
    status = await user_manager.request_password_reset(email=request.email)
    return ok({"status": status})


@router.post("/" + auth_url_prefix + "/reset-password")
async def reset_password_api(request: UserResetPasswordConfirm):
    from app import globals

    user_manager = globals.get_user_manager()
    try:
        await user_manager.reset_password_with_token(
            token=request.token,
            new_password=request.new_password,
        )
    except ValueError as exc:
        raise BusinessException(
            code=2003,
            message=str(exc),
            http_status=400,
        ) from exc
    return ok({"reset": True})
