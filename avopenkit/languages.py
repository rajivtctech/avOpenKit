"""Interface languages (spec section 5a, F17).

A language is offered only when its compiled translation, avopenkit_<code>.qm, is present in
the i18n folder. Translations are compiled only once reviewed (tools/update_translations.sh),
so an unreviewed language cannot appear in the list. English needs no file.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QLibraryInfo, QLocale, QTranslator

FOLDER = Path(__file__).resolve().parent / "i18n"

# The languages of spec section 5a, each named in its own script. Order is the menu order.
LANGUAGES = {
    "en": "English",
    "hi": "हिन्दी",
    "es": "Español",
    "fr": "Français",
    "bn": "বাংলা",
    "pa": "ਪੰਜਾਬੀ",
    "or": "ଓଡ଼ିଆ",
    "ta": "தமிழ்",
    "te": "తెలుగు",
    "kn": "ಕನ್ನಡ",
    "ml": "മലയാളം",
}


def qm_path(code: str, folder: Path = FOLDER) -> Path:
    return Path(folder) / f"avopenkit_{code}.qm"


def available(folder: Path = FOLDER) -> list[str]:
    """Codes that can be chosen now: English, plus every language with a compiled translation."""
    return [c for c in LANGUAGES if c == "en" or qm_path(c, folder).is_file()]


def system_code() -> str:
    return QLocale.system().name().split("_")[0].lower()


def effective(choice: str, folder: Path = FOLDER, system: str | None = None) -> str:
    """The language actually used: the saved choice, or the system language when no choice has
    been made, falling back to English when that language is not available."""
    code = choice or (system if system is not None else system_code())
    return code if code in available(folder) else "en"


def install(app, choice: str, folder: Path = FOLDER, system: str | None = None) -> str:
    """Load the translation for the effective language into the application. Returns its code."""
    code = effective(choice, folder, system)
    for old in getattr(app, "_avopenkit_translators", []):
        app.removeTranslator(old)
    loaded = []
    if code != "en":
        ours = QTranslator(app)
        if ours.load(str(qm_path(code, folder))):
            app.installTranslator(ours)
            loaded.append(ours)
        else:
            code = "en"
        # Qt's own texts (standard dialog buttons). Qt ships these for only some languages.
        qt = QTranslator(app)
        qt_folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if code != "en" and qt.load(f"qtbase_{code}", qt_folder):
            app.installTranslator(qt)
            loaded.append(qt)
    app._avopenkit_translators = loaded
    return code
