import gettext
from logging import getLogger, StreamHandler

lang = gettext.translation("messages", localedir="locales", languages=["en_US"])
lang.install()
_ = lang.gettext

logger = getLogger("stardrive")
logger.setLevel("DEBUG")
logger.addHandler(StreamHandler())


def bytes_to_human_readable(num_bytes: int) -> str:
    """
    将字节数转换为人类可读的字符串。
    """
    for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} YB"
