from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from hub.plugin_api import BaseGamePlugin, GameMeta

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


_this_dir = Path(__file__).resolve().parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))


class PiskvorkyPlugin(BaseGamePlugin):
    meta = GameMeta(
        id="piskvorky",
        name="Piškvorky",
        description="Klasické piškvorky na různých deskách s AI botem.",
        version="0.1.0",
        author="GameHub",
        graphic_text="✕ ◯ ✕",
    )

    def create_widget(self, parent=None) -> "QWidget":
        import importlib.util

        spec = importlib.util.spec_from_file_location("piskvorky_ui", _this_dir / "ui" / "__init__.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["piskvorky_ui"] = module
        spec.loader.exec_module(module)
        return module.PiskvorkyWidget(parent=parent)


plugin = PiskvorkyPlugin()
