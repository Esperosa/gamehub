from __future__ import annotations

from pathlib import Path

from hub.layer_loader import load_module_from_file, reexport_public

_GAME_DIR = Path(__file__).resolve().parents[1]
_MODULE = load_module_from_file(f"{_GAME_DIR.name}_solver_layer", _GAME_DIR / "ai.py")

__all__ = reexport_public(_MODULE, globals())
