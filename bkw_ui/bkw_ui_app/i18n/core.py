from __future__ import annotations

from PySide6.QtCore import QObject, QSettings, Signal

from .strings import DEFAULT_LANGUAGE, STRINGS, SUPPORTED_LANGUAGES

_SETTINGS_KEY = "ui/language"


class I18n(QObject):
    language_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._lang = DEFAULT_LANGUAGE

    def language(self) -> str:
        return self._lang

    def load_from_settings(self) -> None:
        # Read once at startup; org/app name must already be set on QCoreApplication.
        settings = QSettings()
        value = settings.value(_SETTINGS_KEY, DEFAULT_LANGUAGE)
        if isinstance(value, str) and value in SUPPORTED_LANGUAGES:
            self._lang = value
        else:
            self._lang = DEFAULT_LANGUAGE

    def set_language(self, lang: str) -> None:
        if lang not in SUPPORTED_LANGUAGES or lang == self._lang:
            return
        self._lang = lang
        QSettings().setValue(_SETTINGS_KEY, lang)
        self.language_changed.emit(lang)

    def t(self, key: str, **kwargs: object) -> str:
        s = STRINGS.get(self._lang, {}).get(key)
        if s is None:
            s = STRINGS[DEFAULT_LANGUAGE].get(key, key)
        return s.format(**kwargs) if kwargs else s


i18n = I18n()


def t(key: str, **kwargs: object) -> str:
    return i18n.t(key, **kwargs)
