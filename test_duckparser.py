"""Self-check for the non-trivial bits: level detection, storage filtering,
theme templating, and the block accounting the "go to line" feature relies on.

Run: python test_duckparser.py
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from models.log_storage import LogStorage, LogEntry
from parser.log_parser import detect_level
from ui.main_window import load_palette, build_stylesheet, format_tab_path


def test_detect_level():
    assert detect_level("everything is fine") == "ALL"
    assert detect_level("ERROR: disk missing") == "ERROR"
    assert detect_level("connection failed") == "ERROR"
    assert detect_level("WARNING: temperature high") == "WARNING"
    # Whichever keyword appears first wins.
    assert detect_level("WARNING: connect failed") == "WARNING"
    assert detect_level("ERROR raised after warning") == "ERROR"


def test_storage_filtering():
    s = LogStorage()
    s.add(LogEntry("a.log", 1, "boot", "ALL"))
    err = LogEntry("a.log", 2, "ERROR disk", "ERROR")
    s.add(err)
    s.add(LogEntry("b.log", 1, "WARNING heat", "WARNING"))

    assert len(s.get(None, "ALL")) == 3
    assert len(s.get("a.log", "ALL")) == 2
    assert len(s.get(None, "ERROR")) == 1
    assert s.find_entry_in_all(err) == 1

    # Clearing the ALL view keeps errors/warnings in their own tabs.
    s.clear_non_critical()
    assert s.get(None, "ALL") == []
    assert len(s.get(None, "ERROR")) == 1
    assert len(s.get(None, "WARNING")) == 1
    assert s.find_entry_in_all(err) is None

    s.clear(None, "ERROR")
    assert s.get(None, "ERROR") == []
    assert len(s.get(None, "WARNING")) == 1

    s.clear()
    assert s.get(None, "WARNING") == []


def test_storage_clear_scopes():
    s = LogStorage()
    s.add(LogEntry("a.log", 1, "x", "ALL"))
    s.add(LogEntry("b.log", 1, "y", "ALL"))

    s.clear("a.log")
    assert len(s.get(None, "ALL")) == 1
    assert s.get("a.log", "ALL") == []


def test_every_palette_fills_the_template():
    for theme in ("dark", "light"):
        qss = build_stylesheet(load_palette(theme))  # KeyError here means a missing color
        assert "$" not in qss, f"unsubstituted placeholder left in {theme}"
        assert "#LogView" in qss

    # Unknown theme falls back instead of crashing.
    assert load_palette("nope") == load_palette("dark")


def test_settings_lives_in_the_user_config_dir():
    """Settings must never land next to the exe -- a onefile build run from the
    desktop would litter the desktop with settings.json."""
    import settings.settings_manager as sm

    d = sm._settings_dir()
    assert d.endswith("DuckParser")
    assert os.path.dirname(sm.SETTINGS_FILE) == d
    assert not sm.SETTINGS_FILE.startswith(os.path.dirname(os.path.dirname(sm.__file__)) + os.sep)


def test_close_icon_is_reachable_from_the_stylesheet():
    """A QSS url() pointing nowhere fails silently and leaves a blank square
    where the X should be -- which is exactly how this broke once already."""
    import re
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPixmap

    QApplication.instance() or QApplication([])

    for theme in ("dark", "light"):
        qss = build_stylesheet(load_palette(theme))
        match = re.search(r"close-button\s*\{[^}]*image:\s*url\(([^)]+)\)", qss)
        assert match, f"{theme}: close-button has no image rule"

        path = match.group(1).strip()
        assert os.path.isabs(path), f"relative url() breaks in a frozen exe: {path}"
        assert os.path.exists(path), f"{theme}: missing icon file {path}"

        pixmap = QPixmap(path)
        assert not pixmap.isNull(), f"{theme}: Qt cannot decode {path}"
        assert pixmap.width() >= 16, f"{theme}: icon too small to scale cleanly"


def test_spec_bundles_every_runtime_data_file():
    """Files the app opens at runtime must be listed in the spec, or the exe
    starts up into a traceback."""
    spec = open("DuckParser.spec", encoding="utf-8").read()
    for needed in ("themes/base.qss", "themes/palettes.json",
                   "localization/ru.json", "localization/en.json",
                   "localization/ua.json", "ico/48x48.jpg", "ico/85x85.jpg",
                   "ico/close.png"):
        assert needed in spec, f"{needed} missing from DuckParser.spec datas"


def test_format_tab_path():
    sep = os.sep
    path = sep.join(["C:", "work", "Duckside", "Builds", "Logs", "duckside.log"])

    assert format_tab_path(path, 0) == path
    assert format_tab_path(path, 3) == sep.join(["...", "Duckside", "Builds", "Logs", "duckside.log"])
    # Asking for more folders than there are shows the whole path, no leading "...".
    assert format_tab_path(path, 9) == path


def test_same_named_logs_get_their_own_tabs():
    """Two builds writing duckside.log must not collapse into one tab."""
    import tempfile
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as root:
        paths = []
        for build in ("build_a", "build_b"):
            folder = os.path.join(root, build)
            os.makedirs(folder)
            path = os.path.join(folder, "duckside.log")
            open(path, "w", encoding="utf-8").write("boot\n")
            paths.append(path)

        window = MainWindow()
        try:
            for path in paths:
                window._open_file_by_path(path)

            tabs = window.tabs.file_tabs
            assert tabs.count() == 3, "expected the All tab plus one tab per file"
            assert tabs.tabText(1) == "duckside.log"
            assert tabs.tabText(2) == "duckside.log (1)"
            assert tabs.tabToolTip(2).endswith(os.path.join("build_b", "duckside.log"))

            # Each tab keeps its own log lines.
            assert len(window.storage.get("duckside.log", "ALL")) == 1
            assert len(window.storage.get("duckside.log (1)", "ALL")) == 1

            # The same path twice just focuses the tab it already has.
            window._open_file_by_path(paths[0])
            assert tabs.count() == 3
            assert tabs.currentIndex() == 1
        finally:
            window.stop_workers()


def _make_rows(n=6):
    from PySide6.QtGui import QColor

    entries = [LogEntry("a.log", i, f"line {i}", "ALL") for i in range(n)]
    colors = [QColor("#151515") if i % 2 == 0 else QColor("#222222") for i in range(n)]
    return entries, [(e.text, c) for e, c in zip(entries, colors)]


def test_append_row_matches_full_rebuild():
    """One row must equal one text block, or 'go to line in ALL' jumps wrong."""
    from PySide6.QtWidgets import QApplication
    from ui.log_view import LogView

    QApplication.instance() or QApplication([])
    entries, rows = _make_rows()

    rebuilt = LogView()
    rebuilt.set_rows(rows, entries)

    appended = LogView()
    for (text, background), entry in zip(rows, entries):
        appended.append_row(text, background, entry)

    assert appended.document().blockCount() == rebuilt.document().blockCount() == len(entries)
    assert appended.row_count() == len(entries)

    for i, entry in enumerate(entries):
        block = appended.document().findBlockByNumber(i)
        assert block.text() == entry.text, f"block {i}: {block.text()!r}"
        assert appended.get_entry_at_line(i) is entry
        assert block.blockFormat().background().color() == rows[i][1]

    # An empty view (e.g. the WARNING tab before any warning arrives) still has
    # one empty block. Appending into it must reuse that block, not add a second.
    empty = LogView()
    empty.set_rows([], [])
    assert empty.row_count() == 0
    empty.append_row(*rows[0], entries[0])
    assert empty.document().blockCount() == 1
    assert empty.get_entry_at_line(0) is entries[0]
    assert empty.document().findBlockByNumber(0).text() == entries[0].text


def test_row_background_spans_full_window_width():
    """The reported bug: live-appended rows only painted behind the glyphs,
    while tab-switching (full rebuild) painted the whole line."""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QColor, QImage

    from ui.log_view import LogView

    QApplication.instance() or QApplication([])

    error_bg = QColor(180, 60, 60, 150)
    entry = LogEntry("a.log", 1, "short line", "ERROR")
    row = ("short line", error_bg)

    def render_first_row(view):
        view.resize(600, 200)
        view.show()
        layout = view.document().documentLayout()
        rect = layout.blockBoundingRect(view.document().findBlockByNumber(0))
        image = QImage(view.viewport().size(), QImage.Format_ARGB32)
        image.fill(QColor("#151515"))
        view.viewport().render(image)
        y = int(rect.center().y()) - view.verticalScrollBar().value()
        # x well past the end of "short line", still inside the viewport
        return image.pixelColor(view.viewport().width() - 12, y)

    appended = LogView()
    appended.append_row(*row, entry)
    far_right_appended = render_first_row(appended)

    rebuilt = LogView()
    rebuilt.set_rows([row], [entry])
    far_right_rebuilt = render_first_row(rebuilt)

    plain = LogView()
    plain.set_rows([("short line", QColor("#151515"))], [entry])
    far_right_plain = render_first_row(plain)

    assert far_right_appended == far_right_rebuilt, (
        f"append and rebuild disagree: {far_right_appended.name()} "
        f"vs {far_right_rebuilt.name()}"
    )
    assert far_right_appended.red() > far_right_appended.blue(), (
        f"error tint missing at the right edge: {far_right_appended.name()}"
    )
    assert far_right_appended != far_right_plain, "error row not distinguishable from a plain row"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all good")
