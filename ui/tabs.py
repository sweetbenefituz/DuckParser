from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget,
    QLabel, QGraphicsOpacityEffect, QFrame, QTabBar, QMenu
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtGui import QPixmap, QPainter, QPainterPath
from localization.localization_manager import get_localization, tr
import os
import random

# Filter tab order; index maps straight to the level name.
FILTER_LEVELS = ("ALL", "ERROR", "WARNING")
FILTER_LABEL_KEYS = ("tab_all", "tab_error", "tab_warning")


class RoundLabel(QLabel):
    _click_count = 0  # Class variable to persist across instances

    def __init__(self, pixmap_path: str, size: int):
        super().__init__()
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)

        if not os.path.exists(pixmap_path):
            return

        scaled = QPixmap(pixmap_path).scaled(
            size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )

        rounded = QPixmap(size, size)
        rounded.fill(Qt.transparent)

        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        painter.drawPixmap((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
        painter.end()

        self.setPixmap(rounded)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            RoundLabel._click_count += 1
            self._show_quack_notification(RoundLabel._click_count % 5 == 0)
        super().mousePressEvent(event)

    def _show_quack_notification(self, is_special: bool):
        if is_special:
            facts = tr("duck_facts")
            text = random.choice(facts) if isinstance(facts, list) and facts else "Quack! 🦆"
            duration = 5000
        else:
            text = "Quack!"
            duration = 1500

        quack_label = QLabel(text, self.window())
        quack_label.setObjectName("QuackLabel")
        quack_label.adjustSize()

        # Sit to the LEFT of the duck, clamped inside the window.
        local_pos = self.window().mapFromGlobal(self.mapToGlobal(self.rect().center()))
        x_pos = max(10, local_pos.x() - self.width() // 2 - quack_label.width() - 10)
        quack_label.move(x_pos, local_pos.y() - quack_label.height() // 2)
        quack_label.show()

        effect = QGraphicsOpacityEffect(quack_label)
        quack_label.setGraphicsEffect(effect)

        anim = QPropertyAnimation(effect, b"opacity", quack_label)
        anim.setDuration(duration)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InQuad)
        anim.finished.connect(quack_label.deleteLater)
        anim.start()


class FilterTabs(QWidget):
    def __init__(self):
        super().__init__()
        get_localization().language_changed.connect(self._update_translations)
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 0)
        main_layout.setSpacing(0)

        # Top row: filter tabs and duck icon
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)

        self.filter_tabs = QTabWidget()
        self.filter_tabs.setObjectName("FilterTabs")
        for key in FILTER_LABEL_KEYS:
            self.filter_tabs.addTab(QWidget(), tr(key))

        top_layout.addWidget(self.filter_tabs)
        top_layout.addStretch()

        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ico", "85x85.jpg")
        self.logo_label = RoundLabel(logo_path, 50)
        self.logo_label.setObjectName("LogoLabel")
        top_layout.addWidget(self.logo_label)
        top_layout.addSpacing(10)

        main_layout.addLayout(top_layout)

        self.separator = QFrame()
        self.separator.setObjectName("FilterSeparator")
        self.separator.setFrameShape(QFrame.HLine)
        self.separator.setFixedHeight(2)
        main_layout.addWidget(self.separator)

        # Bottom row: file tabs and clear button
        self.file_tabs = QTabWidget()
        self.file_tabs.setObjectName("FileTabs")

        self.file_tab_bar = FileTabBar()
        self.file_tabs.setTabBar(self.file_tab_bar)
        self.file_tabs.addTab(QWidget(), tr("tab_all"))

        self.clear_btn = QPushButton(tr("btn_clear_tab"))
        self.clear_btn.setObjectName("ClearButton")
        self.file_tabs.setCornerWidget(self.clear_btn, Qt.TopRightCorner)

        main_layout.addWidget(self.file_tabs)

    def _update_translations(self):
        for i, key in enumerate(FILTER_LABEL_KEYS):
            self.filter_tabs.setTabText(i, tr(key))
        self.file_tabs.setTabText(0, tr("tab_all"))
        self.clear_btn.setText(tr("btn_clear_tab"))


class FileTabBar(QTabBar):
    open_path_requested = Signal(int)

    def __init__(self):
        super().__init__()
        self.setMovable(True)
        self.setTabsClosable(True)  # Qt draws and wires the close buttons

    def tabInserted(self, index):
        if index == 0:
            self.setTabButton(0, QTabBar.RightSide, None)  # the "All" tab never closes

    def mousePressEvent(self, event):
        index = self.tabAt(event.pos())

        if index <= 0 or event.button() != Qt.RightButton:
            return super().mousePressEvent(event)

        menu = QMenu(self)
        open_action = menu.addAction(tr("ctx_open_path"))
        close_action = menu.addAction(tr("ctx_close"))
        action = menu.exec(event.globalPos())

        if action == open_action:
            self.open_path_requested.emit(index)
        elif action == close_action:
            self.tabCloseRequested.emit(index)
