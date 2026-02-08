from __future__ import annotations

from hub.plugin_api import PluginManifest, resolve_i18n_text, validate_manifest


def _dummy_widget_factory(parent=None):
    from PySide6.QtWidgets import QWidget

    return QWidget(parent)


def test_resolve_i18n_text_prefers_exact_language() -> None:
    value = resolve_i18n_text({"cs": "Ahoj", "en": "Hello"}, "en", "Fallback")
    assert value == "Hello"


def test_resolve_i18n_text_falls_back_to_default() -> None:
    value = resolve_i18n_text({"cs": "Ahoj"}, "de", "Fallback")
    assert value == "Ahoj"


def test_validate_manifest_accepts_i18n_maps() -> None:
    manifest = PluginManifest(
        id="demo",
        name="Demo",
        description="Demo plugin",
        create_widget=_dummy_widget_factory,
        graphic_text="★",
        name_i18n={"cs": "Demo", "en": "Demo"},
        description_i18n={"cs": "Ukázka", "en": "Demo"},
    )
    assert validate_manifest(manifest) == []


def test_validate_manifest_rejects_invalid_i18n_map() -> None:
    manifest = PluginManifest(
        id="demo",
        name="Demo",
        description="Demo plugin",
        create_widget=_dummy_widget_factory,
        graphic_text="★",
        name_i18n={"cs": ""},
    )
    errors = validate_manifest(manifest)
    assert any("name_i18n" in e for e in errors)
