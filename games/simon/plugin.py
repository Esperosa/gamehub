"""
Simon Says Game Plugin - Implements GamePlugin interface
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Add games/simon to path for imports
_this_dir = Path(__file__).resolve().parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

from hub.plugin_api import BaseGamePlugin, GameMeta

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


class SimonPlugin(BaseGamePlugin):
    """Plugin class for Simon Says memory game."""
    
    meta = GameMeta(
        id="simon",
        name="Simon",
        description="Zapamatuj si a zopakuj světelnou sekvenci",
        version="1.0.0",
        author="GameHub",
        graphic_text="◢◣\n◥◤",
    )
    
    def create_widget(self, parent=None) -> "QWidget":
        """Create and return the game widget."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("simon_ui", _this_dir / "ui.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["simon_ui"] = module
        spec.loader.exec_module(module)
        return module.SimonWidget(parent)


# Export plugin instance (required by plugin loader)
plugin = SimonPlugin()
