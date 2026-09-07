from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QMenuBar, QMenu, QFileDialog, QLabel,
    QInputDialog, QMessageBox, QApplication,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QActionGroup
from ui.tabs import FilterTabs, FILTER_LEVELS, FILTER_LABEL_KEYS
from ui.log_view import LogView
from models.log_storage import LogStorage, LogEntry
from parser.log_parser import detect_level
from parser.log_worker import LogWorker
from settings.settings_manager import settings
from localization.localization_manager import get_localization, tr
from string import Template
import json
import os

THEMES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "themes")

RECENT_FILES_MAX = 10
STATUS_INTERVAL_MS = 500
FILTER_DELAY_MS = 250


def to_qcolor(value) -> QColor:
    """Palette colours are "#rrggbb" strings, or [r, g, b, a] when they need alpha."""
    return QColor(*value) if isinstance(value, list) else QColor(value)


def load_palette(theme: str) -> dict:
    with open(os.path.join(THEMES_DIR, "palettes.json"), "r", encoding="utf-8") as f:
        palettes = json.load(f)
    return palettes.get(theme) or palettes["dark"]


PATH_DEPTHS = ((0, "path_full"), (2, "path_2"), (3, "path_3"), (4, "path_4"), (5, "path_5"))
LINE_LIMITS = ((50000, "limit_50k"), (200000, "limit_200k"),
               (500000, "limit_500k"), (0, "limit_none"))


def format_tab_path(path: str, depth: int) -> str:
    """Tab tooltip: the whole path, or the last `depth` folders plus the file name."""
    if depth <= 0:
        return path

    parts = os.path.normpath(path).split(os.sep)
    if len(parts) <= depth + 1:
        return path

    return os.sep.join(["..."] + parts[-(depth + 1):])


