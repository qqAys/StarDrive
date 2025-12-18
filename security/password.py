import random
import string


def generate_random_password(length: int = 10) -> str:
    return "".join(
        random.choice(string.ascii_letters + string.digits) for _ in range(length)
    )
