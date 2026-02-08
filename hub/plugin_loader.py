from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

from hub.plugin_api import (
    PluginManifest,
    validate_manifest,
)


@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    folder: Path


_log = logging.getLogger(__name__)


def _manifest_from_module(module: object, plugin_label: str) -> PluginManifest | None:
    manifest_obj = getattr(module, "manifest", None)
    if manifest_obj is None:
        _log.error("[%s] missing entrypoint 'manifest: PluginManifest'.", plugin_label)
        return None
    if not isinstance(manifest_obj, PluginManifest):
        _log.error("[%s] 'manifest' is present but is not PluginManifest.", plugin_label)
        return None
    return manifest_obj


def discover_plugins(games_dir: Path) -> List[LoadedPlugin]:
    """Discover game plugins under `games_dir`.

    Required entrypoint:
      - module `manifest: PluginManifest`
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
        plugin_label = f"{item.name}/plugin.py"

        try:
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)
            if spec is None or spec.loader is None:
                _log.error("[%s] failed to create import spec.", plugin_label)
                continue

            module = importlib.util.module_from_spec(spec)

            # Allow plugin-local imports:
            sys.path.insert(0, str(item))
            try:
                spec.loader.exec_module(module)  # type: ignore[attr-defined]
            finally:
                if sys.path and sys.path[0] == str(item):
                    sys.path.pop(0)

            manifest = _manifest_from_module(module, plugin_label)
            if manifest is None:
                continue

            errors = validate_manifest(manifest)
            if errors:
                _log.error("[%s] invalid manifest: %s", plugin_label, "; ".join(errors))
                continue

            loaded.append(LoadedPlugin(manifest=manifest, folder=item))

        except Exception as exc:
            _log.exception("[%s] failed to load plugin: %r", plugin_label, exc)
            continue

    return loaded
