import re

EMAIL_REGEX = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"


def is_valid_email(email):
    """
    判断邮箱格式是否有效
    """
    if re.fullmatch(EMAIL_REGEX, email):
        return True
    return False
