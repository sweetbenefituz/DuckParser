from PySide6.QtWidgets import (
    QDialog, QGridLayout, QLabel, QLineEdit, QPushButton, QCheckBox, QTextEdit,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor, QTextDocument, QTextCharFormat, QColor
from localization.localization_manager import get_localization, tr

# Every hit but the current one. The current hit is the real text selection, so
# it already stands out in the #LogView selection colour.
MATCH_BG = QColor(120, 90, 0, 190)
MATCH_FG = QColor("#ffffff")

# A one-letter query in a 200k-line log matches a silly number of times. Stop
# counting there and show "20000+" instead of freezing the window.
# ponytail: raise the cap if anyone ever hits it for real.
MAX_MATCHES = 20000
MAX_HIGHLIGHTS = 5000
RESCAN_DELAY_MS = 200


class SearchDialog(QDialog):
    """Notepad++-shaped search: its own window, a hit counter, case and
    direction switches. Stays open while you step through the hits.

    How far the search has got is this dialog's own business: it walks its list
    of hits by index and never asks the log where the caret is. Clicking around
    in the log, deliberately or by accident, does not move the search.
    """

    def __init__(self, view):
        super().__init__(view.window())
        self.view = view

        self._matches = []         # (start, end) of every hit, in document order
        self._scan_key = None      # query + flags + document revision the list was built from
        self._searched_key = None  # query + flags the step count belongs to
        self._index = None         # the hit we are standing on; None before the first Find

        self.setWindowTitle(tr("search_title"))
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self._build_ui()

        get_localization().language_changed.connect(self._update_translations)

    def _build_ui(self):
        layout = QGridLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        self.query_label = QLabel(tr("search_label"))
        self.input = QLineEdit()
        self.input.setMinimumWidth(280)
        self.input.textChanged.connect(self._schedule_rescan)

        # lambda, not connect(self.find): clicked() hands the slot its own
        # checked flag, which arrives as backward=False and overrules the box.
        self.find_btn = QPushButton(tr("search_find"))
        self.find_btn.setDefault(True)
        self.find_btn.clicked.connect(lambda: self.find())

        self.case_box = QCheckBox(tr("search_case"))
        self.case_box.toggled.connect(self._schedule_rescan)

        self.backward_box = QCheckBox(tr("search_backward"))

        self.count_label = QLabel()
        self.count_label.setObjectName("SearchCount")

        self.close_btn = QPushButton(tr("search_close"))
        self.close_btn.setAutoDefault(False)  # Enter always means "search", never "close"
        self.close_btn.clicked.connect(self.close)

        layout.addWidget(self.query_label, 0, 0)
        layout.addWidget(self.input, 0, 1)
        layout.addWidget(self.find_btn, 0, 2)
        layout.addWidget(self.case_box, 1, 1)
        layout.addWidget(self.close_btn, 1, 2)
        layout.addWidget(self.backward_box, 2, 1)
        layout.addWidget(self.count_label, 3, 0, 1, 3)

        # Retyping rescans the whole document, so wait for a pause in typing.
        self._rescan_timer = QTimer(self)
        self._rescan_timer.setSingleShot(True)
        self._rescan_timer.setInterval(RESCAN_DELAY_MS)
        self._rescan_timer.timeout.connect(self._rescan)

    def _update_translations(self):
        self.setWindowTitle(tr("search_title"))
        self.query_label.setText(tr("search_label"))
        self.find_btn.setText(tr("search_find"))
        self.case_box.setText(tr("search_case"))
        self.backward_box.setText(tr("search_backward"))
        self.close_btn.setText(tr("search_close"))
        self._update_count()

    # ------------------------------------------------------------- scanning

    def _query_key(self):
        return (self.input.text(), self.case_box.isChecked())

    def _flags(self):
        if self.case_box.isChecked():
            return QTextDocument.FindFlag.FindCaseSensitively
        return QTextDocument.FindFlag(0)

    def _scan_key_now(self):
        # The document revision changes as the log grows, which is exactly when
        # the hit list has to be built again.
        return self._query_key() + (self.view.document().revision(),)

    def _schedule_rescan(self):
        self._rescan_timer.start()

    def _rescan(self):
        document = self.view.document()
        query = self.input.text()

        self._matches = []
        self._scan_key = self._scan_key_now()

        if query:
            cursor = QTextCursor(document)
            while len(self._matches) < MAX_MATCHES:
                cursor = document.find(query, cursor, self._flags())
                if cursor.isNull():
                    break
                self._matches.append((cursor.selectionStart(), cursor.selectionEnd()))

        if self._query_key() != self._searched_key:
            self._index = None  # a different word: the step count starts over
        elif self._index is not None and self._index >= len(self._matches):
            # The log was trimmed under us and the hit we stood on is gone.
            self._index = len(self._matches) - 1 if self._matches else None

        self._highlight()
        self._update_count()

    def _ensure_scanned(self):
        if self._scan_key != self._scan_key_now():
            self._rescan()

    def _highlight(self):
        fmt = QTextCharFormat()
        fmt.setBackground(MATCH_BG)
        fmt.setForeground(MATCH_FG)

        selections = []
        for start, end in self._matches[:MAX_HIGHLIGHTS]:
            cursor = QTextCursor(self.view.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)

            selection = QTextEdit.ExtraSelection()
            selection.format = fmt
            selection.cursor = cursor
            selections.append(selection)

        self.view.setExtraSelections(selections)

    def _update_count(self):
        if not self.input.text():
            self.count_label.setText("")
            return

        total = len(self._matches)
        if not total:
            self.count_label.setText(tr("search_none"))
            return

        more = "+" if total >= MAX_MATCHES else ""
        where = f"{self._index + 1} / {total}{more}" if self._index is not None else f"{total}{more}"

        self.count_label.setText(f"{tr('search_count')}: {where}")

    # ----------------------------------------------------------- navigation

    def find(self, backward: bool | None = None):
        if backward is None:
            backward = self.backward_box.isChecked()

        self._rescan_timer.stop()
        self._ensure_scanned()

        if not self._matches:
            self._index = None
            self._update_count()
            return

        if self._query_key() != self._searched_key or self._index is None:
            # A word searched for the first time starts at the top of the log,
            # or at the bottom when going backwards.
            self._index = len(self._matches) - 1 if backward else 0
            self._searched_key = self._query_key()
        else:
            self._index = (self._index + (-1 if backward else 1)) % len(self._matches)

        start, end = self._matches[self._index]
        cursor = QTextCursor(self.view.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        self.view.select_match(cursor)

        self._update_count()

    # --------------------------------------------------------------- window

    def focus_input(self):
        self.input.setFocus()
        self.input.selectAll()

    def restart(self):
        """Reopening the window searches from the top again."""
        self._searched_key = None
        self._index = None

    def center_on_parent(self):
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        self.move(parent.geometry().center() - self.rect().center())

    def closeEvent(self, event):
        self.view.setExtraSelections([])  # leaving the search leaves no paint behind
        super().closeEvent(event)
