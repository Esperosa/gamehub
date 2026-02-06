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
- Tisk/PDF generátor pro `sudoku`, `kenken`, `slitherlink`
- Build do `.exe` pro Windows

## Rychlý start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

## Tisk a PDF (Sudoku, KenKen, Slitherlink)

V hrách `sudoku`, `kenken` a `slitherlink` je tlačítko `Tisk/PDF` pro dávkové generování tisknutelných úloh.

- Co umí:
  - Vygenerovat více úloh najednou podle zvolených variant (velikost/obtížnost).
  - Export do `PDF` nebo přímý tisk na tiskárnu.
  - Rozložení `1 / 2 / 4 / 6 / 9` úloh na stránku.
  - Černobílý A4 výstup se silným černým rámem puzzle.
- Výchozí nastavení dialogu:
  - Počty variant jsou `0` (uživatel vyplní přesně co chce).
  - Výstup je defaultně `PDF`.
  - Cesta pro PDF je defaultně složka `Downloads`.
- Vzhled tisku:
  - Sudoku: čistá mřížka + zadané hodnoty.
  - KenKen: zvýrazněné klece a výraznější linky klecí.
  - Slitherlink: výrazné tečky vrcholů + číselné indicie.

## Jak hry fungují

Níže je praktický přehled pravidel, ovládání a interní logiky (AI/solverů).

### 2048

- Cíl:
  - Spojováním stejných číselných dlaždic dosáhnout hodnoty `2048` (nebo pokračovat dál).
- Ovládání:
  - `Šipky` nebo `W/A/S/D` pro tah.
  - Tlačítka `Nová hra`, `AI Vyřešit`.
- Funkce:
  - Plynulé animace, skóre, výhra/prohra overlay.
- Agent/AI:
  - Expectimax solver (`games/game2048/solver.py`) s heuristikami (gradient/snake pattern, smoothness).
  - Akcelerace přes Numba, adaptivní hloubka hledání.

### KenKen

- Cíl:
  - Vyplnit mřížku čísly `1..N` bez opakování v řádcích/sloupcích a splnit podmínky klecí (`+ - * /`).
- Ovládání:
  - Klik na buňku.
  - `1..9` zadání hodnoty, `Delete/Backspace/0` smazání.
  - `Šipky` pohyb po buňkách.
  - Kolečko myši cykluje hodnoty.
  - Tlačítka velikosti `4x4..9x9`, `Nápověda`, `Nová hra`, `Tisk/PDF`.
- Funkce:
  - Generace puzzle na pozadí, validace, hint systém.
  - Dávkový černobílý tisk/PDF s layoutem na A4.
- Agent/AI:
  - Constraint solver s MRV heuristikou + propagace omezení.
  - Unikátnost řešení se ověřuje při generaci.
  - Výpočty jsou optimalizované (Numba fallback na čistý Python).

### Mastermind

- Cíl:
  - Uhodnout tajný barevný kód.
  - Černé kolíky = správná barva i pozice, bílé = správná barva špatná pozice.
- Ovládání:
  - Klik na slot a barvu, nebo klávesy `1..8` pro rychlé zadání.
  - `←/→` změna slotu, `Enter` potvrzení, `Delete/Backspace` smazání.
  - Tlačítka `Nápověda`, `Potvrdit`, `Nová hra`.
  - Nastavení obtížnosti a délky kódu.
- Funkce:
  - Různé počty barev a pokusů podle obtížnosti.
- Agent/AI:
  - Hint používá minimax-like strategii (`suggest_guess`) nad množinou kompatibilních kódů.

### Nonogram

- Cíl:
  - Vyplnit správné buňky podle čísel u řádků/sloupců a odhalit obrazec.
- Ovládání:
  - Levé tlačítko: vyplnit.
  - Pravé tlačítko: označit jako prázdné (`X`).
  - Drag funguje pro rychlé vyplnění/označení.
  - Tlačítka velikosti (`5x5`, `10x10`, `15x15`), obtížnosti, `Nápověda`, `Nová hra`.
- Funkce:
  - Vizuální zvýraznění, konfety při dokončení.
- Agent/AI:
  - Line solver + constraint propagation.
  - Hint vrací determinovatelný krok; při potřebě fallback na hlubší řešení.

