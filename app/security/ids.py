import ulid


def generate_ulid() -> str:
    return str(ulid.new())
