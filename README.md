# GameHub

<p align="center">
  <img src="hub/assets/brainhub.png" alt="GameHub logo" width="120" />
</p>

<p align="center">
  Desktop aplikace v Pythonu (PySide6), která sdružuje logické hry, AI moduly a tisk/PDF exporty do jednoho launcheru.
</p>

<p align="center">
  <a href="https://github.com/Esperosa/gamehub/releases"><img src="https://img.shields.io/github/v/release/Esperosa/gamehub?label=release&style=for-the-badge" alt="Latest release"></a>
  <a href="https://github.com/Esperosa/gamehub/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/Esperosa/gamehub/ci.yml?branch=main&label=ci&style=for-the-badge" alt="CI status"></a>
  <a href="https://github.com/Esperosa/gamehub/actions/workflows/codeql.yml"><img src="https://img.shields.io/github/actions/workflow/status/Esperosa/gamehub/codeql.yml?branch=main&label=codeql&style=for-the-badge" alt="CodeQL status"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-27c2ff?style=for-the-badge" alt="MIT license"></a>
  <a href="ARCHITECTURE.md"><img src="https://img.shields.io/badge/plugin%20api-manifest%20only-8f7dff?style=for-the-badge" alt="Plugin API"></a>
  <a href="docs/print_export_samples.md"><img src="https://img.shields.io/badge/print%2FPDF-ready-f4a93a?style=for-the-badge" alt="Print and PDF"></a>
</p>

<p align="center">
  <img src="docs/media/repo_hero.png" alt="GameHub hero" width="100%" />
</p>

## Ukázky Hraní

| Hub | Dialog Tisku | Náhled PDF |
|---|---|---|
| ![Ukázka Hubu](docs/media/clips/hub.webp) | ![Ukázka dialogu tisku](docs/media/clips/print_dialog.webp) | ![Ukázka náhledu PDF](docs/media/clips/pdf_preview.webp) |

| 2048 | KenKen | Mastermind |
|---|---|---|
| ![Ukázka 2048](docs/media/clips/game2048.webp) | ![Ukázka KenKen](docs/media/clips/kenken.webp) | ![Ukázka Mastermind](docs/media/clips/mastermind.webp) |

| Nonogram | Othello | Piskvorky |
|---|---|---|
| ![Ukázka Nonogram](docs/media/clips/nonogram.webp) | ![Ukázka Othello](docs/media/clips/othello.webp) | ![Ukázka Piškvorky](docs/media/clips/piskvorky.webp) |

| Simon | Slitherlink | Sudoku |
|---|---|---|
| ![Ukázka Simon](docs/media/clips/simon.webp) | ![Ukázka Slitherlink](docs/media/clips/slitherlink.webp) | ![Ukázka Sudoku](docs/media/clips/sudoku.webp) |

## Rychlé Odkazy

