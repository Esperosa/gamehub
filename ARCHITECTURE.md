# ARCHITECTURE

## 1. Přehled

GameHub je desktop aplikace postavená na `PySide6` s pluginovým loadingem her ze složky `games/`.
Každá hra je izolovaná ve své složce a může mít vlastní `engine`, `solver` a `ui`.

## 2. Struktura projektu

```text
run.py
hub/
  app.py
  main_window.py
  plugin_loader.py
  plugin_api.py
  layer_loader.py
  widgets/
games/
  <game_name>/
    plugin.py
    engine.py
    solver.py (volitelné)
    ui.py
    engine/__init__.py (layer re-export)
    solver/__init__.py (layer re-export)
    ui/__init__.py (layer re-export)
tests/
```

## 3. Jak hub načítá pluginy

Vstupní tok:

1. `run.py` volá `hub.app.main()`.
2. `hub.app.main()` vytvoří `QApplication` a `MainWindow`.
3. `MainWindow._reload_plugins()` volá `discover_plugins()` z `hub/plugin_loader.py`.

`discover_plugins(games_dir)`:

1. Projde složky v `games/`.
2. V každé složce hledá `plugin.py`.
3. `plugin.py` načte přes `importlib`.
4. Vyžaduje entrypoint `manifest: PluginManifest`.
5. Manifest validuje přes `validate_manifest()` (`hub/plugin_api.py`).
6. Vrací `LoadedPlugin(manifest=..., folder=...)`.

## 4. Lifecycle hry

Lifecycle hooky definuje `GameLifecycle` (`hub/plugin_api.py`):

- `on_activate()`
- `on_deactivate()`
- `dispose()`

Volání lifecycle v `MainWindow`:

1. `open_plugin()`:
   - vytvoří widget přes `plugin.create_widget(parent=page)`,
   - po mountu volá `on_activate()`.
2. Při návratu domů / přepnutí hry / zavření okna:
   - `_teardown_active_plugin()` volá `on_deactivate()`,
   - pak volá `dispose()`,
   - widget odpojí ze stacku.

## 5. Kde je engine / solver / ui

Každá hra typicky obsahuje:

- `engine.py` - pravidla, stav hry, validace, generátor.
- `solver.py` nebo solver logika v `engine.py` - hinty/AI/řešení.
- `ui.py` - Qt widgety, interakce, render.

Kvůli balení a stabilnímu import graphu jsou často přítomné vrstvy:

- `engine/__init__.py`
- `solver/__init__.py`
- `ui/__init__.py`

Tyto moduly používají `hub/layer_loader.py` (`load_module_from_file`, `reexport_public`) pro bezpečný re-export runtime vrstvy.

## 6. Jak přidat novou hru

## 6.1 Kroky

1. Vytvoř složku `games/mygame/`.
2. Přidej minimálně:
   - `plugin.py`
   - `ui.py`
   - `engine.py` (doporučeno)
3. Přidej metadata (`id`, `name`, `description`, `graphic_text` nebo `icon_path`).
4. Ověř načtení přes:
   - `python tester.py --plugins-only`
5. Přidej testy do `tests/` nebo `games/mygame/tester.py` (`run_audit()`).

## 6.2 Šablona (manifest entrypoint, doporučeno)

```python
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QWidget

from hub.layer_loader import load_module_from_file
from hub.plugin_api import PluginManifest

_THIS_DIR = Path(__file__).resolve().parent
_UI_MODULE_NAME = f"game_plugins.{_THIS_DIR.name}.ui"


def _create_widget(parent: Optional[QWidget] = None) -> QWidget:
    module = load_module_from_file(_UI_MODULE_NAME, _THIS_DIR / "ui" / "__init__.py")
    widget_factory = getattr(module, "MyGameWidget", None)
    if widget_factory is None:
        raise ImportError("Cannot load MyGameWidget from UI module")
    return widget_factory(parent)


manifest = PluginManifest(
    id="mygame",
    name="My Game",
    description="Krátký popis hry",
    version="0.1.0",
    author="Your Name",
    graphic_text="★",
    create_widget=_create_widget,
)
```

## 7. Poznámky k packagingu

- `GameHub_allmods.spec` sbírá modulový strom `hub` a všech `games.*`.
- Build skripty:
  - Windows: `scripts/build_windows.ps1`
  - Linux: `scripts/build_linux.sh`
- GitHub Release workflow: `.github/workflows/release.yml`
