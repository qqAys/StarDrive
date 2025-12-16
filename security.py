import fnmatch
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
    "/*.ico",  # 匹配 /favicon.ico
    "/*.png",  # 匹配所有 .png 图标文件
    "/*.webmanifest",  # 匹配 /site.webmanifest
    "/apple-touch-icon*",  # 确保匹配 /apple-touch-icon.png
    # 登录页面
    "/login*",
    "/share*",
)

JWT_ALGORITHM = "HS256"


def is_route_unrestricted(
    route: str, patterns: tuple = unrestricted_page_routes
) -> bool:
    """
    判断给定的 route 是否匹配 patterns 中的任一通配符模式。

    Args:
        route: 要检查的字符串（如 URL 路径）。
        patterns: 包含通配符模式的元组/列表。

    Returns:
        如果匹配任一模式，返回 True；否则返回 False。
    """
    for pattern in patterns:
        # 使用 fnmatch.fnmatch 进行通配符匹配
        if fnmatch.fnmatch(route, pattern):
            return True
    return False


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
