from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from games.game2048.engine import create_game
from games.game2048.solver import Solver2048, WEIGHT_KEYS, get_default_weights


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    idx = int((len(sorted_values) - 1) * p)
    return float(sorted_values[idx])


def _parse_weight_overrides(items: list[str]) -> dict[str, float]:
    overrides: dict[str, float] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --weight '{item}'. Expected format key=value.")
        key, raw_value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid --weight '{item}': missing key.")
        try:
            value = float(raw_value)
        except ValueError as exc:
            raise ValueError(f"Invalid --weight '{item}': value must be numeric.") from exc
        overrides[key] = value
    return overrides


def _simulate_game_with_solver(
    *,
    seed: int,
    solver: Solver2048,
    max_moves: int,
    max_seconds: float,
) -> dict[str, Any]:
    random.seed(seed)
    game = create_game(4)
    solver.pull_search_stats(reset=True)

    start = time.perf_counter()
    think_s = 0.0
    termination = "game_over"

    while True:
        if game.game_over:
            termination = "game_over"
            break

        if game.moves >= max_moves:
            termination = "move_cap"
            break

        elapsed = time.perf_counter() - start
        if elapsed >= max_seconds:
            termination = "time_cap"
            break

        grid_snapshot = [row[:] for row in game.grid]
        t0 = time.perf_counter()
        move = solver.get_move(grid_snapshot)
        think_s += time.perf_counter() - t0

        if move is None:
            termination = "no_move"
            break

        if not game.move(move):
            termination = "stalled_move"
            break

    elapsed = time.perf_counter() - start
    search_stats = solver.pull_search_stats(reset=True)
    return {
        "seed": seed,
        "won_2048": bool(game.best_tile >= 2048),
        "score": int(game.score),
        "best_tile": int(game.best_tile),
        "moves": int(game.moves),
        "elapsed_s": round(elapsed, 6),
        "think_s": round(think_s, 6),
        "termination": termination,
        "search_stats": search_stats,
    }


def _simulate_game_in_process(payload: dict[str, Any]) -> dict[str, Any]:
    solver = Solver2048(
        depth=int(payload["depth"]),
        fast_mode=bool(payload["fast_mode"]),
        weights=payload["weights"],
        chance_branch_limit=int(payload["chance_branch_limit"]),
        iterative_deepening=bool(payload["iterative_deepening"]),
        move_time_budget_ms=float(payload["move_time_budget_ms"]),
        fast_time_budget_ms=float(payload["fast_time_budget_ms"]),
    )
    return _simulate_game_with_solver(
        seed=int(payload["seed"]),
        solver=solver,
        max_moves=int(payload["max_moves"]),
        max_seconds=float(payload["max_seconds"]),
    )


