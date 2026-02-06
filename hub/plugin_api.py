from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Optional, Dict, Any

from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class GameMeta:
    id: str
    name: str
    description: str
    version: str = "0.1.0"
    author: str = ""
    icon_path: Optional[str] = None  # relative path inside plugin folder
    graphic_text: Optional[str] = None  # decorative text/symbols for card (e.g. "✕ ◯")


class GamePlugin(Protocol):
    meta: GameMeta

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget: ...
    def default_settings(self) -> Dict[str, Any]: ...
    def settings_schema(self) -> Dict[str, Any]: ...


class BaseGamePlugin:
    meta: GameMeta

    def default_settings(self) -> Dict[str, Any]:
        return {}

    def settings_schema(self) -> Dict[str, Any]:
        return {}
