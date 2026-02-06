"""
KenKen Game Plugin - Implements GamePlugin interface
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Add games/kenken to path for imports
_this_dir = Path(__file__).resolve().parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

from hub.plugin_api import BaseGamePlugin, GameMeta

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


class KenKenPlugin(BaseGamePlugin):
    """Plugin class for KenKen game."""
    
    meta = GameMeta(
        id="kenken",
        name="KenKen",
        description="Logická hra s klecemi a aritmetickými operacemi",
        version="1.0.0",
        author="GameHub",
        graphic_text="6× 3+",
    )
    
    def create_widget(self, parent=None) -> "QWidget":
        """Create and return the game widget."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("kenken_ui", _this_dir / "ui.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["kenken_ui"] = module  # Required for proper module loading
        spec.loader.exec_module(module)
        return module.KenKenWidget(parent)


# Export plugin instance (required by plugin loader)
plugin = KenKenPlugin()
