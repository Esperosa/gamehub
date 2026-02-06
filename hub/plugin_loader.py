from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from hub.plugin_api import GamePlugin


@dataclass
class LoadedPlugin:
    plugin: GamePlugin
    folder: Path


def discover_plugins(games_dir: Path) -> List[LoadedPlugin]:
    """Discover game plugins under `games_dir`.

    A plugin is a folder containing `plugin.py` exporting `plugin` object.
    """
    games_dir = games_dir.resolve()
    if not games_dir.exists():
        return []

    loaded: List[LoadedPlugin] = []

    for item in sorted(games_dir.iterdir()):
        if not item.is_dir():
            continue

        plugin_file = item / "plugin.py"
        if not plugin_file.exists():
            continue

        module_name = f"game_plugins.{item.name}"

        try:
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)

            # Allow plugin-local imports:
            sys.path.insert(0, str(item))
            try:
                spec.loader.exec_module(module)  # type: ignore[attr-defined]
            finally:
                if sys.path and sys.path[0] == str(item):
                    sys.path.pop(0)

            plugin_obj: Optional[GamePlugin] = getattr(module, "plugin", None)
            if plugin_obj is None:
                continue

            meta = getattr(plugin_obj, "meta", None)
            create_widget = getattr(plugin_obj, "create_widget", None)
            if meta is None or create_widget is None:
                continue

            loaded.append(LoadedPlugin(plugin=plugin_obj, folder=item))

        except Exception:
            # Broken plugin -> skip
            continue

    return loaded
