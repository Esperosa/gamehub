from __future__ import annotations

import argparse
import importlib.util
import json
import math
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from games.game2048.solver import WEIGHT_KEYS, get_default_weights


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_benchmark_runner() -> Any:
    """Load benchmark_game2048_solver.py dynamically and return run_benchmark callable."""
    module_path = ROOT / "scripts" / "benchmark_game2048_solver.py"
    spec = importlib.util.spec_from_file_location("game2048_benchmark_runtime", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load benchmark module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run_benchmark = getattr(module, "run_benchmark", None)
    if not callable(run_benchmark):
        raise RuntimeError("benchmark_game2048_solver.py does not expose callable run_benchmark().")
    return run_benchmark


def _parse_weight_overrides(items: list[str]) -> dict[str, float]:
    overrides: dict[str, float] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --weight '{item}'. Expected key=value.")
        key, raw_value = item.split("=", 1)
        key = key.strip()
        if key not in WEIGHT_KEYS:
            raise ValueError(f"Unknown weight key '{key}'.")
        try:
            overrides[key] = float(raw_value)
        except ValueError as exc:
            raise ValueError(f"Invalid value for '{key}': '{raw_value}'.") from exc
    return overrides


def _weight_bounds() -> dict[str, tuple[float, float]]:
    return {
        "gradient": (400.0, 22000.0),
        "corner_bonus": (500.0, 35000.0),
        "corner_distance_penalty": (200.0, 22000.0),
        "empty_cells": (400.0, 6000.0),
        "monotonicity": (100.0, 6000.0),
        "smoothness": (2.0, 300.0),
        "merge": (10.0, 2000.0),
        "near_2048": (0.05, 12.0),
        "left_bias": (0.0, 900.0),
        "up_bias": (0.0, 900.0),
        "right_penalty": (0.0, 900.0),
        "down_penalty": (0.0, 900.0),
        "corner_break_penalty": (0.0, 3000.0),
        "move_score_scale": (0.001, 0.2),
        "terminal_penalty": (10000.0, 5000000.0),
    }


@dataclass
class CandidateScore:
    objective: float
    summary: dict[str, Any]
    weights: dict[str, float]


def _score_summary(summary: dict[str, Any]) -> float:
    """
    Convert benchmark summary to scalar objective for tuner optimization.

    Priorities:
    1) Higher 2048 win rate
    2) Higher score / stronger tail
    3) Keep think time practical (soft penalty)
    """
    win_rate = float(summary["win_rate_2048"])
    score_avg = float(summary["score"]["avg"])
    score_p90 = float(summary["score"]["p90"])
    think_ms = float(summary["solver_time"]["avg_think_ms_per_move"])

    # Estimate average best tile to reward stable high boards even before 2048.
    best_tile_dist = summary.get("best_tile_distribution", {})
    total = 0.0
    count = 0.0
    for key, value in best_tile_dist.items():
        total += float(int(key)) * float(value)
        count += float(value)
    avg_best_tile = total / max(count, 1.0)

    think_penalty = max(0.0, think_ms - 45.0) * 180.0

    return (
        win_rate * 320000.0
        + score_avg * 5.5
        + score_p90 * 1.8
        + avg_best_tile * 20.0
        - think_penalty
    )


def _mutate_weights(
    base: dict[str, float],
    *,
    rng: random.Random,
    sigma: float,
    mutate_fraction: float,
    bounds: dict[str, tuple[float, float]],
) -> dict[str, float]:
    candidate = dict(base)

    keys = list(WEIGHT_KEYS)
    rng.shuffle(keys)
    mutate_n = max(1, int(len(keys) * mutate_fraction))
    mutate_set = set(keys[:mutate_n])

    for key in keys:
        lo, hi = bounds[key]
        value = candidate[key]
        if key in mutate_set:
            step = rng.gauss(0.0, sigma)
            # Occasional larger jump to avoid local minima.
            if rng.random() < 0.1:
                step = rng.gauss(0.0, sigma * 2.0)
            value *= math.exp(step)
        value = max(lo, min(hi, value))
        candidate[key] = float(value)

    return candidate


def _state_template() -> dict[str, Any]:
    return {
        "schema": 1,
        "created_at_utc": _utc_now_iso(),
        "updated_at_utc": _utc_now_iso(),
        "runs_total": 0,
        "best": None,
        "history": [],
        "top": [],
    }


def _load_state(path: Path, reset: bool) -> dict[str, Any]:
    if reset or not path.exists():
        return _state_template()

    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        return _state_template()
    if state.get("schema") != 1:
        return _state_template()
    return state


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _candidate_to_state(score: CandidateScore, meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "objective": round(score.objective, 6),
        "summary": score.summary,
        "weights": {k: float(v) for k, v in score.weights.items()},
        "meta": meta,
    }


def _update_top(state: dict[str, Any], entry: dict[str, Any], keep: int = 12) -> None:
    top = list(state.get("top", []))
    top.append(entry)
    top.sort(key=lambda x: float(x.get("objective", -1e18)), reverse=True)
    state["top"] = top[:keep]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Iterative Game2048 weight tuner with persistent state. "
            "Resumes from previous best and keeps improving across runs."
        )
    )
    parser.add_argument(
        "--record",
        type=Path,
        default=Path("benchmarks/game2048_weight_tuner_state.json"),
        help="Path to persistent tuning state JSON.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1000,
        help="How many candidate evaluations to run this session.",
    )
    parser.add_argument("--games-per-eval", type=int, default=10, help="Simulated games per candidate.")
    parser.add_argument("--depth", type=int, default=3, help="Player-ply depth.")
    parser.add_argument("--chance-branch-limit", type=int, default=8, help="Chance-node branch limit.")
    parser.add_argument("--max-moves", type=int, default=2500, help="Per-game move cap.")
    parser.add_argument("--max-seconds", type=float, default=20.0, help="Per-game time cap.")
    parser.add_argument("--workers", type=int, default=4, help="Parallel process workers.")
    parser.add_argument("--seed-start", type=int, default=2026030100, help="Seed base for reproducibility.")
    parser.add_argument("--sigma", type=float, default=0.14, help="Mutation strength (log-space sigma).")
    parser.add_argument(
        "--mutate-fraction",
        type=float,
        default=0.45,
        help="Fraction of weights mutated per candidate (0..1).",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=2500,
        help="Max number of history records kept in state file.",
    )
    parser.add_argument(
        "--weight",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Apply fixed starting override(s) before tuning.",
    )
    parser.add_argument("--reset", action="store_true", help="Ignore previous state and start fresh.")
    parser.add_argument("--list-weights", action="store_true", help="Print supported weight keys and exit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    defaults = get_default_weights()

    if args.list_weights:
        print("Supported weights:")
        for key in WEIGHT_KEYS:
            print(f"  {key}={defaults[key]}")
        return 0

    try:
        cli_overrides = _parse_weight_overrides(args.weight)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    run_benchmark = _load_benchmark_runner()
    bounds = _weight_bounds()

    state = _load_state(args.record, args.reset)

    best_state = state.get("best")
    if isinstance(best_state, dict) and isinstance(best_state.get("weights"), dict):
        current_best_weights = {k: float(v) for k, v in best_state["weights"].items() if k in defaults}
        for key, value in defaults.items():
            current_best_weights.setdefault(key, value)
    else:
        current_best_weights = dict(defaults)

    for key, value in cli_overrides.items():
        current_best_weights[key] = float(value)

    # Clamp start weights to allowed bounds.
    for key, (lo, hi) in bounds.items():
        current_best_weights[key] = max(lo, min(hi, float(current_best_weights[key])))

    rng = random.Random(args.seed_start + int(state.get("runs_total", 0)))

    # Evaluate baseline if there is no saved best (or reset).
    if not isinstance(best_state, dict):
        baseline_result = run_benchmark(
            games=max(1, int(args.games_per_eval)),
            seed_start=int(args.seed_start),
            depth=max(1, int(args.depth)),
            fast_mode=False,
            chance_branch_limit=max(1, min(16, int(args.chance_branch_limit))),
            max_moves=max(1, int(args.max_moves)),
            max_seconds=max(0.001, float(args.max_seconds)),
            workers=max(1, int(args.workers)),
            weights=current_best_weights,
        )
        baseline_summary = baseline_result["summary"]
        baseline_score = CandidateScore(
            objective=_score_summary(baseline_summary),
            summary=baseline_summary,
            weights=dict(current_best_weights),
        )
        best_entry = _candidate_to_state(
            baseline_score,
            {
                "iteration": 0,
                "seed_start": int(args.seed_start),
                "type": "baseline",
            },
        )
        state["best"] = best_entry
        _update_top(state, best_entry)
        state["runs_total"] = int(state.get("runs_total", 0)) + 1
        state["history"].append(best_entry)
        state["updated_at_utc"] = _utc_now_iso()
        _save_state(args.record, state)
        print(
            f"[baseline] objective={best_entry['objective']:.2f} "
            f"win_rate={baseline_summary['win_rate_2048']:.2%}"
        )

    best_objective = float(state["best"]["objective"])
    best_weights = {k: float(v) for k, v in state["best"]["weights"].items()}

    for i in range(1, max(1, int(args.iterations)) + 1):
        eval_id = int(state.get("runs_total", 0)) + 1

        # Mix exploitation (best/top) with occasional wider exploration.
        top_pool = [entry for entry in state.get("top", []) if isinstance(entry, dict)]
        use_top = bool(top_pool) and rng.random() < 0.35
        if use_top:
            parent = rng.choice(top_pool)
            parent_weights = {k: float(v) for k, v in parent.get("weights", {}).items() if k in defaults}
            for key, value in defaults.items():
                parent_weights.setdefault(key, value)
        else:
            parent_weights = dict(best_weights)

        candidate_weights = _mutate_weights(
            parent_weights,
            rng=rng,
            sigma=max(0.01, float(args.sigma)),
            mutate_fraction=max(0.05, min(1.0, float(args.mutate_fraction))),
            bounds=bounds,
        )

        seed_start = int(args.seed_start) + eval_id * 10000
        result = run_benchmark(
            games=max(1, int(args.games_per_eval)),
            seed_start=seed_start,
            depth=max(1, int(args.depth)),
            fast_mode=False,
            chance_branch_limit=max(1, min(16, int(args.chance_branch_limit))),
            max_moves=max(1, int(args.max_moves)),
            max_seconds=max(0.001, float(args.max_seconds)),
            workers=max(1, int(args.workers)),
            weights=candidate_weights,
        )
        summary = result["summary"]
        objective = _score_summary(summary)

        entry = _candidate_to_state(
            CandidateScore(objective=objective, summary=summary, weights=candidate_weights),
            {
                "iteration": i,
                "eval_id": eval_id,
                "seed_start": seed_start,
                "sigma": float(args.sigma),
            },
        )

        state["history"].append(entry)
        if len(state["history"]) > max(50, int(args.history_limit)):
            state["history"] = state["history"][-int(args.history_limit) :]

        _update_top(state, entry)

        improved = objective > best_objective
        if improved:
            best_objective = objective
            best_weights = dict(candidate_weights)
            state["best"] = entry

        state["runs_total"] = eval_id
        state["updated_at_utc"] = _utc_now_iso()
        _save_state(args.record, state)

        print(
            f"[{i}/{args.iterations}] "
            f"objective={objective:.2f} "
            f"win={summary['win_rate_2048']:.2%} "
            f"avg_score={summary['score']['avg']} "
            f"think_ms={summary['solver_time']['avg_think_ms_per_move']} "
            f"{'NEW_BEST' if improved else ''}"
        )

    best = state["best"]
    print("\n[done] tuner state updated")
    print(f"record: {args.record}")
    print(f"best objective: {float(best['objective']):.2f}")
    print(f"best win_rate: {float(best['summary']['win_rate_2048']):.2%}")
    print(f"best avg_score: {best['summary']['score']['avg']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
