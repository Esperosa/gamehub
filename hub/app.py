from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QCoreApplication, QStandardPaths
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


_APP_NAME = "BrainHub"
_APP_ORG = "BrainHub"


def _ensure_app_identity() -> None:
    QCoreApplication.setApplicationName(_APP_NAME)
    QCoreApplication.setOrganizationName(_APP_ORG)


def _log_file_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not base:
        local_app = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        base = str(local_app / _APP_NAME)
    log_dir = Path(base) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "runtime.log"


def _configure_runtime_logging() -> None:
    _ensure_app_identity()
    log_file = _log_file_path()
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    logging.getLogger(__name__).info("=== BrainHub startup === frozen=%s log=%s", getattr(sys, "frozen", False), log_file)


def main() -> None:
    _configure_runtime_logging()
    prepare_background_runtime()

    # Force Qt dialogs so app stylesheet applies consistently across systems.
    QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, True)
    app = QApplication(sys.argv)
    app.setApplicationName(_APP_NAME)
    app.setOrganizationName(_APP_ORG)

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
