from __future__ import annotations

import sys
from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from hub.main_window import MainWindow
from hub.theme import apply_theme


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("BrainHub")
    app.setOrganizationName("BrainHub")

    # App icon for taskbar/window and runtime UI.
    icon_file = Path(__file__).resolve().parent / "assets" / "brainhub.png"
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    apply_theme(app)

    win = MainWindow(app=app)
    if icon_file.exists():
        win.setWindowIcon(QIcon(str(icon_file)))
    win.show()

    sys.exit(app.exec())
