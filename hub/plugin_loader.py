from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from hub.plugin_api import (
    GamePlugin,
    ManifestBackedPlugin,
    PluginManifest,
    validate_manifest,
)


@dataclass
class LoadedPlugin:
    plugin: GamePlugin
    folder: Path


_log = logging.getLogger(__name__)


def _manifest_from_legacy_plugin(plugin_obj: object, plugin_label: str) -> Optional[PluginManifest]:
    meta = getattr(plugin_obj, "meta", None)
    if meta is None:
        _log.error("[%s] missing meta on legacy plugin object.", plugin_label)
        return None

    create_widget = getattr(plugin_obj, "create_widget", None)
    if not callable(create_widget):
        _log.error("[%s] missing create_widget() on legacy plugin object.", plugin_label)
        return None

    return PluginManifest(
        id=str(getattr(meta, "id", "")),
        name=str(getattr(meta, "name", "")),
        description=str(getattr(meta, "description", "")),
        version=str(getattr(meta, "version", "0.1.0")),
        author=str(getattr(meta, "author", "")),
        icon_path=getattr(meta, "icon_path", None),
        graphic_text=getattr(meta, "graphic_text", None),
        create_widget=create_widget,
        default_settings=getattr(plugin_obj, "default_settings", None),
        settings_schema=getattr(plugin_obj, "settings_schema", None),
    )


def _manifest_from_module(module: object, plugin_label: str) -> Optional[PluginManifest]:
    manifest_obj = getattr(module, "manifest", None)
    if manifest_obj is not None:
        if isinstance(manifest_obj, PluginManifest):
            return manifest_obj
        _log.error("[%s] 'manifest' is present but is not PluginManifest.", plugin_label)
        return None

    get_manifest = getattr(module, "get_manifest", None)
    if get_manifest is not None:
        if not callable(get_manifest):
            _log.error("[%s] 'get_manifest' exists but is not callable.", plugin_label)
            return None
        try:
            manifest_obj = get_manifest()
        except Exception as exc:
            _log.exception("[%s] get_manifest() failed: %r", plugin_label, exc)
            return None
        if not isinstance(manifest_obj, PluginManifest):
            _log.error("[%s] get_manifest() did not return PluginManifest.", plugin_label)
            return None
        return manifest_obj

    # Backward compatibility: legacy `plugin` object.
    plugin_obj = getattr(module, "plugin", None)
    if plugin_obj is None:
        _log.error("[%s] missing entrypoint (expected manifest/get_manifest/plugin).", plugin_label)
        return None

    _log.warning("[%s] uses legacy `plugin` entrypoint. Prefer PluginManifest.", plugin_label)
    return _manifest_from_legacy_plugin(plugin_obj, plugin_label)


def discover_plugins(games_dir: Path) -> List[LoadedPlugin]:
    """Discover game plugins under `games_dir`.

    Stable entrypoint:
      - module `manifest: PluginManifest`, or
      - module `get_manifest() -> PluginManifest`
    Legacy fallback:
      - module `plugin` object with `.meta` and `.create_widget()`
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

            plugin_obj: GamePlugin = ManifestBackedPlugin(manifest)
            loaded.append(LoadedPlugin(plugin=plugin_obj, folder=item))

        except Exception as exc:
            _log.exception("[%s] failed to load plugin: %r", plugin_label, exc)
            continue

    return loaded
