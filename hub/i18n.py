from __future__ import annotations

from typing import Dict

SUPPORTED_LANGUAGES = ("cs", "en")

_TEXTS: Dict[str, Dict[str, str]] = {
    "cs": {
        "header_title": "BrainHub",
        "header_subtitle": "Logické hry",
        "language_label": "Jazyk",
        "language_cs": "Čeština",
        "language_en": "English",
        "back": "Zpět",
        "play_hint": "▶ Hrát",
        "dialog_title": "GameHub",
        "no_plugins": "Nenašel jsem žádné pluginy ve složce games/.",
        "plugin_reload_failed": "Nepodařilo se načíst pluginy her. Podrobnosti jsou v logu.",
        "last_runs_io_failed": (
            "Nepodařilo se načíst nebo uložit historii posledních spuštění. "
            "Řazení her podle posledního spuštění nemusí fungovat."
        ),
        "settings_io_failed": (
            "Nepodařilo se načíst nebo uložit nastavení aplikace. "
            "Jazykové nastavení nemusí být zachováno."
        ),
        "plugin_open_failed": "Hru '{name}' se nepodařilo otevřít. Podrobnosti jsou v logu.",
        "plugin_widget_crash": "Plugin spadl při vytváření widgetu:\n{error}",
    },
    "en": {
        "header_title": "BrainHub",
        "header_subtitle": "Logic Games",
        "language_label": "Language",
        "language_cs": "Čeština",
        "language_en": "English",
        "back": "Back",
        "play_hint": "▶ Play",
        "dialog_title": "GameHub",
        "no_plugins": "No plugins were found in the games/ directory.",
        "plugin_reload_failed": "Failed to load game plugins. See logs for details.",
        "last_runs_io_failed": (
            "Failed to read or store last-run history. "
            "Sorting by recently played games may not work."
        ),
        "settings_io_failed": (
            "Failed to read or store app settings. "
            "Language preference might not persist."
        ),
        "plugin_open_failed": "Failed to open game '{name}'. See logs for details.",
        "plugin_widget_crash": "Plugin crashed while creating widget:\n{error}",
    },
}


def normalize_language(language: str | None) -> str:
    if not language:
        return "cs"
    token = language.lower().replace("_", "-").strip()
    if token in SUPPORTED_LANGUAGES:
        return token
    short = token.split("-", 1)[0]
    if short in SUPPORTED_LANGUAGES:
        return short
    return "cs"


def tr(language: str, key: str, **kwargs: object) -> str:
    lang = normalize_language(language)
    text = _TEXTS.get(lang, {}).get(key)
    if text is None:
        text = _TEXTS["cs"].get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text
