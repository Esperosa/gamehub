# Sudoku 16x16 - performance benchmark (hard)

Datum měření: 2026-02-08  
Cíl: porovnat všechny reálně zkoušené přístupy pro generování `16x16 hard` a nechat v kódu nejrychlejší variantu.

## Testovací scénář

- Varianta: `Sudoku 16x16`, obtížnost `hard`
- Počet generování: `30` puzzle na běh
- Seed range: `2026020800..2026020829`
- Metriky: `avg`, `median`, `p95`, `min`, `max`, plus rozptyl clue (`empty` count)
- Všechny běhy proběhly ve stejném lokálním prostředí na stejné větvi/PC.

## Testované přístupy

### 1) Baseline (commit `744738e`)

- Stav po bitmask solver optimalizacích.
- Uniqueness timeout pro `16x16 hard`: `0.08s`.

Výsledek:

- `avg 1.7646s`
- `median 0.7817s`
- `p95 7.7887s`
- `min 0.0539s`
- `max 8.5037s`

### 2) Experiment: kvóty + symetrické odebírání clue (necommitováno)

- Přidané row/col/box minima během carvingu.
- Preferované symetrické odebírání buněk.

Výsledek:

- `avg 2.4941s`
- `median 0.6045s`
- `p95 6.9217s`
- `min 0.0557s`
- `max 7.7026s`

Poznámka:

- Lepší typická středová hodnota, ale horší průměr (častější drahé outliery).
- Celkově pomalejší než baseline.

### 3) Experiment: předpočítané row/col indexy v solver rekurzi (necommitováno)

- Eliminace části `//` a `%` lookupů v hot path.

Výsledek:

- `avg 1.8792s`
- `median 0.8570s`
- `p95 7.8014s`
- `min 0.0513s`
- `max 8.7418s`

Poznámka:

- V praxi bez zisku; celkově mírně horší než baseline.

### 4) Final: zkrácení uniqueness timeoutu (commit `114e05b`)

- Změna `games/sudoku/engine.py`: `16x16 hard` timeout `0.08s -> 0.05s`.

Výsledek:

- `avg 1.4938s`
- `median 0.7382s`
- `p95 5.0858s`
- `min 0.0509s`
- `max 5.6208s`

Kvalita/hustota clue (kontrolní běh):

- Baseline `avg_empty 144.8`, `min/max 137/152`
- Final `avg_empty 144.57`, `min/max 137/152`

## Závěr

Nejrychlejší z testovaných přístupů je commit `114e05b` (timeout `0.05s`), který je nyní aktivní v kódu.

- Zlepšení proti baseline `744738e`:
- `avg -16.0%`
- `median -5.6%`
- `max -33.9%`
- `p95 -34.7%`

## Reprodukce

Benchmark skript:

```bash
python scripts/benchmark_sudoku_generation.py --size 16 --difficulty hard --count 30 --seed-start 2026020800
```

Porovnání proti jinému commitu:

```bash
git worktree add --detach ..\gamehub_baseline 744738e
cd ..\gamehub_baseline
python scripts/benchmark_sudoku_generation.py --size 16 --difficulty hard --count 30 --seed-start 2026020800
```

Po měření worktree odstranit:

```bash
git -C ..\gamehub_16dc1d64 worktree remove --force ..\gamehub_baseline
```

