"""Piskvorky plugin manifest."""
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
    spec = importlib.util.spec_from_file_location("piskvorky_ui", _THIS_DIR / "ui" / "__init__.py")
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load piskvorky UI module.")
    module = importlib.util.module_from_spec(spec)
    sys.modules["piskvorky_ui"] = module
    spec.loader.exec_module(module)
    return module.PiskvorkyWidget(parent=parent)


manifest = PluginManifest(
    id="piskvorky",
    name="Piškvorky",
    description="Klasické piškvorky na různých deskách s AI botem.",
    name_i18n={
        "cs": "Piškvorky",
        "en": "Gomoku",
    },
    description_i18n={
        "cs": "Klasické piškvorky na různých deskách s AI botem.",
        "en": "Classic Gomoku on multiple board sizes with an AI bot",
    },
    version="0.1.0",
    author="GameHub",
    graphic_text="✕ ◯ ✕",
    create_widget=_create_widget,
)
