import secrets

ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_access_code(length: int = 6) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))
