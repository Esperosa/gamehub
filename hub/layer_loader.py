from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Dict, List


def load_module_from_file(module_name: str, file_path: Path) -> ModuleType:
    """Load a module from file path under a stable unique module name."""
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create import spec for {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def reexport_public(module: ModuleType, target_globals: Dict[str, object]) -> List[str]:
    """Copy public symbols from module to target namespace and return __all__."""
    exported = [name for name in vars(module).keys() if not name.startswith("_")]
    for name in exported:
        target_globals[name] = getattr(module, name)
    return exported
