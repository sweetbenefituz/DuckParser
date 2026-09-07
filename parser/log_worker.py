import os

from PySide6.QtCore import QThread, Signal
from models.log_storage import LogEntry
from parser.log_parser import detect_level
from settings.settings_manager import settings


class LogWorker(QThread):
    new_entry = Signal(LogEntry)

    def __init__(self, path: str, file_name: str):
        super().__init__()
        self.path = path
        self.file_name = file_name
        self._running = True

    def _open(self):
        return open(self.path, "r", encoding="utf-8", errors="ignore")

    def run(self):
        try:
            f = self._open()
            # Counting to EOF also leaves the handle there, so tailing
            # starts right after the last existing line.
            line_no = sum(1 for _ in f)

            while self._running:
                where = f.tell()
                line = f.readline()

                if line:
                    line_no += 1
                    self._emit_line(line_no, line)
                    continue

                if os.path.getsize(self.path) < where:
                    # A new build run recreated the log. Without this the handle
                    # sits past the new end of file and nothing ever shows up.
                    f.close()
                    f = self._open()
                    line_no = 0
                    continue

                self.msleep(200)
                f.seek(where)

            f.close()

        except OSError as e:
            self.new_entry.emit(LogEntry(
                file=self.file_name,
                line_no=0,
                text=f"Parser error: {e}",
                level="ERROR"
            ))

    def _emit_line(self, line_no: int, line: str):
        line = line.rstrip("\n")

        self.new_entry.emit(LogEntry(
            file=self.file_name,
            line_no=line_no,
            text=line,
            level=detect_level(line, settings.error_words, settings.warning_words)
        ))

    def stop(self):
        self._running = False
