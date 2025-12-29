import random
import string

from app.core.i18n import _


def generate_random_password(length: int = 10) -> str:
    return "".join(
        random.choice(string.ascii_letters + string.digits) for _ in range(length)
    )


def validate_password(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, _("New password must be at least 8 characters long.")
    if not any(char.isdigit() for char in password):
        return False, _("New password must contain at least one digit.")
    if not any(char.isupper() for char in password):
        return False, _("New password must contain at least one uppercase letter.")
    if not any(char.islower() for char in password):
        return False, _("New password must contain at least one lowercase letter.")
    if not any(char in string.punctuation for char in password):
        return False, _("New password must contain at least one special character.")
    return True, _("New password is valid.")
