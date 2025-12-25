def bytes_to_human_readable(num_bytes: int) -> str:
    """
    Convert a number of bytes into a human-readable string representation.

    The function converts the given number of bytes into the most appropriate
    unit (from bytes up to yottabytes), providing a readable format with two
    decimal places precision.
    """
    for unit in ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} YB"