### Othello (Reversi)

- Cíl:
  - Mít na konci partie více kamenů své barvy.
  - Otáčíš soupeřovy kameny uzavřením mezi své kameny v osmi směrech.
- Ovládání:
  - Klik na zvýrazněný legální tah.
  - Tlačítko `Nová hra`, přepínač obtížnosti.
- Funkce:
  - Automatické pass tahy, skóre, game-over overlay.
- Agent/AI:
  - Minimax s alpha-beta pruning.
  - Adaptivní hloubka podle fáze hry + hodnocení mobility, rohů, hran, parity.

### Piškvorky / Gomoku

- Cíl:
  - Udělat souvislou řadu:
  - `3x3 -> 3 v řadě`, `8x8 -> 4 v řadě`, `13x13 -> 5 v řadě`.
- Ovládání:
  - Klik do mřížky.
  - Přepínač velikosti a obtížnosti.
  - `Nová hra`.
  - U režimu `13x13` je aktivní otevření Swap2 (volby přes overlay tlačítka).
- Funkce:
  - Async výpočty tahu bota (UI se neblokuje).
  - Statistiky/rating.
- Agent/AI:
  - `easy`: jednoduchá heuristika, dělá chyby.
  - `medium`: lehký minimax/alpha-beta (mělké hledání).
  - `hard`: iterativní prohledávání + alpha-beta + transposition table.
  - Prioritizace okamžité výhry, bloků a forků.

### Simon

- Cíl:
  - Zapamatovat a zopakovat rostoucí sekvenci barev.
- Ovládání:
  - Klik na segmenty kruhu.
  - Přepínač obtížnosti (`easy/medium/hard`), `Zvuk`, `Nová hra`.
- Funkce:
  - Zvukové tóny, skóre, high-score, vizuální efekty.
  - Režimy enginu: `classic`, `reverse`, `speed`, `chaos` (v UI je standardně vystavená hlavně obtížnost).
- Agent/AI:
  - Není protivník-bot; logika je deterministický engine sekvencí.

### Slitherlink

- Cíl:
  - Nakreslit jednu uzavřenou smyčku podle číselných indicií.
- Ovládání:
  - Klik na hranu cykluje stav: `prázdná -> čára -> X -> prázdná`.
  - Tlačítka velikosti (`7x7`, `10x10`, `15x15`), obtížnosti, `Nápověda`, `Vyřešit`, `Vymazat`, `Nová hra`, `Tisk/PDF`.
- Funkce:
  - Načítání/generace puzzle na pozadí.
  - Auto-solve animace.
  - Tisk/PDF s výraznými tečkami vrcholů a čitelnými indiciemi.
- Agent/AI:
  - Hinty přes constraint propagation.
  - Plný solver přes SAT (`python-sat`) s kontrolou validní jediné smyčky.

### Sudoku

- Cíl:
  - Vyplnit mřížku čísly podle pravidel Sudoku.
- Ovládání:
  - Klik na buňku.
  - `1..9` zadání, `Delete/Backspace/0` smazání.
  - `Šipky` navigace.
  - Kolečko myši cykluje hodnoty.
  - Velikost (`3x3`, `6x6`, `9x9`), obtížnost, `Nápověda`, `Nová hra`, `Tisk/PDF`.
- Funkce:
  - Highlight konfliktů, průběh, konfety při dokončení.
  - Tisk/PDF čisté sudoku mřížky (černobílý A4 export).
- Agent/AI:
  - Backtracking solver s MRV heuristikou.
  - Generátor vytváří puzzle s ověřenou jednoznačností řešení.

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
.venv\Scripts\python -m PyInstaller --noconfirm --clean --onefile --windowed --name GameHub --icon hub\assets\brainhub.ico --add-data "games;games" --add-data "hub\assets;hub\assets" --hidden-import winsound --hidden-import numpy --hidden-import numba --hidden-import llvmlite --hidden-import pysat.solvers --hidden-import pysat.card --hidden-import hub.printing run.py
```

Výstup:

```text
dist/GameHub.exe
```

## Poznámka

`dist/`, `.venv/` a další build/cache artefakty jsou záměrně ignorované v `.gitignore`.
