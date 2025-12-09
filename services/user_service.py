from typing import Optional

from nicegui import app
from pydantic import EmailStr

from schemas.user_schema import (
    StoredUser,
    UserRegister,
    UserRead,
    UserModifyPassword,
    UserLogin,
)
from security import HashingManager, generate_random_password
from utils import logger, _

ALL_USERS_KEY = "all_users"


class UserManager:
    """
    处理 NiceGUI app.storage.general 中的用户数据。
    """

    storage = app.storage.general

    def __init__(self):

        # 用户信息存储初始化
        if ALL_USERS_KEY not in self.storage:
            self.storage[ALL_USERS_KEY] = {}

        self.users = self.storage[ALL_USERS_KEY]

        if len(self.users) == 0:
            # 初始化管理员
            initial_email = "admin@stardrive.abc"
            initial_password = generate_random_password()
            self.create(
                UserRegister(
                    username="admin", email=initial_email, password=initial_password
                ),
                bypass_exists_check=True,
            )
            self.make_superuser(initial_email)
            logger.info(
                _("Administrator account created. Email: {}, Password: {}").format(
                    initial_email, initial_password
                )
            )

    @staticmethod
    def is_login() -> bool:
        """
        检查用户是否已登录
        """
        return app.storage.user.get("authenticated", False)

    def exists(self, email: EmailStr) -> bool:
        """
        检查用户是否存在
        """
        return email in self.users

    def login(self, user_in: UserLogin) -> UserRead:
        """
        用户登录
        """
        try:
            if not HashingManager.verify_password(
                user_in.password, self.users[user_in.email]["password_hash"]
            ):
                message = _("Invalid password or email")
                logger.warning(message)
                raise ValueError(message)
        except Exception as e:
            message = _("Login failed")
            logger.error(message)
            raise ValueError(message) from e

        app.storage.user.update({"username": user_in.email, "authenticated": True})
        return self.get(user_in.email)

    def create(
        self, user_in: UserRegister, bypass_exists_check: bool = False
    ) -> StoredUser:
        """
        创建用户
        """

        if not bypass_exists_check and self.exists(user_in.email):
            message = _("User already exists")
            logger.warning(message)
            raise ValueError(message)

        # 生成 user_id
        new_user_id = len(self.users) + 1

        new_user_data = StoredUser(
            id=new_user_id,
            username=user_in.username,
            email=user_in.email,
            password_hash=HashingManager.hash_password(user_in.password),
        )

        # 存储到 app.storage.general
        self.users[new_user_data.email] = new_user_data.model_dump()
        self.storage[ALL_USERS_KEY] = self.users  # 确保存储更新

        return new_user_data

    def get(self, email: EmailStr) -> Optional[UserRead]:
        """
        获取用户信息
        """
        if not self.exists(email):
            message = _("User does not exist")
            logger.warning(message)
            raise ValueError(message)

        return UserRead(**self.users[email])

    def modify_password(self, user_in: UserModifyPassword) -> bool:
        """
        修改用户密码
        """
        if not self.exists(user_in.email):
            message = _("User does not exist")
            logger.warning(message)
            raise ValueError(message)

        self.users[user_in.email]["password_hash"] = HashingManager.hash_password(
            user_in.new_password
        )
        self.storage[ALL_USERS_KEY] = self.users  # 确保存储更新

        try:
            return HashingManager.verify_password(
                user_in.new_password, self.users[user_in.email]["password_hash"]
            )
        except Exception as e:
            message = _("Password modification failed")
            logger.error(message)
            raise ValueError(message) from e

    def active_change(self, email: EmailStr, is_active: bool) -> bool:
        """
        用户状态切换
        """
        if not self.exists(email):
            message = _("User does not exist")
            logger.warning(message)
            raise ValueError(message)

        self.users[email]["is_active"] = is_active
        self.storage[ALL_USERS_KEY] = self.users  # 确保存储更新

        return True

    def superuser_change(self, email: EmailStr, is_superuser: bool) -> bool:
        """
        超级用户权限切换
        """
        if not self.exists(email):
            message = _("User does not exist")
            logger.warning(message)
            raise ValueError(message)

        self.users[email]["is_superuser"] = is_superuser
        self.storage[ALL_USERS_KEY] = self.users  # 确保存储更新

        return True

    def disable(self, email: EmailStr) -> bool:
        """
        禁用用户
        """
        return self.active_change(email, False)

    def enable(self, email: EmailStr) -> bool:
        """
        启用用户
        """
        return self.active_change(email, True)

    def make_superuser(self, email: EmailStr) -> bool:
        """
        将用户设为超级用户
        """
        return self.superuser_change(email, True)

    def remove_superuser(self, email: EmailStr) -> bool:
        """
        取消超级用户权限
        """
        return self.superuser_change(email, False)
