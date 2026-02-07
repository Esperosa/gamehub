"""
2048 Game Plugin - Implements GamePlugin interface
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Add games/game2048 to path for imports
_this_dir = Path(__file__).resolve().parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

from hub.plugin_api import BaseGamePlugin, GameMeta

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


class Game2048Plugin(BaseGamePlugin):
    """Plugin class for 2048 game."""
    
    meta = GameMeta(
        id="game2048",
        name="2048",
        description="Klasická posuvná hra - spojujte dlaždice a dosáhněte 2048!",
        version="1.0.0",
        author="GameHub",
        graphic_text="2048",
    )
    
    def create_widget(self, parent=None) -> "QWidget":
        """Create and return the game widget."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("game2048_ui", _this_dir / "ui" / "__init__.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["game2048_ui"] = module
        spec.loader.exec_module(module)
        return module.Game2048Widget(parent)


# Export plugin instance (required by plugin loader)
plugin = Game2048Plugin()

