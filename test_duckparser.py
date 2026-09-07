"""Self-check for the non-trivial bits: level detection, storage filtering,
theme templating, and the block accounting the "go to line" feature relies on.

Run: python test_duckparser.py
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from models.log_storage import LogStorage, LogEntry
from parser.log_parser import detect_level
from settings.settings_manager import settings
from ui.main_window import load_palette, build_stylesheet, format_tab_path

# Tests drive the real settings singleton; writing through would overwrite the
# user's own settings.json.
settings.save = lambda: None


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

    # Clearing the ALL view keeps errors/warnings in their own tabs.
    s.clear_non_critical()
    assert s.get(None, "ALL") == []
    assert len(s.get(None, "ERROR")) == 1
    assert len(s.get(None, "WARNING")) == 1

    s.clear(None, "ERROR")
    assert s.get(None, "ERROR") == []
    assert len(s.get(None, "WARNING")) == 1

    s.clear()
    assert s.get(None, "WARNING") == []


def test_storage_line_limit():
    """A long-running build must not grow the storage until the app dies."""
    s = LogStorage(max_lines=100)
    for i in range(5000):
        s.add(LogEntry("a.log", i, f"line {i}", "ALL"))

    kept = s.all_entries()
    assert 100 <= len(kept) <= 100 + 1000, len(kept)
    assert kept[-1].line_no == 4999, "the newest line must survive"

    unlimited = LogStorage()
    for i in range(2000):
        unlimited.add(LogEntry("a.log", i, "x", "ALL"))
    assert len(unlimited.all_entries()) == 2000


def test_custom_keywords():
    """Unreal says "Fatal", Unity says "Exception" -- both must be colourable
    without touching the code."""
    assert detect_level("Fatal error in module") == "ERROR"  # "error" alone catches this one
    assert detect_level("Assertion tripped") == "ALL", "default words must stay narrow"
    assert detect_level("Assertion tripped", error_words=["assertion"]) == "ERROR"
    assert detect_level("Deprecated call", warning_words=["deprecated"]) == "WARNING"
    # Empty lists mean nothing is coloured, not a crash.
    assert detect_level("ERROR everywhere", error_words=[], warning_words=[]) == "ALL"


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
    path = sep.join(["C:", "work", "MyGame", "Builds", "Logs", "output.log"])

    assert format_tab_path(path, 0) == path
    assert format_tab_path(path, 3) == sep.join(["...", "MyGame", "Builds", "Logs", "output.log"])
    # Asking for more folders than there are shows the whole path, no leading "...".
    assert format_tab_path(path, 9) == path


def test_same_named_logs_get_their_own_tabs():
    """Two builds writing output.log must not collapse into one tab."""
    import tempfile
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as root:
        paths = []
        for build in ("build_a", "build_b"):
            folder = os.path.join(root, build)
            os.makedirs(folder)
            path = os.path.join(folder, "output.log")
            open(path, "w", encoding="utf-8").write("boot\n")
            paths.append(path)

        window = MainWindow()
        try:
            for path in paths:
                window._open_file_by_path(path)

            tabs = window.tabs.file_tabs
            assert tabs.count() == 3, "expected the All tab plus one tab per file"
            assert tabs.tabText(1) == "output.log"
            assert tabs.tabText(2) == "output.log (1)"
            assert tabs.tabToolTip(2).endswith(os.path.join("build_b", "output.log"))

            # Each tab keeps its own log lines.
            assert len(window.storage.get("output.log", "ALL")) == 1
            assert len(window.storage.get("output.log (1)", "ALL")) == 1

            # The same path twice just focuses the tab it already has.
            window._open_file_by_path(paths[0])
            assert tabs.count() == 3
            assert tabs.currentIndex() == 1
        finally:
            window.stop_workers()


def _window_with_file(root, lines):
    """A MainWindow with one file open, no tail thread running."""
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    QApplication.instance() or QApplication([])

    path = os.path.join(root, "output.log")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(line + "\n" for line in lines))

    window = MainWindow()
    window._open_file_by_path(path)
    return window, path


def test_load_whole_file_shows_what_is_already_there():
    """The reported bug: opening a finished build log showed an empty tab,
    because tailing starts at the end of the file."""
    import tempfile

    with tempfile.TemporaryDirectory() as root:
        window, _ = _window_with_file(root, [
            "boot ok", "ERROR disk missing", "WARNING low memory", "done",
        ])
        try:
            # Tailing alone sees nothing but the synthetic "log opened" line.
            assert len(window.storage.get("output.log", "ERROR")) == 0

            window.current_file = "output.log"
            window._load_full_files()

            assert len(window.storage.get("output.log", "ERROR")) == 1
            assert len(window.storage.get("output.log", "WARNING")) == 1
            assert len(window.storage.get("output.log", "ALL")) == 4
            assert window.storage.get("output.log", "ERROR")[0].line_no == 2
            # Reloading must leave a live tail behind, not a dead tab.
            assert window.workers_by_file["output.log"].isRunning()
        finally:
            window.stop_workers()


def test_text_filter_and_tab_counters():
    import tempfile

    with tempfile.TemporaryDirectory() as root:
        window, _ = _window_with_file(root, [
            "loading Inventory", "ERROR Inventory broken", "ERROR Audio broken",
        ])
        try:
            window.current_file = "output.log"
            window._load_full_files()

            window.tabs.filter_input.setText("inventory")
            window._apply_text_filter()

            assert [e.text for e in window._visible_entries("ALL")] == [
                "loading Inventory", "ERROR Inventory broken",
            ]
            assert len(window._visible_entries("ERROR")) == 1

            window._update_status()
            assert window.tabs.filter_tabs.tabText(1).endswith("(1)"), \
                window.tabs.filter_tabs.tabText(1)
            # "All" carries no count: it would just repeat the status bar.
            assert "(" not in window.tabs.filter_tabs.tabText(0), \
                window.tabs.filter_tabs.tabText(0)

            window.tabs.filter_input.setText("")
            window._apply_text_filter()
            window._update_status()
            assert window.tabs.filter_tabs.tabText(1).endswith("(2)")
        finally:
            window.stop_workers()


def test_recent_files_are_deduped_and_capped():
    from ui.main_window import MainWindow, RECENT_FILES_MAX
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    saved = list(settings.recent_files)
    try:
        settings.recent_files = []
        window = MainWindow()

        for i in range(RECENT_FILES_MAX + 5):
            window._push_recent(f"C:\\logs\\file{i}.log")
        assert len(settings.recent_files) == RECENT_FILES_MAX
        assert settings.recent_files[0].endswith("file14.log"), "newest goes first"

        # Re-opening a file moves it up instead of adding a duplicate.
        window._push_recent(settings.recent_files[3])
        assert len(settings.recent_files) == RECENT_FILES_MAX
        assert len(set(settings.recent_files)) == RECENT_FILES_MAX
    finally:
        settings.recent_files = saved


def test_worker_survives_the_log_being_recreated():
    """A new build run truncates the log. The old code kept waiting past the
    old end of file and never showed another line."""
    import tempfile
    import time
    from PySide6.QtWidgets import QApplication
    from parser.log_worker import LogWorker

    app = QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "output.log")
        with open(path, "w", encoding="utf-8") as f:
            f.write("old run line\n")

        seen = []
        worker = LogWorker(path, "output.log")
        worker.new_entry.connect(lambda e: seen.append(e.text))
        worker.start()
        time.sleep(0.5)  # let the thread reach the tail loop before writing

        def wait_for(text, seconds=10):
            deadline = time.time() + seconds
            while time.time() < deadline:
                app.processEvents()
                if any(text in s for s in seen):
                    return True
                time.sleep(0.05)
            return False

        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write("tailed line\n")
            assert wait_for("tailed line"), seen

            # A new run starts the log over from scratch.
            with open(path, "w", encoding="utf-8") as f:
                f.write("fresh run line\n")
            assert wait_for("fresh run line"), seen
        finally:
            worker.stop()
            worker.wait(2000)


def test_refilled_view_is_fully_painted():
    """The reported bug: after Clear tab, Load whole file refilled the storage
    but the viewport kept showing the emptied document until a tab switch.

    The half-painted viewport itself only reproduces on a real desktop, not
    under the offscreen platform this suite runs on, so what is guarded here is
    the state around it: content, and a cleared view going back to following
    the newest line."""
    import tempfile
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QImage, QColor

    QApplication.instance() or QApplication([])

    def ink(view):
        image = QImage(view.viewport().size(), QImage.Format_ARGB32)
        image.fill(QColor("#000000"))
        view.viewport().render(image)
        background = image.pixelColor(5, 5).rgb()
        return sum(
            1
            for y in range(0, image.height(), 4)
            for x in range(0, image.width(), 4)
            if image.pixelColor(x, y).rgb() != background
        )

    with tempfile.TemporaryDirectory() as root:
        window, _ = _window_with_file(root, [f"LogTemp: tick {i}" for i in range(300)])
        try:
            window.resize(900, 600)
            window.show()
            window.current_file = "output.log"

            window._load_full_files()
            window._clear_current_view()
            assert window.log_view.row_count() == 0
            assert ink(window.log_view) == 0, "a cleared view must be blank"

            window._load_full_files()
            painted = ink(window.log_view)

            window.log_view.repaint()
            complete = ink(window.log_view)

            assert painted > 0, "nothing was painted after the reload"
            assert painted >= complete * 0.9, (
                f"only part of the view was painted: {painted} of {complete}"
            )
            # An emptied view starts following the newest line again.
            bar = window.log_view.verticalScrollBar()
            assert bar.value() == bar.maximum()
        finally:
            window.stop_workers()


def test_search_counts_and_steps_through_hits():
    import tempfile
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as root:
        window, _ = _window_with_file(root, [
            "boot Alpha", "load ALPHA", "run alpha", "done Beta",
        ])
        try:
            window.current_file = "output.log"
            window._load_full_files()

            view = window.log_view
            view._show_search()
            dialog = view.search_dialog

            dialog.input.setText("alpha")
            dialog._rescan()
            assert len(dialog._matches) == 3, "case-insensitive by default"

            dialog.case_box.setChecked(True)
            dialog._rescan()
            assert len(dialog._matches) == 1, "Match case must narrow it down"
            dialog.case_box.setChecked(False)
            dialog._rescan()

            # Stepping forward walks the hits in order and wraps around.
            seen = []
            for _ in range(4):
                dialog.find()
                seen.append(view.textCursor().selectionStart())
            assert seen[:3] == sorted(seen[:3]), seen
            assert seen[3] == seen[0], "the last hit must wrap back to the first"

            # And backwards steps the other way.
            dialog.find(backward=True)
            assert view.textCursor().selectionStart() == seen[2]

            assert "3" in dialog.count_label.text(), dialog.count_label.text()

            # The button and Enter both obey the "Search backwards" box, and
            # nothing else. clicked() used to hand find() its own checked flag,
            # which forced forward; Enter fired both that and returnPressed,
            # so it stepped twice forward -- or, with the box on, cancelled
            # itself out and looked dead.
            from PySide6.QtCore import Qt
            from PySide6.QtTest import QTest

            def step(backward, use_enter):
                dialog.backward_box.setChecked(backward)
                before = view.textCursor().selectionStart()
                if use_enter:
                    QTest.keyClick(dialog.input, Qt.Key_Return)
                else:
                    dialog.find_btn.click()
                return before, view.textCursor().selectionStart()

            starts = sorted(start for start, _ in dialog._matches)
            for use_enter in (False, True):
                how = "Enter" if use_enter else "the button"
                before, after = step(backward=False, use_enter=use_enter)
                expected = next((s for s in starts if s > before), starts[0])
                assert after == expected, f"{how} forward: {before} -> {after}"

                before, after = step(backward=True, use_enter=use_enter)
                expected = next((s for s in reversed(starts) if s < before), starts[-1])
                assert after == expected, f"{how} backwards: {before} -> {after}"

            dialog.backward_box.setChecked(False)

            dialog.input.setText("nothing like this")
            dialog._rescan()
            assert dialog._matches == []
            assert dialog.count_label.text() == tr_or_key("search_none")

            dialog.close()
            assert view.extraSelections() == [], "closing must clear the highlights"
        finally:
            window.stop_workers()


def test_a_fresh_search_ignores_where_the_caret_was_left():
    """The reported bug: click somewhere in the middle of the log, then search,
    and it reported "180 / 300" -- the hunt started at the stray click."""
    import tempfile
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QTextCursor

    QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as root:
        window, _ = _window_with_file(root, [f"line {i} target" for i in range(30)])
        try:
            window.current_file = "output.log"
            window._load_full_files()

            view = window.log_view
            view.setTextCursor(QTextCursor(view.document().findBlockByNumber(20)))

            view._show_search()
            dialog = view.search_dialog
            dialog.input.setText("target")
            dialog._rescan()

            dialog.find()
            assert view.textCursor().blockNumber() == 0, "a new word starts at the top"

            dialog.find()
            assert view.textCursor().blockNumber() == 1, "then it steps on from there"

            # Clicking in the log mid-search changes nothing: the search keeps
            # its own count and carries on from the hit it was standing on.
            view.setTextCursor(QTextCursor(view.document().findBlockByNumber(25)))
            dialog.find()
            assert view.textCursor().blockNumber() == 2, "a click must not move the search"

            # Another word starts over at the top.
            dialog.input.setText("line 1")
            dialog._rescan()
            dialog.find()
            assert view.textCursor().blockNumber() == 1

            # Backwards, a fresh word starts at the bottom.
            dialog.input.setText("target")
            dialog._rescan()
            dialog.backward_box.setChecked(True)
            dialog.find()
            assert view.textCursor().blockNumber() == 29
            dialog.backward_box.setChecked(False)

            # Reopening the window starts over too.
            dialog.close()
            view._show_search()
            dialog.find()
            assert view.textCursor().blockNumber() == 0

            # A log that grows mid-search must not drag the caret back up.
            dialog.find()
            window._on_new_log_entry(LogEntry("output.log", 31, "line 30 target", "ALL"))
            dialog.find()
            assert view.textCursor().blockNumber() == 2, "a new line is not a new search"
        finally:
            window.stop_workers()


def tr_or_key(key):
    from localization.localization_manager import tr
    return tr(key)


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
