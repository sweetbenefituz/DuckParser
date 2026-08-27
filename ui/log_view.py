from PySide6.QtWidgets import QTextEdit, QPushButton, QMenu, QLineEdit, QHBoxLayout, QWidget
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QTextCursor, QTextCharFormat, QTextBlockFormat, QColor,
    QKeySequence, QShortcut, QTextDocument,
)
from localization.localization_manager import get_localization, tr

HIGHLIGHT_BG = QColor("#1e90ff")
HIGHLIGHT_FG = QColor("#ffffff")


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

        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.verticalScrollBar().rangeChanged.connect(self._on_range_changed)

        self._build_scroll_button()
        self._build_search_bar()
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        get_localization().language_changed.connect(self._update_translations)

    def _build_scroll_button(self):
        self.scroll_btn = QPushButton("v", self)
        self.scroll_btn.setObjectName("ScrollDownButton")
        self.scroll_btn.setFixedSize(32, 32)
        self.scroll_btn.hide()
        self.scroll_btn.clicked.connect(self.scroll_to_bottom)

    def _build_search_bar(self):
        self.search_widget = QWidget(self)
        self.search_widget.setObjectName("SearchBar")

        layout = QHBoxLayout(self.search_widget)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("search_placeholder"))
        self.search_input.returnPressed.connect(self._search_next)
        layout.addWidget(self.search_input)

        for label, slot in (("▲", self._search_prev), ("▼", self._search_next), ("✕", self._hide_search)):
            btn = QPushButton(label)
            btn.setFixedWidth(32)
            btn.clicked.connect(slot)
            layout.addWidget(btn)

        self.search_widget.setFixedHeight(46)
        self.search_widget.hide()

        QShortcut(QKeySequence.Find, self).activated.connect(self._show_search)
        QShortcut(Qt.Key_Escape, self).activated.connect(self._hide_search)

        self._last_search_pos = -1

    def _update_translations(self):
        self.search_input.setPlaceholderText(tr("search_placeholder"))

    def _show_search(self):
        self.search_widget.show()
        self.search_widget.raise_()
        self.search_input.setFocus()
        self.search_input.selectAll()
        self._position_search_bar()

    def _hide_search(self):
        self.search_widget.hide()
        self._last_search_pos = -1
        self.setExtraSelections([])

    def _position_search_bar(self):
        target_width = min(350, self.width() - 40)
        self.search_widget.setFixedWidth(target_width)
        self.search_widget.move(self.width() - target_width - 20, 10)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        scrollbar_width = self.verticalScrollBar().width() if self.verticalScrollBar().isVisible() else 0
        self.scroll_btn.move(
            self.width() - 42 - scrollbar_width - 8,
            self.height() - 42
        )
        if self.search_widget.isVisible():
            self._position_search_bar()

    def _find(self, backward: bool):
        query = self.search_input.text()
        if not query:
            return

        flags = QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0)
        cursor = self.textCursor()
        if backward and self._last_search_pos < 0:
            cursor.movePosition(QTextCursor.End)

        found = self.document().find(query, cursor, flags)
        if found.isNull():
            # Wrap around to the far end and try once more.
            cursor.movePosition(QTextCursor.End if backward else QTextCursor.Start)
            found = self.document().find(query, cursor, flags)

        if found.isNull():
            return

        self.setTextCursor(found)
        fmt = QTextCharFormat()
        fmt.setBackground(HIGHLIGHT_BG)
        fmt.setForeground(HIGHLIGHT_FG)
        selection = QTextEdit.ExtraSelection()
        selection.format = fmt
        selection.cursor = found
        self.setExtraSelections([selection])

        self._center_on_cursor()
        self._last_search_pos = found.position()
        self._disable_auto_scroll()

    def _search_prev(self):
        self._find(backward=True)

    def _search_next(self):
        self._find(backward=False)

    def _disable_auto_scroll(self):
        self._auto_scroll = False
        self._user_scrolled_up = True
        self.scroll_btn.show()

    def _on_scroll(self):
        bar = self.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 10

        self._auto_scroll = at_bottom
        self._user_scrolled_up = not at_bottom
        self.scroll_btn.setVisible(not at_bottom)

    def _on_range_changed(self, min_val, max_val):
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
        scrollbar.blockSignals(True)

        self.setTextCursor(QTextCursor(block))
        self.ensureCursorVisible()
        self._center_on_cursor()

        self._auto_scroll = False
        self._user_scrolled_up = True

        scrollbar.blockSignals(False)
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

    def append_row(self, text: str, background: QColor, entry):
        self._line_entries.append(entry)

        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.End)
        self._insert_row(cursor, text, background)

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
        scrollbar.blockSignals(True)
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

        self._auto_scroll = old_auto_scroll
        self._user_scrolled_up = old_user_scrolled_up

        scrollbar.blockSignals(False)

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
