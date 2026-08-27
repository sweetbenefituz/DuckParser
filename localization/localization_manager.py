import json
import os
from PySide6.QtCore import QObject, Signal

LOCALIZATION_DIR = os.path.dirname(__file__)


class LocalizationManager(QObject):
    language_changed = Signal()

    def __init__(self):
        super().__init__()
        self._current_lang = "ru"
        self._translations = {}
        self._load_language(self._current_lang)

    def _load_language(self, lang: str):
        path = os.path.join(LOCALIZATION_DIR, f"{lang}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._translations = json.load(f)
        except (OSError, ValueError):
            self._translations = {}

    def set_language(self, lang: str):
        if self._current_lang != lang:
            self._current_lang = lang
            self._load_language(lang)
            self.language_changed.emit()

    def get(self, key: str):
        """Returns the translation, or the key itself when missing.

        Values are usually str, but may be a list (see "duck_facts").
        """
        return self._translations.get(key, key)


_manager = None


def get_localization() -> LocalizationManager:
    # Lazy: LocalizationManager is a QObject, so it must not be built at
    # import time -- first call happens once QApplication exists.
    global _manager
    if _manager is None:
        _manager = LocalizationManager()
    return _manager


def tr(key: str):
    return get_localization().get(key)