def build_stylesheet(palette: dict) -> str:
    """base.qss is the only stylesheet; the palette fills in its $placeholders."""
    icon_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ico")
    values = dict(
        palette,
        # QSS wants forward slashes and an absolute path (see base.qss).
        close_icon=os.path.join(icon_dir, "close.png").replace("\\", "/"),
    )
    with open(os.path.join(THEMES_DIR, "base.qss"), "r", encoding="utf-8") as f:
        return Template(f.read()).substitute(values)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.storage = LogStorage(settings.max_lines)
        self.current_filter = "ALL"
        self.current_file = None
        self.workers_by_file = {}
        self._text_filter = ""
        self._status_dirty = True
        self._palette = load_palette(settings.theme)
        self._cache_row_colors()

        get_localization().language_changed.connect(self._update_translations)

        self._build_ui()
        self.setAcceptDrops(True)  # drop a .log from Explorer straight onto the window

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.menu_bar = QMenuBar()
        self._build_menu()
        layout.addWidget(self.menu_bar)

        self.tabs = FilterTabs()
        layout.addWidget(self.tabs)
        self.tabs.filter_tabs.currentChanged.connect(self._on_filter_changed)
        self.tabs.file_tabs.currentChanged.connect(self._on_file_changed)
        self.tabs.clear_btn.clicked.connect(self._clear_current_view)
        self.tabs.load_full_btn.clicked.connect(self._load_full_files)
        self.tabs.file_tab_bar.tabCloseRequested.connect(self._close_file_tab)
        self.tabs.file_tab_bar.open_path_requested.connect(self._open_file_path)

        self.log_view = LogView()
        self.log_view.max_rows = settings.max_lines
        self.log_view.setAcceptDrops(False)  # let drops fall through to this window
        self.log_view.goto_all_requested.connect(self._goto_entry_in_all)
        layout.addWidget(self.log_view, 1)

        self.status_label = QLabel()
        self.status_label.setObjectName("StatusBar")
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.status_label)

        # Typing in the filter box rebuilds the whole view, so wait for a pause.
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(FILTER_DELAY_MS)
        self._filter_timer.timeout.connect(self._apply_text_filter)
        self.tabs.filter_input.textChanged.connect(lambda _: self._filter_timer.start())

        # Counters and the status line are recomputed on a timer, not per line:
        # a fast log would otherwise rescan the storage thousands of times a second.
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status)
        self._status_timer.start(STATUS_INTERVAL_MS)

    def _build_menu(self):
        self.file_menu = QMenu(tr("menu_file"), self)
        self.open_action = self.file_menu.addAction(tr("menu_open"))
        self.open_action.triggered.connect(self._open_log_file)

        self.recent_menu = QMenu(tr("menu_recent"), self)
        self.recent_menu.setToolTipsVisible(True)  # the entry is shortened; the tooltip has the full path
        self.file_menu.addMenu(self.recent_menu)
        self._rebuild_recent_menu()

        self.file_menu.addSeparator()
        self.clear_action = self.file_menu.addAction(tr("menu_clear_all"))
        self.clear_action.triggered.connect(self._clear_all_views)

        self.settings_menu = QMenu(tr("menu_settings"), self)

        self.language_menu = QMenu(tr("menu_language"), self)
        self.lang_actions = {}
        for code, key in (("ru", "lang_russian"), ("en", "lang_english"), ("ua", "lang_ukrainian")):
            action = self.language_menu.addAction(tr(key))
            action.triggered.connect(lambda checked=False, c=code: self._set_language(c))
            self.lang_actions[key] = action

        self.theme_menu = QMenu(tr("menu_theme"), self)
        self.theme_actions = {}
        for name, key in (("dark", "theme_dark"), ("light", "theme_light")):
            action = self.theme_menu.addAction(tr(key))
            action.triggered.connect(lambda checked=False, n=name: self._set_theme(n))
            self.theme_actions[key] = action

        self.path_menu = QMenu(tr("menu_tab_path"), self)
        self.path_actions = {}
        path_group = QActionGroup(self)
        for depth, key in PATH_DEPTHS:
            action = self.path_menu.addAction(tr(key))
            action.setCheckable(True)
            action.setChecked(settings.path_depth == depth)
            path_group.addAction(action)
            action.triggered.connect(lambda checked=False, d=depth: self._set_path_depth(d))
            self.path_actions[key] = action

        self.limit_menu = QMenu(tr("menu_max_lines"), self)
        self.limit_actions = {}
        limit_group = QActionGroup(self)
        for limit, key in LINE_LIMITS:
            action = self.limit_menu.addAction(tr(key))
            action.setCheckable(True)
            action.setChecked(settings.max_lines == limit)
            limit_group.addAction(action)
            action.triggered.connect(lambda checked=False, n=limit: self._set_max_lines(n))
            self.limit_actions[key] = action

        self.settings_menu.addMenu(self.language_menu)
        self.settings_menu.addMenu(self.theme_menu)
        self.settings_menu.addMenu(self.path_menu)
        self.settings_menu.addMenu(self.limit_menu)
        self.settings_menu.addSeparator()

        self.word_actions = {}
        for key in ("error_words", "warning_words"):
            action = self.settings_menu.addAction(tr(f"menu_{key}"))
            action.triggered.connect(lambda checked=False, k=key: self._edit_words(k))
            self.word_actions[key] = action

        self.settings_menu.addSeparator()

        self.always_on_top_action = self.settings_menu.addAction(tr("always_on_top"))
        self.always_on_top_action.setCheckable(True)
        self.always_on_top_action.triggered.connect(self._toggle_always_on_top)

        self.menu_bar.addMenu(self.file_menu)
        self.menu_bar.addMenu(self.settings_menu)

    def _update_translations(self):
        self.window().setWindowTitle(tr("app_title"))

        self.file_menu.setTitle(tr("menu_file"))
        self.open_action.setText(tr("menu_open"))
        self.recent_menu.setTitle(tr("menu_recent"))
        self.clear_action.setText(tr("menu_clear_all"))

        self.settings_menu.setTitle(tr("menu_settings"))
        self.language_menu.setTitle(tr("menu_language"))
        self.theme_menu.setTitle(tr("menu_theme"))
        self.path_menu.setTitle(tr("menu_tab_path"))
        self.limit_menu.setTitle(tr("menu_max_lines"))

        for key, action in (*self.lang_actions.items(), *self.theme_actions.items(),
                            *self.path_actions.items(), *self.limit_actions.items()):
            action.setText(tr(key))

        for key, action in self.word_actions.items():
            action.setText(tr(f"menu_{key}"))

        self.always_on_top_action.setText(tr("always_on_top"))
        self._rebuild_recent_menu()
        self._status_dirty = True  # the tab labels just lost their counters

    # ---------------------------------------------------------------- settings

    def _toggle_always_on_top(self, checked: bool):
        window = self.window()
        window.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        window.show()  # flags change hides the window, so bring it back

    def _set_language(self, lang: str):
        settings.language = lang
        get_localization().set_language(lang)

    def _set_path_depth(self, depth: int):
        settings.path_depth = depth
        self._refresh_tab_tooltips()

    def _set_max_lines(self, limit: int):
        settings.max_lines = limit
        self.storage.max_lines = limit
        self.log_view.max_rows = limit

    def _edit_words(self, key: str):
        """Keyword lists live in settings so Unreal's "Fatal" or Unity's
        "Exception" can be coloured without touching the code."""
        text, ok = QInputDialog.getText(
            self, tr("menu_settings"), tr(f"prompt_{key}"),
            text=", ".join(getattr(settings, key)),
        )
        if not ok:
            return

        setattr(settings, key, [w.strip().lower() for w in text.split(",") if w.strip()])

        for entry in self.storage.all_entries():
            entry.level = detect_level(entry.text, settings.error_words, settings.warning_words)
        self._refresh_view()

    def _refresh_tab_tooltips(self):
        for i in range(self.tabs.file_tabs.count()):
            worker = self.workers_by_file.get(self.tabs.file_tabs.tabText(i))
            if worker:
                self.tabs.file_tabs.setTabToolTip(
                    i, format_tab_path(worker.path, settings.path_depth)
                )

    def _set_theme(self, theme: str):
        settings.theme = theme
        self._apply_theme(theme)

    def _apply_theme(self, theme: str):
        self._palette = load_palette(theme)
        self._cache_row_colors()
        self.window().setStyleSheet(build_stylesheet(self._palette))
        self._refresh_view()  # zebra striping is palette-dependent

    def _cache_row_colors(self):
        # Built once per theme instead of per row.
        self._row_error = to_qcolor(self._palette["row_error"])
        self._row_warning = to_qcolor(self._palette["row_warning"])
        self._zebra = (
            to_qcolor(self._palette["zebra_even"]),
            to_qcolor(self._palette["zebra_odd"]),
        )

    # ------------------------------------------------------------------- view

    def _on_filter_changed(self, index: int):
        self.current_filter = FILTER_LEVELS[index]
        self._refresh_view()

    def _on_file_changed(self, index: int):
        # Index 0 is the "All files" tab whatever it is called in the current language.
        self.current_file = None if index == 0 else self.tabs.file_tabs.tabText(index)
        self._refresh_view()

    def _apply_text_filter(self):
        self._text_filter = self.tabs.filter_input.text().strip().lower()
        self._refresh_view()

    def _matches_text(self, entry: LogEntry) -> bool:
        return not self._text_filter or self._text_filter in entry.text.lower()

    def _visible_entries(self, level: str | None = None) -> list[LogEntry]:
        entries = self.storage.get(self.current_file, level or self.current_filter)
        return [e for e in entries if self._matches_text(e)]

    def _row(self, entry: LogEntry, index: int) -> tuple[str, QColor]:
        """Returns the text to show and the colour its whole line gets."""
        if entry.level == "ERROR":
            background = self._row_error
        elif entry.level == "WARNING":
            background = self._row_warning
        else:
            background = self._zebra[index % 2]

        # Line numbers only make sense in the filtered tabs.
        prefix = "" if self.current_filter == "ALL" else f"[{tr('line_prefix')} {entry.line_no}] "
        if self.current_file is None:
            prefix = f"[{entry.file}] {prefix}"

        return prefix + entry.text, background

    def _refresh_view(self):
        entries = self._visible_entries()
        self.log_view.set_rows(
            (self._row(e, i) for i, e in enumerate(entries)),
            entries,
        )
        self._status_dirty = True

    def _on_new_log_entry(self, entry: LogEntry):
        self.storage.add(entry)
        self._status_dirty = True

        if self.current_file not in (None, entry.file):
            return
        if self.current_filter not in ("ALL", entry.level):
            return
        if not self._matches_text(entry):
            return

        # Append one row instead of rebuilding the document per line.
        text, background = self._row(entry, self.log_view.row_count())
        self.log_view.append_row(text, background, entry)

    def _update_status(self):
        if not self._status_dirty:
            return
        self._status_dirty = False

        counts = dict.fromkeys(FILTER_LEVELS, 0)
        for entry in self.storage.all_entries(self.current_file):
            if not self._matches_text(entry):
                continue
            if not entry.hidden:
                counts["ALL"] += 1
            if entry.level in ("ERROR", "WARNING"):
                counts[entry.level] += 1

        for i, (level, key) in enumerate(zip(FILTER_LEVELS, FILTER_LABEL_KEYS)):
            # No count on "All": it is just the line total, already in the status bar.
            label = tr(key) if level == "ALL" else f"{tr(key)} ({counts[level]})"
            if self.tabs.filter_tabs.tabText(i) != label:
                self.tabs.filter_tabs.setTabText(i, label)

        self.status_label.setText(self._status_text(counts["ALL"]))

    def _status_text(self, shown: int) -> str:
        parts = []

        if self.current_file is None:
            if not self.workers_by_file:
                return tr("status_no_file")
            parts.append(f"{tr('status_files')}: {len(self.workers_by_file)}")
        else:
            worker = self.workers_by_file.get(self.current_file)
            if worker is None:
                return tr("status_no_file")
            parts.append(worker.path)
            parts.append(tr("status_live") if worker.isRunning() else tr("status_stopped"))

        parts.append(f"{tr('status_lines')}: {shown}")
        if self._text_filter:
            parts.append(f"{tr('status_filter')}: {self._text_filter}")

        return "     ".join(parts)

    # ------------------------------------------------------------------ files

    def _open_log_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("file_dialog_title"),
            settings.last_folder,
            "Text files (*.log *.txt *.xml *.json);;All files (*)"
        )
        if path:
            self._accept_file(path)

    def _accept_file(self, path: str):
        """Every way a file can arrive: the dialog, a drop, the recent list."""
        settings.last_folder = os.path.dirname(path)
        self._push_recent(path)
        self._open_file_by_path(path)
        self._refresh_view()
        self._save_open_files()

    def _open_file_by_path(self, path: str):
        existing = self._tab_index_for_path(path)
        if existing is not None:
            self.tabs.file_tabs.setCurrentIndex(existing)  # same file twice: just go to it
            return

        # Logs from different builds share a name, so the second one becomes
        # "output.log (1)". That label is the key storage and workers use.
        label = self._unique_tab_label(os.path.basename(path))
        index = self.tabs.file_tabs.addTab(QWidget(), label)
        self.tabs.file_tabs.setTabToolTip(index, format_tab_path(path, settings.path_depth))

        self.storage.add(LogEntry(
            file=label,
            line_no=0,
            text=f'{tr("log_opened")} "{label}"',
            level="ALL"
        ))

        self._start_worker(path, label)

    def _start_worker(self, path: str, label: str):
        worker = LogWorker(path, label)
        worker.new_entry.connect(self._on_new_log_entry)
        worker.start()
        self.workers_by_file[label] = worker

    def _load_full_files(self):
        """Tailing only shows lines written from now on. This reads what is
        already in the file -- the whole point of opening a finished log."""
        labels = [self.current_file] if self.current_file else list(self.workers_by_file)
        if not labels:
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for label in labels:
                self._reload_file(label)
        finally:
            # In the finally block on purpose: a file that blows up halfway
            # through must not leave the view showing the old, cleared document.
            QApplication.restoreOverrideCursor()
            self._refresh_view()

    def _reload_file(self, label: str):
        worker = self.workers_by_file.get(label)
        if worker is None:
            return

        path = worker.path
        # Entries already queued from the old thread would land in the rebuilt
        # view and be counted twice.
        worker.new_entry.disconnect(self._on_new_log_entry)
        worker.stop()
        worker.wait(2000)

        self.storage.clear(label)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line_no, line in enumerate(f, 1):
                    text = line.rstrip("\n")
                    self.storage.add(LogEntry(
                        file=label,
                        line_no=line_no,
                        text=text,
                        level=detect_level(text, settings.error_words, settings.warning_words),
                    ))
        except OSError as e:
            self.storage.add(LogEntry(label, 0, f"Parser error: {e}", "ERROR"))

        # A fresh worker picks up at the end of the file and keeps tailing.
        self._start_worker(path, label)

    def _tab_index_for_path(self, path: str):
        target = os.path.normcase(os.path.abspath(path))
        for i in range(self.tabs.file_tabs.count()):
            worker = self.workers_by_file.get(self.tabs.file_tabs.tabText(i))
            if worker and os.path.normcase(os.path.abspath(worker.path)) == target:
                return i
        return None

    def _unique_tab_label(self, name: str) -> str:
        label, n = name, 0
        while self._file_tab_exists(label):
            n += 1
            label = f"{name} ({n})"
        return label

    def _file_tab_exists(self, name: str) -> bool:
        return any(
            self.tabs.file_tabs.tabText(i) == name
            for i in range(self.tabs.file_tabs.count())
        )

    def _clear_current_view(self):
        if self.current_filter == "ALL":
            # Keep errors/warnings alive in their own tabs, just hide them here.
            self.storage.clear_non_critical(self.current_file)
        else:
            self.storage.clear(self.current_file, self.current_filter)
        self._refresh_view()

    def _clear_all_views(self):
        self.storage.clear()
        self._refresh_view()

    def _close_file_tab(self, index: int):
        if index == 0:
            return

        name = self.tabs.file_tabs.tabText(index)

        worker = self.workers_by_file.pop(name, None)
        if worker:
            worker.stop()
            worker.wait(1000)

        self.storage.clear(name)
        self.tabs.file_tabs.removeTab(index)

        if self.current_file == name:
            self.tabs.file_tabs.setCurrentIndex(0)  # emits currentChanged -> refresh

        self._save_open_files()

    def _open_file_path(self, index: int):
        worker = self.workers_by_file.get(self.tabs.file_tabs.tabText(index))
        if worker:
            os.startfile(os.path.dirname(worker.path))

    def _save_open_files(self):
        settings.open_files = [w.path for w in self.workers_by_file.values()]

    # --------------------------------------------------------- recent / drops

    def _push_recent(self, path: str):
        target = os.path.normcase(path)
        recent = [p for p in settings.recent_files if os.path.normcase(p) != target]
        settings.recent_files = ([path] + recent)[:RECENT_FILES_MAX]
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        self.recent_menu.clear()
        self.recent_menu.setEnabled(bool(settings.recent_files))

        for path in settings.recent_files:
            action = self.recent_menu.addAction(format_tab_path(path, 2))
            action.setToolTip(path)
            action.triggered.connect(lambda checked=False, p=path: self._open_recent(p))

        if settings.recent_files:
            self.recent_menu.addSeparator()
            clear_action = self.recent_menu.addAction(tr("menu_recent_clear"))
            clear_action.triggered.connect(self._clear_recent)

    def _clear_recent(self):
        settings.recent_files = []
        self._rebuild_recent_menu()

    def _open_recent(self, path: str):
        if not os.path.exists(path):
            settings.recent_files = [p for p in settings.recent_files if p != path]
            self._rebuild_recent_menu()
            QMessageBox.warning(self, tr("app_title"), f"{tr('recent_missing')}\n{path}")
            return
        self._accept_file(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path):
                self._accept_file(path)
        event.acceptProposedAction()

    # ------------------------------------------------------------- navigation

    def _goto_entry_in_all(self, line_index: int):
        entry = self.log_view.get_entry_at_line(line_index)
        if entry is None:
            return

        self.tabs.filter_tabs.setCurrentIndex(0)  # emits currentChanged -> refresh

        # The same list _refresh_view just built, so the text filter cannot skew the index.
        entries = self._visible_entries("ALL")
        if entry in entries:
            self.log_view.scroll_to_line(entries.index(entry))

    def stop_workers(self):
        for worker in self.workers_by_file.values():
            worker.stop()
            worker.wait(1000)

    def restore_state(self):
        get_localization().set_language(settings.language)
        self._update_translations()
        self._apply_theme(settings.theme)

        for path in settings.open_files:
            if os.path.exists(path):
                self._open_file_by_path(path)

        self._refresh_view()
