from PySide6.QtWidgets import QWidget, QVBoxLayout, QMenuBar, QMenu, QFileDialog
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QActionGroup
from ui.tabs import FilterTabs, FILTER_LEVELS
from ui.log_view import LogView
from models.log_storage import LogStorage, LogEntry
from parser.log_worker import LogWorker
from settings.settings_manager import settings
from localization.localization_manager import get_localization, tr
from string import Template
import json
import os

THEMES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "themes")


def to_qcolor(value) -> QColor:
    """Palette colours are "#rrggbb" strings, or [r, g, b, a] when they need alpha."""
    return QColor(*value) if isinstance(value, list) else QColor(value)


def load_palette(theme: str) -> dict:
    with open(os.path.join(THEMES_DIR, "palettes.json"), "r", encoding="utf-8") as f:
        palettes = json.load(f)
    return palettes.get(theme) or palettes["dark"]


PATH_DEPTHS = ((0, "path_full"), (2, "path_2"), (3, "path_3"), (4, "path_4"), (5, "path_5"))


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

        self.storage = LogStorage()
        self.current_filter = "ALL"
        self.current_file = None
        self.workers_by_file = {}
        self._palette = load_palette(settings.theme)
        self._cache_row_colors()

        get_localization().language_changed.connect(self._update_translations)

        self._build_ui()

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
        self.tabs.file_tab_bar.tabCloseRequested.connect(self._close_file_tab)
        self.tabs.file_tab_bar.open_path_requested.connect(self._open_file_path)

        self.log_view = LogView()
        self.log_view.goto_all_requested.connect(self._goto_entry_in_all)
        layout.addWidget(self.log_view, 1)

    def _build_menu(self):
        self.file_menu = QMenu(tr("menu_file"), self)
        self.open_action = self.file_menu.addAction(tr("menu_open"))
        self.open_action.triggered.connect(self._open_log_file)
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

        self.settings_menu.addMenu(self.language_menu)
        self.settings_menu.addMenu(self.theme_menu)
        self.settings_menu.addMenu(self.path_menu)
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
        self.clear_action.setText(tr("menu_clear_all"))

        self.settings_menu.setTitle(tr("menu_settings"))
        self.language_menu.setTitle(tr("menu_language"))
        self.theme_menu.setTitle(tr("menu_theme"))
        self.path_menu.setTitle(tr("menu_tab_path"))

        for key, action in (*self.lang_actions.items(), *self.theme_actions.items(),
                            *self.path_actions.items()):
            action.setText(tr(key))

        self.always_on_top_action.setText(tr("always_on_top"))

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

    def _on_filter_changed(self, index: int):
        self.current_filter = FILTER_LEVELS[index]
        self._refresh_view()

    def _on_file_changed(self, index: int):
        # Index 0 is the "All files" tab whatever it is called in the current language.
        self.current_file = None if index == 0 else self.tabs.file_tabs.tabText(index)
        self._refresh_view()

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
        entries = self.storage.get(self.current_file, self.current_filter)
        self.log_view.set_rows(
            (self._row(e, i) for i, e in enumerate(entries)),
            entries,
        )

    def _on_new_log_entry(self, entry: LogEntry):
        self.storage.add(entry)

        if self.current_file not in (None, entry.file):
            return
        if self.current_filter not in ("ALL", entry.level):
            return

        # Append one row instead of rebuilding the document per line.
        text, background = self._row(entry, self.log_view.row_count())
        self.log_view.append_row(text, background, entry)

    def _open_log_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("file_dialog_title"),
            settings.last_folder,
            "Text files (*.log *.txt *.xml *.json);;All files (*)"
        )
        if not path:
            return

        settings.last_folder = os.path.dirname(path)
        self._open_file_by_path(path)
        self._refresh_view()
        self._save_open_files()

    def _open_file_by_path(self, path: str):
        existing = self._tab_index_for_path(path)
        if existing is not None:
            self.tabs.file_tabs.setCurrentIndex(existing)  # same file twice: just go to it
            return

        # Logs from different builds share a name, so the second one becomes
        # "duckside.log (1)". That label is the key storage and workers use.
        label = self._unique_tab_label(os.path.basename(path))
        index = self.tabs.file_tabs.addTab(QWidget(), label)
        self.tabs.file_tabs.setTabToolTip(index, format_tab_path(path, settings.path_depth))

        self.storage.add(LogEntry(
            file=label,
            line_no=0,
            text=f'{tr("log_opened")} "{label}"',
            level="ALL"
        ))

        worker = LogWorker(path, label)
        worker.new_entry.connect(self._on_new_log_entry)
        worker.start()
        self.workers_by_file[label] = worker

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

    def _goto_entry_in_all(self, line_index: int):
        entry = self.log_view.get_entry_at_line(line_index)
        if entry is None:
            return

        self.tabs.filter_tabs.setCurrentIndex(0)  # emits currentChanged -> refresh

        all_index = self.storage.find_entry_in_all(entry)
        if all_index is not None:
            self.log_view.scroll_to_line(all_index)

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
