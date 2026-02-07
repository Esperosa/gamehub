"""
Sudoku Game Plugin - Implements GamePlugin interface
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Add games/sudoku to path for imports
_this_dir = Path(__file__).resolve().parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

from hub.plugin_api import BaseGamePlugin, GameMeta

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


class SudokuPlugin(BaseGamePlugin):
    """Plugin class for Sudoku game."""
    
    meta = GameMeta(
        id="sudoku",
        name="Sudoku",
        description="Klasické sudoku s volitelnou velikostí a obtížností",
        version="1.0.0",
        author="GameHub",
        graphic_text="1 2 3",
    )
    
    def create_widget(self, parent=None) -> "QWidget":
        """Create and return the game widget."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("sudoku_ui", _this_dir / "ui" / "__init__.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["sudoku_ui"] = module  # Required for proper module loading
        spec.loader.exec_module(module)
        return module.SudokuWidget(parent)


# Export plugin instance (required by plugin loader)
plugin = SudokuPlugin()

