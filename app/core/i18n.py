import gettext

from nicegui import app

from app.config import settings
from app.core.logging import logger
from app.core.paths import LOCALES_DIR

APP_DEFAULT_LANGUAGE = settings.APP_DEFAULT_LANGUAGE.replace("-", "_")

# List of supported languages loaded from the locales directory.
SUPPORTED_LANGUAGES = [item.name for item in LOCALES_DIR.iterdir() if item.is_dir()]
logger.debug(f"Supported languages: {SUPPORTED_LANGUAGES}")

# Dictionary to hold Translation objects for each supported language.
translations = {}


def load_translations(
    localedir=LOCALES_DIR, domain="messages", supported_languages=None
):
    """
    Load Translation objects for all supported languages into a dictionary.

    This function iterates over the list of supported languages and attempts to
    load the corresponding .mo translation files using Python's built-in gettext module.
    If a translation file is missing for a language, a warning is logged and a
    NullTranslations object is used as a fallback to return the original message.
    """
    if supported_languages is None:
        supported_languages = SUPPORTED_LANGUAGES
    for lang_code in supported_languages:
        try:
            # Create a Translation object for the specific language.
            t = gettext.translation(domain, localedir=localedir, languages=[lang_code])
            translations[lang_code] = t
        except FileNotFoundError:
            logger.warning(f"Translation file not found for language: {lang_code}")
            translations[lang_code] = gettext.NullTranslations()


load_translations()


def dynamic_gettext(message: str, lang_code: str = None) -> str:
    """
    Return the translated version of a message based on the specified or current user language.

    If no language code is provided, this function attempts to retrieve the user's preferred
    language from NiceGUI's user storage. If that fails (e.g., during application startup),
    it falls back to the application's default language.

    If a valid Translation object exists for the resolved language, the message is translated.
    Otherwise, the original message is returned unchanged.
    """
    if lang_code is None:
        try:
            # Retrieve the user's selected language from NiceGUI user storage.
            lang_code = app.storage.user.get("default_lang", APP_DEFAULT_LANGUAGE)
        except RuntimeError:
            # Fallback to the default language during early initialization.
            lang_code = APP_DEFAULT_LANGUAGE

    # Fetch the corresponding translator for the resolved language code.
    translator = translations.get(lang_code)

    if translator:
        # Translate the message using the loaded catalog.
        return translator.gettext(message)
    else:
        # Return the original message if no translator is available.
        return message


# Alias for convenient use throughout the application.
_ = dynamic_gettext
