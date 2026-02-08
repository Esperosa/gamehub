from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from PySide6.QtWidgets import QWidget

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
