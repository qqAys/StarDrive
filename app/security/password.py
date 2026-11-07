import os
import string
from collections.abc import Iterator
from contextlib import contextmanager
from random import SystemRandom

from app.core.i18n import _


def generate_random_password(length: int = 10) -> str:
    random = SystemRandom()
    length = max(length, 8)
    required = [
        random.choice(string.ascii_lowercase),
        random.choice(string.ascii_uppercase),
        random.choice(string.digits),
        random.choice(string.punctuation),
    ]
    remaining = [
        random.choice(string.ascii_letters + string.digits + string.punctuation)
        for _ in range(length - len(required))
    ]
    chars = required + remaining
    random.shuffle(chars)
    return "".join(chars)


def validate_password(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, _("New password must be at least 8 characters long.")
    if len(password.encode("utf-8")) > 72:
        return False, _("New password must not exceed 72 UTF-8 bytes.")
    if not any(char.isdigit() for char in password):
        return False, _("New password must contain at least one digit.")
    if not any(char.isupper() for char in password):
        return False, _("New password must contain at least one uppercase letter.")
    if not any(char.islower() for char in password):
        return False, _("New password must contain at least one lowercase letter.")
    if not any(char in string.punctuation for char in password):
        return False, _("New password must contain at least one special character.")
    return True, _("New password is valid.")


@contextmanager
def open_password_terminal() -> Iterator[int]:
    """Open a console device without creating or truncating a file."""
    device = "CONOUT$" if os.name == "nt" else "/dev/tty"
    descriptor = os.open(device, os.O_WRONLY | getattr(os, "O_NOCTTY", 0))
    try:
        if not os.isatty(descriptor):
            raise OSError("The credential output requires an interactive terminal.")
        yield descriptor
    finally:
        os.close(descriptor)


def show_initial_password(terminal: int, email: str, password: str) -> None:
    if not os.isatty(terminal):
        raise OSError("The credential output requires an interactive terminal.")
    message = _(
        "Initial administrator: {email}. Temporary password: {password}"
    ).format(email=email, password=password)
    pending = memoryview((message + "\n").encode("utf-8"))
    while pending:
        written = os.write(terminal, pending)
        if not written:
            raise OSError("Unable to write to the credential terminal.")
        pending = pending[written:]
