import re

EMAIL_REGEX = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"


def is_valid_email(email: str) -> bool:
    """
    Validate the format of an email address.

    Args:
        email: The email string to validate.

    Returns:
        True if the email matches the standard format; False otherwise.
    """
    return bool(re.fullmatch(EMAIL_REGEX, email))
