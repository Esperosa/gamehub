"""2048 plugin manifest."""
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
    spec = importlib.util.spec_from_file_location("game2048_ui", _THIS_DIR / "ui" / "__init__.py")
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load game2048 UI module.")
    module = importlib.util.module_from_spec(spec)
    sys.modules["game2048_ui"] = module
    spec.loader.exec_module(module)
    return module.Game2048Widget(parent)


manifest = PluginManifest(
    id="game2048",
    name="2048",
    description="Klasická posuvná hra - spojujte dlaždice a dosáhněte 2048!",
    name_i18n={
        "cs": "2048",
        "en": "2048",
    },
    description_i18n={
        "cs": "Klasická posuvná hra - spojujte dlaždice a dosáhněte 2048!",
        "en": "Classic sliding tile game - merge tiles and reach 2048",
    },
    version="1.0.0",
    author="GameHub",
    graphic_text="2048",
    create_widget=_create_widget,
)
