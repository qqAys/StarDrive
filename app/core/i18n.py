import gettext

from nicegui import app

from app.config import settings
from app.core.logging import logger
from app.core.paths import LOCALES_DIR

LANGUAGE_MAP = {
    # ========================
    # Chinese
    # ========================
    "zh_CN": "中文（中国）",
    "zh_TW": "中文（台灣）",
    "zh_HK": "中文（香港）",
    "zh_SG": "中文（新加坡）",
    # ========================
    # English
    # ========================
    "en_US": "English (United States)",
    "en_GB": "English (United Kingdom)",
    "en_AU": "English (Australia)",
    "en_CA": "English (Canada)",
    "en_NZ": "English (New Zealand)",
    "en_IN": "English (India)",
    # ========================
    # Japanese / Korean
    # ========================
    "ja_JP": "日本語（日本）",
    "ko_KR": "한국어（대한민국）",
    # ========================
    # French
    # ========================
    "fr_FR": "Français (France)",
    "fr_CA": "Français (Canada)",
    "fr_BE": "Français (Belgique)",
    "fr_CH": "Français (Suisse)",
    # ========================
    # German
    # ========================
    "de_DE": "Deutsch (Deutschland)",
    "de_AT": "Deutsch (Österreich)",
    "de_CH": "Deutsch (Schweiz)",
    # ========================
    # Spanish
    # ========================
    "es_ES": "Español (España)",
    "es_MX": "Español (México)",
    "es_AR": "Español (Argentina)",
    "es_CO": "Español (Colombia)",
    "es_CL": "Español (Chile)",
    "es_PE": "Español (Perú)",
    # ========================
    # Portuguese
    # ========================
    "pt_PT": "Português (Portugal)",
    "pt_BR": "Português (Brasil)",
    # ========================
    # Italian
    # ========================
    "it_IT": "Italiano (Italia)",
    # ========================
    # Dutch
    # ========================
    "nl_NL": "Nederlands (Nederland)",
    "nl_BE": "Nederlands (België)",
    # ========================
    # Nordic languages
    # ========================
    "sv_SE": "Svenska (Sverige)",
    "no_NO": "Norsk (Norge)",
    "da_DK": "Dansk (Danmark)",
    "fi_FI": "Suomi (Suomi)",
    "is_IS": "Íslenska (Ísland)",
    # ========================
    # Eastern and Central Europe
    # ========================
    "ru_RU": "Русский (Россия)",
    "uk_UA": "Українська (Україна)",
    "pl_PL": "Polski (Polska)",
    "cs_CZ": "Čeština (Česko)",
    "sk_SK": "Slovenčina (Slovensko)",
    "hu_HU": "Magyar (Magyarország)",
    "ro_RO": "Română (România)",
    "bg_BG": "Български (България)",
    # ========================
    # Balkan
    # ========================
    "hr_HR": "Hrvatski (Hrvatska)",
    "sr_RS": "Српски (Србија)",
    "sl_SI": "Slovenščina (Slovenija)",
    # ========================
    # Middle East
    # ========================
    "ar_SA": "العربية (السعودية)",
    "ar_EG": "العربية (مصر)",
    "ar_AE": "العربية (الإمارات)",
    "he_IL": "עברית (ישראל)",
    "fa_IR": "فارسی (ایران)",
    "tr_TR": "Türkçe (Türkiye)",
    # ========================
    # South Asia / Southeast Asia
    # ========================
    "hi_IN": "हिन्दी (भारत)",
    "bn_BD": "বাংলা (বাংলাদেশ)",
    "ta_IN": "தமிழ் (இந்தியா)",
    "te_IN": "తెలుగు (భారతదేశం)",
    "th_TH": "ไทย (ประเทศไทย)",
    "vi_VN": "Tiếng Việt (Việt Nam)",
    "id_ID": "Bahasa Indonesia (Indonesia)",
    "ms_MY": "Bahasa Melayu (Malaysia)",
    # ========================
    # Africa
    # ========================
    "sw_KE": "Kiswahili (Kenya)",
    "sw_TZ": "Kiswahili (Tanzania)",
    "af_ZA": "Afrikaans (South Africa)",
    # ========================
    # Other common languages
    # ========================
    "el_GR": "Ελληνικά (Ελλάδα)",
    "lt_LT": "Lietuvių (Lietuva)",
    "lv_LV": "Latviešu (Latvija)",
    "et_EE": "Eesti (Eesti)",
}


APP_DEFAULT_LANGUAGE = settings.APP_DEFAULT_LANGUAGE.replace("-", "_")

# List of supported languages loaded from the locales directory.
SUPPORTED_LANGUAGES = [item.name for item in LOCALES_DIR.iterdir() if item.is_dir()]
SUPPORTED_LANGUAGES_MAP = {
    lang_code: LANGUAGE_MAP.get(lang_code, lang_code)
    for lang_code in SUPPORTED_LANGUAGES
}
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
