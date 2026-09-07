import json
import os


def _settings_dir() -> str:
    # Per-user config dir, so the file never lands next to the exe (a onefile
    # build on the desktop would otherwise litter the desktop).
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    return os.path.join(base, "DuckParser")


SETTINGS_FILE = os.path.join(_settings_dir(), "settings.json")

DEFAULTS = {
    "language": "ru",
    "theme": "dark",
    "open_files": [],
    "last_folder": "",
    # Tab tooltip: 0 shows the whole path, N shows the last N folders.
    "path_depth": 3,
    # Most recently opened paths, newest first (File -> Recent files).
    "recent_files": [],
    # Words that decide a line's level, lowercase. Editable from the menu:
    # Unreal also says "Fatal" and "Assertion failed", Unity says "Exception".
    "error_words": ["error", "fail", "fatal", "exception", "assert"],
    "warning_words": ["warning", "warn"],
    # Lines kept per file before the oldest are dropped. 0 = unlimited.
    "max_lines": 200000,
}


class SettingsManager:
    """Plain dict-backed settings, written through on every change."""

    def __init__(self):
        self._settings = dict(DEFAULTS)
        self._load()

    def _load(self):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                self._settings.update(json.load(f))
        except (OSError, ValueError):
            pass  # missing or corrupt file: defaults stand

    def save(self):
        try:
            os.makedirs(_settings_dir(), exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _set(self, key: str, value):
        self._settings[key] = value
        self.save()


def _bind(key: str):
    """One read/write property per DEFAULTS key -- beats 80 lines of identical
    getter/setter pairs, and a new setting is now one line in DEFAULTS."""
    return property(
        lambda self: self._settings[key],
        lambda self, value: self._set(key, value),
    )


for _key in DEFAULTS:
    setattr(SettingsManager, _key, _bind(_key))


# A module is already a singleton -- no __new__ dance needed.
settings = SettingsManager()
