import random
import string

import bcrypt
import jwt
from passlib.context import CryptContext

from config import settings

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

JWT_ALGORITHM = "HS256"


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


def generate_jwt_secret(payload: dict) -> str:
    """
    生成 JWT 密钥
    """

    token = jwt.encode(payload, settings.STORAGE_SECRET, algorithm=JWT_ALGORITHM)

    return token


def verify_jwt_secret(token: str) -> dict | None:
    """
    验证 JWT 密钥
    """

    try:
        payload = jwt.decode(token, settings.STORAGE_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except (jwt.ExpiredSignatureError, jwt.DecodeError, jwt.InvalidTokenError):
        return None
