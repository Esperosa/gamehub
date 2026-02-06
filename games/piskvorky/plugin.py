from __future__ import annotations

from PySide6.QtWidgets import QWidget

from hub.plugin_api import BaseGamePlugin, GameMeta
from ui import PiskvorkyWidget


class PiskvorkyPlugin(BaseGamePlugin):
    meta = GameMeta(
        id="piskvorky",
        name="Piškvorky",
        description="Klasické piškvorky na různých deskách s AI botem.",
        version="0.1.0",
        author="GameHub",
        graphic_text="✕ ◯ ✕",
    )

    def create_widget(self, parent=None) -> QWidget:
        return PiskvorkyWidget(parent=parent)


plugin = PiskvorkyPlugin()
