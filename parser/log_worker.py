from PySide6.QtCore import QThread, Signal
from models.log_storage import LogEntry
from parser.log_parser import detect_level


class LogWorker(QThread):
    new_entry = Signal(LogEntry)

    def __init__(self, path: str, file_name: str):
        super().__init__()
        self.path = path
        self.file_name = file_name
        self._running = True

    def run(self):
        try:
            with open(self.path, "r", encoding="utf-8", errors="ignore") as f:
                # Counting to EOF also leaves the handle there, so tailing
                # starts right after the last existing line.
                line_no = sum(1 for _ in f)

                while self._running:
                    where = f.tell()
                    line = f.readline()

                    if not line:
                        self.msleep(200)
                        f.seek(where)
                    else:
                        line_no += 1
                        self._emit_line(line_no, line)

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
            level=detect_level(line)
        ))

    def stop(self):
        self._running = False
