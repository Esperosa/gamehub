# GameHub

Desktop aplikace v Pythonu (PySide6), která sdružuje více logických her do jednoho přehledného launcheru.

## Co v aplikaci je

- Plugin architektura her (`games/<hra>/plugin.py`)
- 9 integrovaných her:
  - `game2048`
  - `kenken`
  - `mastermind`
  - `nonogram`
  - `othello`
  - `piskvorky`
  - `simon`
  - `slitherlink`
  - `sudoku`
- Moderní UI + animované pozadí
- Build do `.exe` pro Windows

## Rychlý start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

## Struktura projektu

```text
run.py
hub/                # shell aplikace (okna, téma, widgety, loader pluginů)
games/              # jednotlivé hry jako pluginy
requirements.txt
```

## Přidání nové hry

1. Vytvoř složku `games/nazev_hry/`
2. Přidej `plugin.py`
3. V `plugin.py` exportuj proměnnou `plugin` kompatibilní s `hub.plugin_api.BaseGamePlugin`

## Build: one-file EXE (Windows)

```bash
.venv\Scripts\python -m pip install pyinstaller
.venv\Scripts\python -m PyInstaller --noconfirm --clean --onefile --windowed --name GameHub --icon hub\assets\brainhub.ico --add-data "games;games" --add-data "hub\assets;hub\assets" --hidden-import winsound --hidden-import numpy --hidden-import numba --hidden-import llvmlite --hidden-import pysat.solvers --hidden-import pysat.card run.py
```

Výstup:

```text
dist/GameHub.exe
```

## Poznámka

`dist/`, `.venv/` a další build/cache artefakty jsou záměrně ignorované v `.gitignore`.
