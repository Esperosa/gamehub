"""
Mastermind Game Plugin - Implements GamePlugin interface
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Add games/mastermind to path for imports
_this_dir = Path(__file__).resolve().parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

from hub.plugin_api import BaseGamePlugin, GameMeta

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


class MastermindPlugin(BaseGamePlugin):
    """Plugin class for Mastermind game."""
    
    meta = GameMeta(
        id="mastermind",
        name="Mastermind",
        description="Uhádněte tajný barevný kód pomocí logické dedukce",
        version="1.0.0",
        author="GameHub",
        graphic_text="● ● ● ●",
    )
    
    def create_widget(self, parent=None) -> "QWidget":
        """Create and return the game widget."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("mastermind_ui", _this_dir / "ui.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["mastermind_ui"] = module
        spec.loader.exec_module(module)
        return module.MastermindWidget(parent)


# Export plugin instance (required by plugin loader)
plugin = MastermindPlugin()
