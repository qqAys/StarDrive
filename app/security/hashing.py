import bcrypt


class HashingManager:
    """
    Utility class for secure password hashing and verification using bcrypt.
    """

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a plain-text password using bcrypt with a randomly generated salt.

        Args:
            password: The plain-text password to hash.

        Returns:
            A bcrypt hash string (UTF-8 encoded).
        """
        salt = bcrypt.gensalt()
        password_bytes = password.encode("utf-8")
        hashed_password = bcrypt.hashpw(password_bytes, salt)
        return hashed_password.decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify that a plain-text password matches the stored bcrypt hash.

        Args:
            plain_password: The user-provided plain-text password.
            hashed_password: The stored bcrypt hash string.

        Returns:
            True if the password matches; False otherwise.
        """
        password_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)
