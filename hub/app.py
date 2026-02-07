from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from hub.main_window import MainWindow
from hub.theme import apply_theme
from hub.widgets.background import prepare_background_runtime

# Keep print module in static import graph so one-file PyInstaller build
# includes it even though game UIs are loaded dynamically from plugins.
from hub import printing as _printing  # noqa: F401

# Keep shared dynamic loader in static import graph for packaged plugin UI layers.
from hub import layer_loader as _layer_loader  # noqa: F401


def _configure_runtime_logging() -> None:
    if getattr(sys, "frozen", False):
        local_app = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        log_dir = local_app / "BrainHub" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "startup.log"
        logging.basicConfig(
            level=logging.INFO,
            filename=str(log_file),
            filemode="a",
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        logging.getLogger(__name__).info("=== BrainHub startup (frozen) ===")
    else:
        logging.basicConfig(level=logging.INFO)


def main() -> None:
    _configure_runtime_logging()
    prepare_background_runtime()

    # Force Qt dialogs so app stylesheet applies consistently across systems.
    QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, True)
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