| Stažení | Rychlý start | Architektura | Tisk/PDF | Benchmarky | Bezpečnost | Pages |
|---|---|---|---|---|---|---|
| [Releases](https://github.com/Esperosa/gamehub/releases) | [Rychlý start](#rychlý-start) | [ARCHITECTURE.md](ARCHITECTURE.md) | [print_export_samples.md](docs/print_export_samples.md) | [benchmarks/README.md](benchmarks/README.md) | [SECURITY.md](SECURITY.md) | [`docs/index.html`](docs/index.html) |

## Implementace vs Knihovny

- Přehled co je autorská logika a co je delegované na knihovny: `docs/author_vs_libraries.md`
- Obsahuje tabulky po hrách + knihovnách a orientační graf odpovědností.

## Branding Repozitáře

- Social preview obrázek: `docs/media/social_preview.png`
- README hero obrázek: `docs/media/repo_hero.png`
- Pages landing stránka: `docs/index.html`
- Gameplay klipy (8s, WebP): `docs/media/clips/*.webp`
- Regenerace assetů: `python scripts/generate_repo_branding.py --output-dir docs/media`
- Regenerace gameplay klipu: `python scripts/generate_gameplay_clips.py --output-dir docs/media/clips --seconds 8 --fps 10 --width 1280 --height 720`
- Manuál pro repo branding: `docs/repository_branding.md`
- Publikace landing stránky: GitHub `Settings -> Pages`, source `main` + `/docs`

## Stažení

- Nejnovější stabilní build: [GitHub Releases](https://github.com/Esperosa/gamehub/releases)
- Windows: `GameHub_*_windows_x64.exe` (+ `.zip`)
- Linux (volitelné): `GameHub_*_linux_x86_64` (+ `.tar.gz`)
- Každý release obsahuje `SHA256SUMS.txt` pro ověření integrity.

## Funkce

- 9 logických her v jednom launcheru (`2048`, `KenKen`, `Mastermind`, `Nonogram`, `Othello`, `Piškvorky`, `Simon`, `Slitherlink`, `Sudoku`)
- Plugin-first architektura (`games/<hra>/plugin.py`)
- Oddělené vrstvy `engine / solver / ui` pro každou hru
- Tisk/PDF export pro `Sudoku`, `KenKen`, `Slitherlink`
- One-file release pipeline (Windows + Linux artefakty + SHA256)

## Jazyková Konzistence

- GitHub dokumentace je vedená `cs-first` (čeština jako hlavní jazyk).
- In-app přepínač jazyka je nyní záměrně vypnutý a ponechaný jako TODO komentář v `hub/main_window.py`.
- Cíl tohoto kola byl sjednotit jazyk především na GitHubu (README, šablony issue/PR, bezpečnostní dokumenty, landing page).

## Garance Solverů

| Hra | Co je garantováno | Jak je to ověřené |
|---|---|---|
| Sudoku | Generátor přijme odebrání čísla jen pokud nenašel alternativní řešení k referenčnímu řešení. | `games/sudoku/engine.py`, audit skript `scripts/audit_solver_claims.py` |
| Slitherlink | Generátor vrací puzzle jen pokud SAT uniqueness check vrátí právě 1 řešení. | `games/slitherlink/engine.py` |
| KenKen | Calcudoku generátor negarantuje unikátní řešení každého puzzle. | `games/kenken/engine.py`, audit report `docs/solver_claims_audit.md` |
| Nonogram | Generované puzzle má validní referenční řešení, unikátnost není tvrdě garantovaná. | `games/nonogram/engine.py`, audit report `docs/solver_claims_audit.md` |

## Podporované Platformy

| Platform | Stav | Artefakt v Releases |
|---|---|---|
| Windows x64 | testováno | `.exe`, `.zip` |
| Linux x86_64 | volitelné (best effort) | binárka, `.tar.gz` |

## Snímky Obrazovky

Aktuální screenshoty jsou generované z **lokální aktuální verze** přes `scripts/capture_screenshots.py`.
Každá hra je otevřená v hubu, rozehraná a pořízená ve stavu, kde jsou vidět všechny hlavní UI prvky.

Regenerace screenshotů:

```bash
.venv\Scripts\python scripts/capture_screenshots.py
```

Skript automaticky:
- otevře hub + všechny hry z aktuálního lokálního stromu,
- počká na dokončení async načítání puzzle,
- provede minimální rozehrání (hint/tah),
- ověří, že obrázky nejsou prázdné a mají validní rozměr.

Screenshoty dialogu tisku + ukázkové PDF exporty:

```bash
.venv\Scripts\python scripts/generate_print_assets.py --media-dir docs/media --sample-dir docs/samples
```

Branding hero/social preview assety:

```bash
.venv\Scripts\python scripts/generate_repo_branding.py --output-dir docs/media
```

Gameplay klipy (8s, Hub + hry + dialog tisku + náhled PDF):

```bash
.venv\Scripts\python scripts/generate_gameplay_clips.py --output-dir docs/media/clips --seconds 8 --fps 10 --width 1280 --height 720
```

| Hub | 2048 |
|---|---|
| ![Hub](docs/media/home.png) | ![2048](docs/media/game2048.png) |

| KenKen | Mastermind |
|---|---|
| ![KenKen](docs/media/kenken.png) | ![Mastermind](docs/media/mastermind.png) |

| Nonogram | Othello |
|---|---|
| ![Nonogram](docs/media/nonogram.png) | ![Othello](docs/media/othello.png) |

| Piškvorky | Simon |
|---|---|
| ![Piskvorky](docs/media/piskvorky.png) | ![Simon](docs/media/simon.png) |

| Slitherlink | Sudoku |
|---|---|
| ![Slitherlink](docs/media/slitherlink.png) | ![Sudoku](docs/media/sudoku.png) |

| Tisk Sudoku | Tisk KenKen | Tisk Slitherlink |
|---|---|---|
| ![Print Sudoku](docs/media/print_dialog_sudoku.png) | ![Print KenKen](docs/media/print_dialog_kenken.png) | ![Print Slitherlink](docs/media/print_dialog_slitherlink.png) |

## Ukázky PDF Exportu

Ukázkové PDF exporty layoutů `1/2/4/6/9` na stránku:

- Sudoku:
  - [layout 1](docs/samples/sudoku_layout_1.pdf), [layout 2](docs/samples/sudoku_layout_2.pdf), [layout 4](docs/samples/sudoku_layout_4.pdf), [layout 6](docs/samples/sudoku_layout_6.pdf), [layout 9](docs/samples/sudoku_layout_9.pdf)
- KenKen:
  - [layout 1](docs/samples/kenken_layout_1.pdf), [layout 2](docs/samples/kenken_layout_2.pdf), [layout 4](docs/samples/kenken_layout_4.pdf), [layout 6](docs/samples/kenken_layout_6.pdf), [layout 9](docs/samples/kenken_layout_9.pdf)
- Slitherlink:
  - [layout 1](docs/samples/slitherlink_layout_1.pdf), [layout 2](docs/samples/slitherlink_layout_2.pdf), [layout 4](docs/samples/slitherlink_layout_4.pdf), [layout 6](docs/samples/slitherlink_layout_6.pdf), [layout 9](docs/samples/slitherlink_layout_9.pdf)

## Licence a autor

- Licence: [MIT](LICENSE)
- Copyright: `© 2026 BeakOverPink (Esperosa)`
- Maintainer: [@Esperosa](https://github.com/Esperosa)
- Právní metadata: `LICENSE`, `NOTICE`

## Dokumentace

- `ARCHITECTURE.md` - načítání pluginů, lifecycle, vrstvy hry, template pro novou hru
- `CONTRIBUTING.md` - dev setup, testy, coding style, contribution workflow
- `CHANGELOG.md` - verze a změny
- `SECURITY.md` - pravidla pro soukromé hlášení zranitelností
- `CODE_OF_CONDUCT.md` - pravidla komunikace v repozitáři
- `docs/sudoku_generation_performance.md` - srovnání variant generování Sudoku 16x16 hard a výsledky benchmarku
- `docs/solver_claims_audit.md` - transparentní audit tvrzení o unikátnosti/řešitelnosti
- `docs/author_vs_libraries.md` - transparentní rozdělení autorské logiky vs role knihoven
- `docs/print_export_samples.md` - jak vznikají print dialog screenshoty a PDF sample exporty
- `docs/repository_branding.md` - jak regenerovat README hero/social preview assety
- `scripts/generate_gameplay_clips.py` - automatická tvorba 8s gameplay klipů pro README
- `scripts/audit_solver_claims.py` - reprodukovatelný audit claimů (Sudoku/KenKen/Nonogram)
- `.github/workflows/ci.yml` - CI kontrola (`ruff`, `mypy`, `pytest`)
- `.github/workflows/codeql.yml` - bezpečnostní code scanning (CodeQL)
- `benchmarks/README.md` - benchmark artefakty a jejich kontext

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

## Tester (audit run)

Pro jednotný audit všech her je k dispozici skript `tester.py`.

```bash
python tester.py
```

Volitelné režimy:

```bash
python tester.py --tests-only
python tester.py --plugins-only
python tester.py --adapters-only
```

`tester.py` automaticky:
- objeví pluginy v `games/`
- provede smoke kontrolu widgetu + lifecycle hooků
- spustí unit testy z `tests/`
- umí načíst i nové game-specific adaptéry přes `games/<game>/tester.py` s funkcí `run_audit()`

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
- Ukázky:
  - Print dialog screenshoty: `docs/media/print_dialog_*.png`
  - PDF sample exporty: `docs/samples/*_layout_{1,2,4,6,9}.pdf`
  - Reprodukce: `docs/print_export_samples.md`
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
  - Solver umí detekovat více řešení; aktuální Calcudoku generátor neprovádí tvrdou uniqueness smyčku.
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
  - `1..9` a pro větší varianty `A..Z`, `Delete/Backspace/0` smazání.
  - `Šipky` navigace.
  - Kolečko myši cykluje hodnoty.
  - Velikost (`4x4`, `6x6`, `9x9`, `16x16`), obtížnost, `Nápověda`, `Nová hra`, `Tisk/PDF`.
- Funkce:
  - Highlight konfliktů, průběh, konfety při dokončení.
  - Tisk/PDF čisté sudoku mřížky (černobílý A4 export).
- Agent/AI:
  - Backtracking solver s MRV + bitmask optimalizací.
  - Generátor vytváří puzzle z referenčního řešení a ověřuje alternativní řešení (unikátnost) s time-budgety.

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
3. V `plugin.py` exportuj `manifest = PluginManifest(...)`

## Sestavení Release Artefaktů

Windows:

```bash
.\scripts\build_windows.ps1 -Version v1.2.3
```

Linux:

```bash
bash ./scripts/build_linux.sh v1.2.3
```

Výstup (`dist/`):
- binární artefakt (`.exe` na Windows, ELF binárka na Linuxu)
- archiv (`.zip` nebo `.tar.gz`)
- checksum soubor (`SHA256SUMS_windows.txt` / `SHA256SUMS_linux.txt`)

Kompatibilní wrapper (legacy):

```bash
.\build_exe.ps1 -Version v1.2.3
```

## Publikace Release

1. Označ release tag:

```bash
git tag v1.2.3
git push origin v1.2.3
```

2. GitHub Actions workflow `.github/workflows/release.yml` automaticky:
- sestaví Windows + Linux artefakty,
- spočítá SHA256 checksumy,
- publikuje GitHub Release s přílohami (`.exe`, `.zip`, `.tar.gz`, `SHA256SUMS.txt`).

3. Ověření checksumu po stažení:

```bash
sha256sum -c SHA256SUMS.txt
```

## Reprodukovatelný Build

- Runtime/build závislosti jsou zamknuté v `requirements-lock.txt`.
- Zdroj pro lock: `requirements-build.in`.
- Regenerace locku:

```bash
.venv\Scripts\python -m piptools compile requirements-build.in --output-file requirements-lock.txt --generate-hashes --allow-unsafe
```

## Kvalita kódu

Instalace dev nástrojů:

```bash
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

Lint + formatter:

```bash
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format .
```

Typová kontrola (hub + plugin API + engine modely):

```bash
.venv\Scripts\python -m mypy
```

Pre-commit hooky:

```bash
.venv\Scripts\python -m pre_commit install
.venv\Scripts\python -m pre_commit run --all-files
```

## Poznámka

`dist/`, `.venv/` a další build/cache artefakty jsou záměrně ignorované v `.gitignore`.
