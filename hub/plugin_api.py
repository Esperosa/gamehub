from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

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


WidgetFactory = Callable[[Optional[QWidget]], QWidget]
SettingsFactory = Callable[[], Dict[str, Any]]


@runtime_checkable
class GameLifecycle(Protocol):
    """Lifecycle hooks for mounted game widgets."""

    def on_activate(self) -> None: ...
    def on_deactivate(self) -> None: ...
    def dispose(self) -> None: ...


class LifecycleHooks:
    """No-op lifecycle defaults that game widgets can inherit."""

    def on_activate(self) -> None:
        return

    def on_deactivate(self) -> None:
        return

    def dispose(self) -> None:
        return


@dataclass(frozen=True)
class PluginManifest:
    """Stable plugin entrypoint contract for loader discovery."""

    id: str
    name: str
    description: str
    create_widget: WidgetFactory
    version: str = "0.1.0"
    author: str = ""
    icon_path: Optional[str] = None
    graphic_text: Optional[str] = None
    default_settings: Optional[SettingsFactory] = None
    settings_schema: Optional[SettingsFactory] = None


_PLUGIN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def validate_manifest(manifest: PluginManifest) -> List[str]:
    """Validate manifest. Returns list of user-facing errors."""
    errors: List[str] = []

    if not isinstance(manifest.id, str) or not manifest.id.strip():
        errors.append("missing or empty id")
    elif not _PLUGIN_ID_RE.fullmatch(manifest.id.strip()):
        errors.append("id contains unsupported characters (allowed: A-Z a-z 0-9 _ . -)")

    if not isinstance(manifest.name, str) or not manifest.name.strip():
        errors.append("missing or empty name")

    if not isinstance(manifest.description, str) or not manifest.description.strip():
        errors.append("missing or empty description")

    if not callable(manifest.create_widget):
        errors.append("missing create_widget callback")

    # Require at least one visual identifier for cards.
    if not manifest.icon_path and not manifest.graphic_text:
        errors.append("missing icon/graphic (set icon_path or graphic_text)")

    if manifest.default_settings is not None and not callable(manifest.default_settings):
        errors.append("default_settings must be callable")

    if manifest.settings_schema is not None and not callable(manifest.settings_schema):
        errors.append("settings_schema must be callable")

    return errors


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


class ManifestBackedPlugin(BaseGamePlugin):
    """Adapter that exposes a PluginManifest as legacy GamePlugin interface."""

    def __init__(self, manifest: PluginManifest):
        self._manifest = manifest
        self.meta = GameMeta(
            id=manifest.id,
            name=manifest.name,
            description=manifest.description,
            version=manifest.version,
            author=manifest.author,
            icon_path=manifest.icon_path,
            graphic_text=manifest.graphic_text,
        )

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        return self._manifest.create_widget(parent)

    def default_settings(self) -> Dict[str, Any]:
        if self._manifest.default_settings is None:
            return {}
        out = self._manifest.default_settings()
        return out if isinstance(out, dict) else {}

    def settings_schema(self) -> Dict[str, Any]:
        if self._manifest.settings_schema is None:
            return {}
        out = self._manifest.settings_schema()
        return out if isinstance(out, dict) else {}
