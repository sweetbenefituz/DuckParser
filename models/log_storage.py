from collections import defaultdict
from dataclasses import dataclass

CRITICAL = ("ERROR", "WARNING")


@dataclass
class LogEntry:
    file: str         # имя файла (Client.log)
    line_no: int      # номер строки
    text: str         # текст строки
    level: str        # ALL / ERROR / WARNING
    hidden: bool = False  # скрыта из вкладки "Все" (пережила очистку)


class LogStorage:
    def __init__(self):
        self._logs = defaultdict(list)

    def add(self, entry: LogEntry):
        self._logs[entry.file].append(entry)

    def clear(self, file: str | None = None, level: str | None = None):
        if file is None and level in (None, "ALL"):
            self._logs.clear()
            return

        for f in ([file] if file else list(self._logs)):
            if level and level != "ALL":
                self._logs[f] = [e for e in self._logs[f] if e.level != level]
            else:
                self._logs[f].clear()

    def get(self, file: str | None, level: str) -> list[LogEntry]:
        files = list(self._logs) if file is None else [file]
        keep = (lambda e: not e.hidden) if level == "ALL" else (lambda e: e.level == level)
        return [e for f in files for e in self._logs.get(f, []) if keep(e)]

    def find_entry_in_all(self, entry: LogEntry) -> int | None:
        entries = self.get(None, "ALL")
        return entries.index(entry) if entry in entries else None

    def clear_non_critical(self, file: str | None = None):
        """Drop everything but errors/warnings; survivors leave the ALL view."""
        for f in ([file] if file else list(self._logs)):
            kept = [e for e in self._logs[f] if e.level in CRITICAL]
            for e in kept:
                e.hidden = True
            self._logs[f] = kept