def run_benchmark(
    *,
    games: int,
    seed_start: int,
    depth: int,
    fast_mode: bool,
    chance_branch_limit: int,
    max_moves: int,
    max_seconds: float,
    workers: int,
    weights: Mapping[str, float],
    iterative_deepening: bool = True,
    move_time_budget_ms: float = 24.0,
    fast_time_budget_ms: float = 10.0,
) -> dict[str, Any]:
    start = time.perf_counter()

    results: list[dict[str, Any]] = []
    seeds = [seed_start + i for i in range(games)]

    if workers <= 1:
        solver = Solver2048(
            depth=depth,
            fast_mode=fast_mode,
            weights=weights,
            chance_branch_limit=chance_branch_limit,
            iterative_deepening=iterative_deepening,
            move_time_budget_ms=move_time_budget_ms,
            fast_time_budget_ms=fast_time_budget_ms,
        )
        for seed in seeds:
            results.append(
                _simulate_game_with_solver(
                    seed=seed,
                    solver=solver,
                    max_moves=max_moves,
                    max_seconds=max_seconds,
                )
            )
    else:
        payloads = [
            {
                "seed": seed,
                "depth": depth,
                "fast_mode": fast_mode,
                "chance_branch_limit": chance_branch_limit,
                "max_moves": max_moves,
                "max_seconds": max_seconds,
                "weights": dict(weights),
                "iterative_deepening": iterative_deepening,
                "move_time_budget_ms": move_time_budget_ms,
                "fast_time_budget_ms": fast_time_budget_ms,
            }
            for seed in seeds
        ]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for result in pool.map(_simulate_game_in_process, payloads):
                results.append(result)

    elapsed = time.perf_counter() - start

    wins = sum(1 for r in results if r["won_2048"])
    scores = [int(r["score"]) for r in results]
    moves = [int(r["moves"]) for r in results]
    think_s = [float(r["think_s"]) for r in results]
    search_stats_rows = [dict(r.get("search_stats", {})) for r in results]

    total_searches = sum(float(s.get("searches", 0.0)) for s in search_stats_rows)
    total_player_nodes = sum(float(s.get("player_nodes", 0.0)) for s in search_stats_rows)
    total_chance_nodes = sum(float(s.get("chance_nodes", 0.0)) for s in search_stats_rows)
    total_tt_hits_player = sum(float(s.get("tt_hits_player", 0.0)) for s in search_stats_rows)
    total_tt_hits_chance = sum(float(s.get("tt_hits_chance", 0.0)) for s in search_stats_rows)
    total_timeouts = sum(float(s.get("timeouts", 0.0)) for s in search_stats_rows)
    total_nodes = total_player_nodes + total_chance_nodes
    total_tt_hits = total_tt_hits_player + total_tt_hits_chance
    total_think_s = sum(think_s)
    nodes_per_s = total_nodes / total_think_s if total_think_s > 0 else 0.0

    best_tile_distribution = Counter(str(r["best_tile"]) for r in results)
    termination_distribution = Counter(str(r["termination"]) for r in results)

    avg_score = sum(scores) / len(scores) if scores else 0.0
    avg_moves = sum(moves) / len(moves) if moves else 0.0
    avg_think_ms = (sum(think_s) / max(sum(moves), 1)) * 1000.0

    summary = {
        "games": games,
        "workers": workers,
        "depth": depth,
        "fast_mode": fast_mode,
        "chance_branch_limit": chance_branch_limit,
        "iterative_deepening": bool(iterative_deepening),
        "move_time_budget_ms": float(move_time_budget_ms),
        "fast_time_budget_ms": float(fast_time_budget_ms),
        "max_moves_per_game": max_moves,
        "max_seconds_per_game": max_seconds,
        "wall_time_s": round(elapsed, 3),
        "win_rate_2048": round(wins / max(games, 1), 4),
        "wins_2048": wins,
        "score": {
            "avg": round(avg_score, 2),
            "median": float(_percentile([float(v) for v in scores], 0.5)),
            "min": min(scores) if scores else 0,
            "max": max(scores) if scores else 0,
            "p90": float(_percentile([float(v) for v in scores], 0.9)),
        },
        "moves": {
            "avg": round(avg_moves, 2),
            "median": float(_percentile([float(v) for v in moves], 0.5)),
            "min": min(moves) if moves else 0,
            "max": max(moves) if moves else 0,
            "p90": float(_percentile([float(v) for v in moves], 0.9)),
        },
        "best_tile_distribution": dict(sorted(best_tile_distribution.items(), key=lambda kv: int(kv[0]))),
        "termination_distribution": dict(sorted(termination_distribution.items())),
        "solver_time": {
            "avg_think_ms_per_move": round(avg_think_ms, 4),
            "avg_game_think_s": round(sum(think_s) / max(len(think_s), 1), 4),
        },
        "solver_search": {
            "total_searches": int(total_searches),
            "total_player_nodes": int(total_player_nodes),
            "total_chance_nodes": int(total_chance_nodes),
            "total_nodes": int(total_nodes),
            "nodes_per_second": round(nodes_per_s, 2),
            "tt_hits_player": int(total_tt_hits_player),
            "tt_hits_chance": int(total_tt_hits_chance),
            "tt_hit_rate_player": round(total_tt_hits_player / total_player_nodes, 4)
            if total_player_nodes > 0
            else 0.0,
            "tt_hit_rate_chance": round(total_tt_hits_chance / total_chance_nodes, 4)
            if total_chance_nodes > 0
            else 0.0,
            "tt_hit_rate_overall": round(total_tt_hits / total_nodes, 4) if total_nodes > 0 else 0.0,
            "timeouts": int(total_timeouts),
        },
        "weights": {k: float(v) for k, v in weights.items()},
    }

    return {
        "summary": summary,
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark/tune Game2048 expectimax solver with CLI-configurable weights."
    )
    parser.add_argument("--games", type=int, default=100, help="Number of simulated games.")
    parser.add_argument("--seed-start", type=int, default=2026020800, help="Base seed for runs.")
    parser.add_argument("--depth", type=int, default=3, help="Player-ply search depth.")
    parser.add_argument("--fast-mode", action="store_true", help="Enable low-latency depth caps.")
    parser.add_argument(
        "--no-iterative-deepening",
        action="store_true",
        help="Disable iterative deepening and run single-depth search.",
    )
    parser.add_argument(
        "--move-time-budget-ms",
        type=float,
        default=24.0,
        help="Per-move search budget for normal mode when iterative deepening is enabled.",
    )
    parser.add_argument(
        "--fast-time-budget-ms",
        type=float,
        default=10.0,
        help="Per-move search budget for fast mode when iterative deepening is enabled.",
    )
    parser.add_argument(
        "--chance-branch-limit",
        type=int,
        default=8,
        help="Max sampled empty cells at chance nodes (1-16).",
    )
    parser.add_argument("--max-moves", type=int, default=4000, help="Per-game move cap.")
    parser.add_argument("--max-seconds", type=float, default=120.0, help="Per-game time cap in seconds.")
    parser.add_argument("--workers", type=int, default=1, help="Process workers for parallel simulation.")
    parser.add_argument(
        "--weight",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override one solver weight (repeatable).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/game2048_solver_benchmark_latest.json"),
        help="Output JSON report path.",
    )
    parser.add_argument(
        "--list-weights",
        action="store_true",
        help="Print supported weight keys and defaults, then exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    defaults = get_default_weights()
    if args.list_weights:
        print("Supported Game2048 solver weights:")
        for key in WEIGHT_KEYS:
            print(f"  {key}={defaults[key]}")
        return 0

    try:
        overrides = _parse_weight_overrides(args.weight)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    weights = dict(defaults)
    for key, value in overrides.items():
        if key not in weights:
            print(
                f"Error: unknown weight '{key}'. Use --list-weights to see valid keys.",
                file=sys.stderr,
            )
            return 2
        weights[key] = value

    result = run_benchmark(
        games=max(1, args.games),
        seed_start=args.seed_start,
        depth=max(1, args.depth),
        fast_mode=bool(args.fast_mode),
        chance_branch_limit=max(1, min(16, args.chance_branch_limit)),
        max_moves=max(1, args.max_moves),
        max_seconds=max(1e-3, float(args.max_seconds)),
        workers=max(1, args.workers),
        weights=weights,
        iterative_deepening=not bool(args.no_iterative_deepening),
        move_time_budget_ms=max(0.0, float(args.move_time_budget_ms)),
        fast_time_budget_ms=max(0.0, float(args.fast_time_budget_ms)),
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = result["summary"]
    search = summary.get("solver_search", {})
    print(f"[ok] report: {args.output}")
    print(
        "[summary] "
        f"games={summary['games']} depth={summary['depth']} fast_mode={summary['fast_mode']} "
        f"win_rate_2048={summary['win_rate_2048']:.2%} "
        f"avg_score={summary['score']['avg']} "
        f"avg_think_ms={summary['solver_time']['avg_think_ms_per_move']} "
        f"nodes_per_s={search.get('nodes_per_second', 0.0)} "
        f"tt_hit={search.get('tt_hit_rate_overall', 0.0):.2%}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
