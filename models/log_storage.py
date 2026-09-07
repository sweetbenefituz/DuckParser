from collections import defaultdict
from dataclasses import dataclass

CRITICAL = ("ERROR", "WARNING")

# Trim in batches: dropping one head element per appended line is O(n) every
# line, and a busy log appends thousands per second.
# ponytail: fixed slack; make it proportional only if trimming ever shows up in a profile.
TRIM_SLACK = 1000


@dataclass
class LogEntry:
    file: str         # tab label the line belongs to (Client.log)
    line_no: int      # 1-based line number in the source file
    text: str         # the raw line
    level: str        # ALL / ERROR / WARNING
    hidden: bool = False  # survived a clear, so it stays out of the ALL view


class LogStorage:
    def __init__(self, max_lines: int = 0):
        self._logs = defaultdict(list)
        self.max_lines = max_lines  # 0 = keep everything

    def add(self, entry: LogEntry):
        lines = self._logs[entry.file]
        lines.append(entry)

        if self.max_lines and len(lines) > self.max_lines + TRIM_SLACK:
            del lines[:len(lines) - self.max_lines]

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

    def all_entries(self, file: str | None = None) -> list[LogEntry]:
        """Every stored line, hidden ones included -- one pass for the tab counters."""
        files = list(self._logs) if file is None else [file]
        return [e for f in files for e in self._logs.get(f, [])]

    def clear_non_critical(self, file: str | None = None):
        """Drop everything but errors/warnings; survivors leave the ALL view."""
        for f in ([file] if file else list(self._logs)):
            kept = [e for e in self._logs[f] if e.level in CRITICAL]
            for e in kept:
                e.hidden = True
            self._logs[f] = kept
