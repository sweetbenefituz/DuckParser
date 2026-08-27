import os
import sys
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtGui import QIcon
from ui.main_window import MainWindow

ICON_PATH = os.path.join(os.path.dirname(__file__), "ico", "48x48.jpg")


class LogParserApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.main_window = MainWindow()
        self.setCentralWidget(self.main_window)
        self.resize(1100, 700)

        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        # Applies language, theme and window title, then reopens last session's files.
        self.main_window.restore_state()

    def closeEvent(self, event):
        self.main_window.stop_workers()  # tail threads would outlive the window otherwise
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = LogParserApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
