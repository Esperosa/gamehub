# Game2048 Rust Core (Optional)

Optional native search core for `games/game2048/solver.py`.

It exposes one Python module:

- `game2048_rust_core.best_move(board, ply, chance_branch_limit, weights, time_budget_ms, tt_max_entries)`

The Python solver auto-detects this module and uses it when available.
If missing or failing, it safely falls back to the pure-Python bitboard solver.

## Build (Development)

```bash
cd games/game2048/rust_core
python -m pip install maturin
maturin develop --release
```

## Disable at Runtime

Set env var:

```bash
GAMEHUB_2048_DISABLE_RUST_CORE=1
```
