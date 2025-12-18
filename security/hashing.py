import bcrypt


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
