"""Nonogram plugin manifest."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from hub.layer_loader import load_module_from_file
from hub.plugin_api import PluginManifest

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


_THIS_DIR = Path(__file__).resolve().parent
_UI_MODULE_NAME = f"game_plugins.{_THIS_DIR.name}.ui"


def _create_widget(parent=None) -> "QWidget":
    module = load_module_from_file(_UI_MODULE_NAME, _THIS_DIR / "ui" / "__init__.py")
    widget_factory = getattr(module, "NonogramWidget", None)
    if widget_factory is None:
        raise ImportError("Cannot load NonogramWidget from UI module.")
    return widget_factory(parent)


manifest = PluginManifest(
    id="nonogram",
    name="Nonogram",
    description="Logická hra - vyplňuj políčka podle číselných indicií a odhal obrázek",
    version="1.0.0",
    author="GameHub",
    graphic_text="█ ▄ █",
    create_widget=_create_widget,
)
