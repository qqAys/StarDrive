import random
import string

import bcrypt
from fastapi.requests import Request
from fastapi.responses import RedirectResponse
from nicegui import app
from passlib.context import CryptContext
from starlette.middleware.base import BaseHTTPMiddleware

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 不需要认证的页面
unrestricted_page_routes = (
    # 静态资源
    "/favicon.ico",
    "/apple-touch-icon.png",
    "/favicon-16x16.png",
    "/favicon-32x32.png",
    "/android-chrome-192x192.png",
    "/android-chrome-512x512.png",
    "/site.webmanifest",
    # 登录页面
    "/login/",
    "/login",
)


@app.add_middleware
class AuthMiddleware(BaseHTTPMiddleware):
    """
    中间件，用于处理用户认证
    如果用户未登录，则跳转到登录页面
    """

    async def dispatch(self, request: Request, call_next):
        if not app.storage.user.get("authenticated", False):
            if (
                not request.url.path.startswith("/_nicegui")
                and request.url.path not in unrestricted_page_routes
            ):
                return RedirectResponse(f"/login?redirect_to={request.url.path}")
        return await call_next(request)


class HashingManager:

    @staticmethod
    def hash_password(password: str) -> str:
        """
        对明文密码进行哈希处理
        """
        # 生成随机 salt
        salt = bcrypt.gensalt()

        # 转换 bytes
        password_bytes = password.encode("utf-8")

        # 哈希处理
        hashed_password = bcrypt.hashpw(password_bytes, salt)

        return hashed_password.decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        验证明文密码是否与存储的哈希密码匹配。
        """
        # 转换 bytes
        password_bytes = plain_password.encode("utf-8")

        # 验证
        return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))


def generate_random_password() -> str:
    """
    生成随机密码
    """

    password = "".join(
        random.choice(string.ascii_letters + string.digits) for _ in range(10)
    )

    return password
