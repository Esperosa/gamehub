"""Sudoku plugin manifest."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from hub.plugin_api import PluginManifest

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))


def _create_widget(parent=None) -> "QWidget":
    spec = importlib.util.spec_from_file_location("sudoku_ui", _THIS_DIR / "ui" / "__init__.py")
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load sudoku UI module.")
    module = importlib.util.module_from_spec(spec)
    sys.modules["sudoku_ui"] = module
    spec.loader.exec_module(module)
    return module.SudokuWidget(parent)


manifest = PluginManifest(
    id="sudoku",
    name="Sudoku",
    description="Klasické sudoku varianty 4×4, 6×6, 9×9 a 16×16",
    name_i18n={
        "cs": "Sudoku",
        "en": "Sudoku",
    },
    description_i18n={
        "cs": "Klasické sudoku varianty 4×4, 6×6, 9×9 a 16×16",
        "en": "Classic Sudoku variants 4x4, 6x6, 9x9 and 16x16",
    },
    version="1.0.0",
    author="GameHub",
    graphic_text="1 2 3",
    create_widget=_create_widget,
)
