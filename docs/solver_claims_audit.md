# Solver Claims Audit

Datum auditu: `2026-02-08`  
Zdroj dat: `benchmarks/solver_claims_audit_2026-02-08.json`

Tento audit kontroluje, zda veřejná tvrzení o řešitelnosti/unikátnosti odpovídají reálnému chování aktuálního kódu.

## Metodika

- Deterministické seedy (`base-seed 20260208`)
- 20 vzorků na variantu
- Bounded time-budgety jen tam, kde by neomezený check způsoboval outliery
- Skript: `scripts/audit_solver_claims.py`

Spuštění:

```bash
python scripts/audit_solver_claims.py --samples 20 --base-seed 20260208 --output benchmarks/solver_claims_audit_2026-02-08.json
```

## Výsledky

### Sudoku

`method: alternative-solution probe`

| Size | Difficulty | Samples | Alternatives Found | Inconclusive Timeout |
|---|---|---:|---:|---:|
| 4 | medium | 20 | 0 | 0 |
| 6 | medium | 20 | 0 | 0 |
| 9 | medium | 20 | 0 | 0 |
| 16 | hard | 20 | 0 | 0 |

Interpretace:
- V auditovaném vzorku nebyla nalezena alternativní řešení.
- Tvrzení o uniqueness u Sudoku zůstává konzistentní s implementací.

### KenKen

`method: count_solutions(limit=2, timeout=0.8s)`

| Size | Samples | Unique | Multiple/Ambiguous | Count Timeout |
|---|---:|---:|---:|---:|
| 4 | 20 | 0 | 20 | 0 |
| 6 | 20 | 4 | 16 | 0 |
| 8 | 20 | 1 | 8 | 11 |

Interpretace:
- Calcudoku generátor negarantuje unikátní řešení.
- Dřívější obecné tvrzení "exactly one solution" bylo nepravdivé a bylo odstraněno.

### Nonogram

`method: solve_result(timeout=1.5s, detect_multiple=True)`

| Size | Samples | Unique | Multiple/Ambiguous | Solve Timeout | Unsolvable |
|---|---:|---:|---:|---:|---:|
| 5 | 20 | 19 | 1 | 0 | 0 |
| 10 | 20 | 20 | 0 | 0 | 0 |
| 15 | 20 | 18 | 2 | 0 | 0 |

Interpretace:
- Generátor vrací validní puzzle s referenčním řešením.
- Uniqueness není hard-guaranteed na všech vzorcích.

## Závěr

- Dokumentace a engine claimy byly upraveny tak, aby odpovídaly reálnému chování.
- Audit je reprodukovatelný a výsledky jsou uložené v `benchmarks/`.
