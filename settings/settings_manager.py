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

    @property
    def language(self) -> str:
        return self._settings["language"]

    @language.setter
    def language(self, value: str):
        self._set("language", value)

    @property
    def theme(self) -> str:
        return self._settings["theme"]

    @theme.setter
    def theme(self, value: str):
        self._set("theme", value)

    @property
    def open_files(self) -> list:
        return self._settings["open_files"]

    @open_files.setter
    def open_files(self, value: list):
        self._set("open_files", value)

    @property
    def last_folder(self) -> str:
        return self._settings["last_folder"]

    @last_folder.setter
    def last_folder(self, value: str):
        self._set("last_folder", value)

    @property
    def path_depth(self) -> int:
        return self._settings["path_depth"]

    @path_depth.setter
    def path_depth(self, value: int):
        self._set("path_depth", value)


# A module is already a singleton -- no __new__ dance needed.
settings = SettingsManager()
