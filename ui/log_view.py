from PySide6.QtWidgets import QTextEdit, QPushButton, QMenu
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QTextCursor, QTextCharFormat, QTextBlockFormat, QColor,
    QKeySequence, QShortcut,
)
from localization.localization_manager import tr
from ui.search_dialog import SearchDialog

# Same batching reason as LogStorage.TRIM_SLACK: removing one block per
# appended row would rewrite the document layout on every single line.
TRIM_SLACK = 1000


class LogView(QTextEdit):
    goto_all_requested = Signal(int)

    def __init__(self):
        super().__init__()

        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.setObjectName("LogView")

        self._auto_scroll = True
        self._user_scrolled_up = False
        self._line_entries = []
        self.max_rows = 0  # 0 = keep everything; set from settings.max_lines

        # Set while the view is being rebuilt or jumped, so our own scroll
        # handlers keep quiet. Never blockSignals() the scrollbar for this:
        # QAbstractScrollArea listens to it too, and a blocked valueChanged
        # leaves the text itself un-scrolled -- a refilled view then paints
        # blank until something else forces a relayout.
        self._suppress_scroll_events = False

        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.verticalScrollBar().rangeChanged.connect(self._on_range_changed)

        self._build_scroll_button()
        self._build_search()
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _build_scroll_button(self):
        self.scroll_btn = QPushButton("v", self)
        self.scroll_btn.setObjectName("ScrollDownButton")
        self.scroll_btn.setFixedSize(32, 32)
        self.scroll_btn.hide()
        self.scroll_btn.clicked.connect(self.scroll_to_bottom)

    def _build_search(self):
        self.search_dialog = None  # built on the first Ctrl+F
        QShortcut(QKeySequence.Find, self).activated.connect(self._show_search)
        QShortcut(Qt.Key_Escape, self).activated.connect(self._close_search)

    def _show_search(self):
        if self.search_dialog is None:
            self.search_dialog = SearchDialog(self)
            self.search_dialog.center_on_parent()

        self.search_dialog.restart()
        self.search_dialog.show()
        self.search_dialog.raise_()
        self.search_dialog.activateWindow()
        self.search_dialog.focus_input()

    def _close_search(self):
        if self.search_dialog is not None:
            self.search_dialog.close()

    def select_match(self, cursor: QTextCursor):
        """Put the caret on a search hit and stop the view running away from it."""
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        self._center_on_cursor()
        self._disable_auto_scroll()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        scrollbar_width = self.verticalScrollBar().width() if self.verticalScrollBar().isVisible() else 0
        self.scroll_btn.move(
            self.width() - 42 - scrollbar_width - 8,
            self.height() - 42
        )

    def _disable_auto_scroll(self):
        self._auto_scroll = False
        self._user_scrolled_up = True
        self.scroll_btn.show()

    def _on_scroll(self):
        if self._suppress_scroll_events:
            return

        bar = self.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 10

        self._auto_scroll = at_bottom
        self._user_scrolled_up = not at_bottom
        self.scroll_btn.setVisible(not at_bottom)

    def _on_range_changed(self, min_val, max_val):
        if self._suppress_scroll_events:
            return
        if self._auto_scroll and not self._user_scrolled_up:
            self.verticalScrollBar().setValue(max_val)

    def scroll_to_bottom(self):
        self._auto_scroll = True
        self._user_scrolled_up = False
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.scroll_btn.hide()

    def scroll_to_line(self, line_index: int):
        # findBlockByNumber, not findBlockByLineNumber: rows are blocks, and
        # a wrapped row spans several *lines* but stays one block.
        block = self.document().findBlockByNumber(line_index)
        if not block.isValid():
            return

        scrollbar = self.verticalScrollBar()
        self._suppress_scroll_events = True

        self.setTextCursor(QTextCursor(block))
        self.ensureCursorVisible()
        self._center_on_cursor()

        self._auto_scroll = False
        self._user_scrolled_up = True

        self._suppress_scroll_events = False
        self.scroll_btn.show()

    def _center_on_cursor(self):
        cursor_rect = self.cursorRect()
        viewport_height = self.viewport().height()
        scroll_value = self.verticalScrollBar().value()
        target_y = cursor_rect.top() - (viewport_height // 2) + scroll_value
        self.verticalScrollBar().setValue(max(0, target_y))

    def row_count(self) -> int:
        return len(self._line_entries)

    def _insert_row(self, cursor: QTextCursor, text: str, background: QColor):
        """One row == one text block, so block numbers stay in step with
        _line_entries indices.

        The colour goes on the *block* format, never the char format: a block
        background paints the full widget width, a char background stops where
        the glyphs stop. HTML <div> backgrounds survive setHtml() as block
        formats but degrade to char formats through insertHtml(), which is why
        rows are built with the cursor API instead of markup.
        """
        if not self.document().isEmpty():
            cursor.insertBlock()

        block_fmt = QTextBlockFormat()
        block_fmt.setBackground(background)
        block_fmt.setTopMargin(3)
        block_fmt.setBottomMargin(3)
        block_fmt.setLeftMargin(6)
        block_fmt.setRightMargin(6)
        cursor.setBlockFormat(block_fmt)

        # Reset explicitly, otherwise the previous row's colours bleed onward.
        cursor.setCharFormat(QTextCharFormat())
        cursor.insertText(text)

    def _trim_oldest(self):
        """Drop the head rows so the view cannot grow without bound. Blocks and
        _line_entries are trimmed together, keeping index == block number."""
        if not self.max_rows or len(self._line_entries) <= self.max_rows + TRIM_SLACK:
            return

        excess = len(self._line_entries) - self.max_rows
        del self._line_entries[:excess]

        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.NextBlock, QTextCursor.KeepAnchor, excess)
        cursor.removeSelectedText()

    def append_row(self, text: str, background: QColor, entry):
        self._line_entries.append(entry)

        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.End)
        self._insert_row(cursor, text, background)

        self._trim_oldest()

        if self._auto_scroll and not self._user_scrolled_up:
            bar = self.verticalScrollBar()
            bar.setValue(bar.maximum())

    def set_rows(self, rows, entries: list):
        """Replace the whole view. `rows` is an iterable of (text, background)."""
        was_at_bottom = self._auto_scroll and not self._user_scrolled_up
        old_scroll_value = self.verticalScrollBar().value()
        old_auto_scroll = self._auto_scroll
        old_user_scrolled_up = self._user_scrolled_up

        scrollbar = self.verticalScrollBar()
        self._suppress_scroll_events = True
        self.setUpdatesEnabled(False)

        self.clear()
        self._line_entries = list(entries)

        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        for text, background in rows:
            self._insert_row(cursor, text, background)
        cursor.endEditBlock()

        self.setUpdatesEnabled(True)

        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(min(old_scroll_value, scrollbar.maximum()))

        if entries:
            self._auto_scroll = old_auto_scroll
            self._user_scrolled_up = old_user_scrolled_up
        else:
            # An emptied view (Clear tab) starts over: whatever is loaded next
            # should follow the newest line, like a freshly opened file.
            self._auto_scroll = True
            self._user_scrolled_up = False

        self._suppress_scroll_events = False
        self.scroll_btn.setVisible(self._user_scrolled_up)

        # repaint(), not update(): a queued update after a full document swap
        # only ever redrew part of the viewport, so a refilled view kept showing
        # the emptied one until a tab switch forced the rest.
        self.viewport().repaint()

    def clear_view(self):
        self.clear()
        self._line_entries.clear()
        self._auto_scroll = True
        self._user_scrolled_up = False

    def _show_context_menu(self, pos):
        block_number = self.cursorForPosition(pos).blockNumber()

        menu = QMenu(self)
        copy_action = menu.addAction(tr("ctx_copy"))

        goto_action = None
        entry = self.get_entry_at_line(block_number)
        if entry is not None and entry.level in ("ERROR", "WARNING"):
            goto_action = menu.addAction(tr("ctx_goto_all"))

        action = menu.exec(self.mapToGlobal(pos))

        if action == copy_action:
            self.copy()
        elif goto_action and action == goto_action:
            self.goto_all_requested.emit(block_number)

    def get_entry_at_line(self, line_index: int):
        if 0 <= line_index < len(self._line_entries):
            return self._line_entries[line_index]
        return None
