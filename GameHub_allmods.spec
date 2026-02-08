# -*- mode: python ; coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path(SPECPATH).resolve()
GAMES_DIR = ROOT / "games"
ICON_FILE = ROOT / "hub" / "assets" / "brainhub.ico"
ICON_ARG = [str(ICON_FILE)] if os.name == "nt" and ICON_FILE.exists() else None

base_hiddenimports = {
    "winsound",
    "numpy",
    "numba",
    "llvmlite",
    "pysat.solvers",
    "pysat.card",
}

def _runtime_module_filter(module_name: str) -> bool:
    # Exclude tests and optional visualization helpers that are not runtime dependencies.
    if ".test" in module_name:
        return False
    if module_name.endswith(".visualize"):
        return False
    return True

# Include every hub module because game UIs import hub modules dynamically.
hiddenimports = set(base_hiddenimports)
hiddenimports.update(collect_submodules("hub", filter=_runtime_module_filter))

# Include every module under games.<game> for all detected game folders.
for item in sorted(GAMES_DIR.iterdir()):
    if not item.is_dir():
        continue
    if not (item / "plugin.py").exists():
        continue
    hiddenimports.update(
        collect_submodules(f"games.{item.name}", filter=_runtime_module_filter)
    )

app_name = os.environ.get("GAMEHUB_EXE_NAME", "GameHub_allmods")


a = Analysis(
    ["run.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "games"), "games"),
        (str(ROOT / "hub" / "assets"), "hub/assets"),
    ],
    hiddenimports=sorted(hiddenimports),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_ARG,
)
