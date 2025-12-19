import gettext

from nicegui import app

from app.core.logging import logger
from app.core.paths import LOCALES_DIR

# 支持的语言列表
# 从 locales 目录下加载
SUPPORTED_LANGUAGES = [item.name for item in LOCALES_DIR.iterdir() if item.is_dir()]
logger.debug(f"Supported languages: {SUPPORTED_LANGUAGES}")

# 存储所有语言的 Translation 对象
translations = {}


def load_translations(
    localedir=LOCALES_DIR, domain="messages", supported_languages=None
):
    """
    加载所有支持语言的 Translation 对象到字典中。
    """
    if supported_languages is None:
        supported_languages = SUPPORTED_LANGUAGES
    for lang_code in supported_languages:
        try:
            # 创建特定语言的 Translation 对象
            t = gettext.translation(domain, localedir=localedir, languages=[lang_code])
            translations[lang_code] = t
        except FileNotFoundError:
            logger.warning(f"Translation file not found for language: {lang_code}")
            translations[lang_code] = gettext.NullTranslations()


load_translations()


def dynamic_gettext(message: str, lang_code: str = None) -> str:
    """
    根据给定的语言代码返回翻译后的消息。
    """
    if lang_code is None:
        try:
            # 尝试从 NiceGUI 用户存储中获取
            lang_code = app.storage.user.get("default_lang", "en_US")
        except RuntimeError:
            # 如在初始化时，使用默认语言
            lang_code = "en_US"
    # 查找对应的 Translation 对象
    translator = translations.get(lang_code)

    if translator:
        # 使用该对象的 gettext 方法进行翻译
        return translator.gettext(message)
    else:
        return message


_ = dynamic_gettext
