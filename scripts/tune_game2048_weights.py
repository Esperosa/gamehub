from __future__ import annotations

import argparse
import importlib.util
import json
import math
import random
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from games.game2048.solver import WEIGHT_KEYS, get_default_weights

_SCHEMA_VERSION = 2


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


def _score_summary(summary: dict[str, Any]) -> float:
    """
    Convert benchmark summary to scalar objective.

    Priority order:
    1) Win-rate towards 2048
    2) Stable score distribution and higher board ceilings
    3) Keep average think-time practical
    """
    win_rate = float(summary["win_rate_2048"])
    score_avg = float(summary["score"]["avg"])
    score_p90 = float(summary["score"]["p90"])
    think_ms = float(summary["solver_time"]["avg_think_ms_per_move"])

    best_tile_dist = summary.get("best_tile_distribution", {})
    total_tile = 0.0
    total_count = 0.0
    for key, value in best_tile_dist.items():
        total_tile += float(int(key)) * float(value)
        total_count += float(value)
    avg_best_tile = total_tile / max(total_count, 1.0)

    think_penalty = max(0.0, think_ms - 45.0) * 180.0

    return (
        win_rate * 320000.0
        + score_avg * 5.5
        + score_p90 * 1.8
        + avg_best_tile * 20.0
        - think_penalty
    )


def _bounds_to_state(bounds: dict[str, tuple[float, float]]) -> dict[str, list[float]]:
    return {key: [float(lo), float(hi)] for key, (lo, hi) in bounds.items()}


def _bounds_from_state(
    raw: Any,
    fallback: dict[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    if not isinstance(raw, dict):
        return dict(fallback)

    out: dict[str, tuple[float, float]] = {}
    for key, (f_lo, f_hi) in fallback.items():
        value = raw.get(key)
        if (
            isinstance(value, list)
            and len(value) == 2
            and isinstance(value[0], (float, int))
            and isinstance(value[1], (float, int))
        ):
            lo = float(value[0])
            hi = float(value[1])
            if hi < lo:
                lo, hi = hi, lo
            lo = max(f_lo, lo)
            hi = min(f_hi, hi)
            if hi <= lo:
                lo, hi = f_lo, f_hi
            out[key] = (lo, hi)
        else:
            out[key] = (f_lo, f_hi)
    return out


def _clamp_weights(
    weights: dict[str, float],
    bounds: dict[str, tuple[float, float]],
    defaults: dict[str, float],
) -> dict[str, float]:
    clamped: dict[str, float] = {}
    for key in WEIGHT_KEYS:
        lo, hi = bounds[key]
        value = float(weights.get(key, defaults[key]))
        clamped[key] = max(lo, min(hi, value))
    return clamped


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    q_clamped = max(0.0, min(1.0, q))
    pos = q_clamped * (len(ordered) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _sample_uniform_or_log(rng: random.Random, lo: float, hi: float) -> float:
    if lo > 0 and hi / lo > 1.7:
        return math.exp(rng.uniform(math.log(lo), math.log(hi)))
    return rng.uniform(lo, hi)


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
        value = float(candidate[key])
        if key in mutate_set:
            if value <= 0:
                value = _sample_uniform_or_log(rng, lo, hi)
            else:
                step = rng.gauss(0.0, sigma)
                if rng.random() < 0.12:
                    step = rng.gauss(0.0, sigma * 1.9)
                value *= math.exp(step)
        candidate[key] = max(lo, min(hi, value))
    return candidate


def _blend_weights(
    a: dict[str, float],
    b: dict[str, float],
    *,
    rng: random.Random,
    bounds: dict[str, tuple[float, float]],
) -> dict[str, float]:
    merged: dict[str, float] = {}
    for key in WEIGHT_KEYS:
        lo, hi = bounds[key]
        base = float(a[key]) if rng.random() < 0.5 else float(b[key])
        if rng.random() < 0.25:
            base = 0.65 * float(a[key]) + 0.35 * float(b[key])
        merged[key] = max(lo, min(hi, base))
    return merged


def _candidate_to_state(
    *,
    objective: float,
    summary: dict[str, Any],
    weights: dict[str, float],
    meta: dict[str, Any],
) -> dict[str, Any]:
    return {
        "objective": round(float(objective), 6),
        "summary": summary,
        "weights": {k: float(v) for k, v in weights.items()},
        "meta": meta,
    }


def _update_top(state: dict[str, Any], entry: dict[str, Any], keep: int) -> None:
    top = list(state.get("top", []))
    top.append(entry)
    top.sort(key=lambda x: float(x.get("objective", -1e18)), reverse=True)
    state["top"] = top[:keep]


def _state_template(bounds: dict[str, tuple[float, float]], config: dict[str, Any]) -> dict[str, Any]:
    now = _utc_now_iso()
    return {
        "schema": _SCHEMA_VERSION,
        "created_at_utc": now,
        "updated_at_utc": now,
        "status": "running",
        "config": config,
        "cycle_index": 0,
        "total_game_runs": 0,
        "total_candidate_evals": 0,
        "global_bounds": _bounds_to_state(bounds),
        "current_bounds": _bounds_to_state(bounds),
        "best": None,
        "top": [],
        "cycle_history": [],
        "validation_history": [],
        "range_history": [],
        "active_cycle": None,
        "final": None,
    }


def _migrate_state_schema1(
    old_state: dict[str, Any],
    *,
    bounds: dict[str, tuple[float, float]],
    config: dict[str, Any],
) -> dict[str, Any]:
    state = _state_template(bounds, config)
    state["status"] = "running"
    state["total_candidate_evals"] = int(old_state.get("runs_total", 0))
    state["cycle_history"] = [
        {
            "cycle_index": 0,
            "note": "migrated_from_schema_1",
            "migrated_at_utc": _utc_now_iso(),
        }
    ]

    best = old_state.get("best")
    if isinstance(best, dict) and isinstance(best.get("weights"), dict):
        state["best"] = best
        state["top"] = [best]

    legacy_top = old_state.get("top")
    if isinstance(legacy_top, list):
        for item in legacy_top:
            if isinstance(item, dict):
                _update_top(state, item, keep=24)

    return state


def _load_state(
    path: Path,
    *,
    reset: bool,
    bounds: dict[str, tuple[float, float]],
    config: dict[str, Any],
) -> dict[str, Any]:
    if reset or not path.exists():
        return _state_template(bounds, config)

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return _state_template(bounds, config)

    schema = int(raw.get("schema", 0))
    if schema == _SCHEMA_VERSION:
        state = raw
        state["config"] = config
        state["global_bounds"] = _bounds_to_state(_bounds_from_state(state.get("global_bounds"), bounds))
        state["current_bounds"] = _bounds_to_state(_bounds_from_state(state.get("current_bounds"), bounds))
        return state

    if schema == 1:
        return _migrate_state_schema1(raw, bounds=bounds, config=config)

    return _state_template(bounds, config)


def _save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at_utc"] = _utc_now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _snapshot_config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "cycle_games": int(args.cycle_games),
        "final_validation_games": int(args.final_validation_games),
        "target_win_rate": float(args.target_win_rate),
        "max_cycles": int(args.max_cycles),
        "agents": int(args.agents),
        "agent_workers": int(args.agent_workers),
        "benchmark_workers": int(args.benchmark_workers),
        "depth": int(args.depth),
        "chance_branch_limit": int(args.chance_branch_limit),
        "max_moves": int(args.max_moves),
        "max_seconds": float(args.max_seconds),
        "seed_start": int(args.seed_start),
        "sigma": float(args.sigma),
        "mutate_fraction": float(args.mutate_fraction),
        "elite_fraction": float(args.elite_fraction),
        "range_tighten": float(args.range_tighten),
        "range_min_fraction": float(args.range_min_fraction),
        "top_keep": int(args.top_keep),
        "history_limit": int(args.history_limit),
        "validate_every_cycles": int(args.validate_every_cycles),
    }


def _select_elite(entries: list[dict[str, Any]], fraction: float) -> list[dict[str, Any]]:
    if not entries:
        return []
    ordered = sorted(entries, key=lambda e: float(e.get("objective", -1e18)), reverse=True)
    take = max(2, int(math.ceil(len(ordered) * max(0.05, min(1.0, fraction)))))
    return ordered[: min(len(ordered), take)]


def _refine_bounds(
    *,
    current_bounds: dict[str, tuple[float, float]],
    global_bounds: dict[str, tuple[float, float]],
    elite: list[dict[str, Any]],
    champion_weights: dict[str, float],
    tighten: float,
    min_span_fraction: float,
) -> dict[str, tuple[float, float]]:
    new_bounds: dict[str, tuple[float, float]] = {}
    t = max(0.05, min(0.95, tighten))
    span_fraction = max(0.005, min(0.5, min_span_fraction))

    for key in WEIGHT_KEYS:
        g_lo, g_hi = global_bounds[key]
        c_lo, c_hi = current_bounds[key]
        g_span = g_hi - g_lo
        min_span = max(g_span * span_fraction, 1e-12)
        champion = float(champion_weights[key])

        values = []
        for entry in elite:
            weights = entry.get("weights")
            if isinstance(weights, dict) and key in weights:
                values.append(float(weights[key]))

        if values:
            q20 = _quantile(values, 0.2)
            q80 = _quantile(values, 0.8)
            core_lo = min(q20, champion)
            core_hi = max(q80, champion)
            core_span = max(core_hi - core_lo, min_span * 0.5)
            target_span = max(min_span, core_span * (1.0 + (1.0 - t)))
            target_center = (core_lo + core_hi) * 0.5
            target_lo = target_center - target_span * 0.5
            target_hi = target_center + target_span * 0.5
            n_lo = c_lo + (target_lo - c_lo) * t
            n_hi = c_hi + (target_hi - c_hi) * t
        else:
            n_lo, n_hi = c_lo, c_hi

        n_lo = min(n_lo, champion)
        n_hi = max(n_hi, champion)
        n_lo = max(g_lo, n_lo)
        n_hi = min(g_hi, n_hi)

        if n_hi <= n_lo:
            n_lo, n_hi = g_lo, g_hi

        if n_hi - n_lo < min_span:
            center = champion
            half = min_span * 0.5
            n_lo = max(g_lo, center - half)
            n_hi = min(g_hi, center + half)
            if n_hi - n_lo < min_span:
                n_lo, n_hi = g_lo, g_hi

        new_bounds[key] = (float(n_lo), float(n_hi))

    return new_bounds


def _seed_for_agent(*, seed_start: int, cycle_index: int, agent_id: int) -> int:
    return int(seed_start) + cycle_index * 1_000_000 + agent_id * 100_000


def _build_cycle_plan(
    *,
    cycle_index: int,
    defaults: dict[str, float],
    current_bounds: dict[str, tuple[float, float]],
    best_weights: dict[str, float],
    top_pool: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    cycle_seed = int(args.seed_start) + cycle_index * 97_159
    rng = random.Random(cycle_seed)

    games_total = max(1, int(args.cycle_games))
    agents_count = max(1, int(args.agents))
    base_games = games_total // agents_count
    remainder = games_total % agents_count

    sigma = max(0.01, float(args.sigma))
    mutate_fraction = max(0.05, min(1.0, float(args.mutate_fraction)))

    agents: list[dict[str, Any]] = []
    for agent_id in range(agents_count):
        games = base_games + (1 if agent_id < remainder else 0)
        if games <= 0:
            continue

        strategy = "exploit"
        if agent_id == 0:
            candidate = dict(best_weights)
            strategy = "champion"
        else:
            roll = rng.random()
            if roll < 0.30:
                strategy = "exploit"
                candidate = _mutate_weights(
                    dict(best_weights),
                    rng=rng,
                    sigma=sigma,
                    mutate_fraction=mutate_fraction,
                    bounds=current_bounds,
                )
            elif roll < 0.60 and len(top_pool) >= 2:
                strategy = "blend"
                a = rng.choice(top_pool)
                b = rng.choice(top_pool)
                wa = _clamp_weights(
                    {k: float(v) for k, v in dict(a.get("weights", {})).items()},
                    current_bounds,
                    defaults,
                )
                wb = _clamp_weights(
                    {k: float(v) for k, v in dict(b.get("weights", {})).items()},
                    current_bounds,
                    defaults,
                )
                candidate = _blend_weights(wa, wb, rng=rng, bounds=current_bounds)
                candidate = _mutate_weights(
                    candidate,
                    rng=rng,
                    sigma=sigma * 0.75,
                    mutate_fraction=max(0.15, mutate_fraction * 0.7),
                    bounds=current_bounds,
                )
            else:
                strategy = "explore"
                candidate = {}
                for key in WEIGHT_KEYS:
                    lo, hi = current_bounds[key]
                    candidate[key] = _sample_uniform_or_log(rng, lo, hi)

        candidate = _clamp_weights(candidate, current_bounds, defaults)
        agents.append(
            {
                "agent_id": agent_id,
                "strategy": strategy,
                "seed_start": _seed_for_agent(
                    seed_start=int(args.seed_start),
                    cycle_index=cycle_index,
                    agent_id=agent_id,
                ),
                "games": games,
                "weights": candidate,
                "status": "pending",
                "result": None,
            }
        )

    return {
        "cycle_index": cycle_index,
        "created_at_utc": _utc_now_iso(),
        "seed": cycle_seed,
        "games_total_planned": sum(int(a["games"]) for a in agents),
        "games_total_finished": 0,
        "bounds_snapshot": _bounds_to_state(current_bounds),
        "agents": agents,
    }


def _evaluate_agent_payload(payload: dict[str, Any]) -> dict[str, Any]:
    run_benchmark = _load_benchmark_runner()
    weights = {k: float(v) for k, v in dict(payload["weights"]).items()}
    result = run_benchmark(
        games=int(payload["games"]),
        seed_start=int(payload["seed_start"]),
        depth=int(payload["depth"]),
        fast_mode=False,
        chance_branch_limit=max(1, min(16, int(payload["chance_branch_limit"]))),
        max_moves=max(1, int(payload["max_moves"])),
        max_seconds=max(0.001, float(payload["max_seconds"])),
        workers=max(1, int(payload["benchmark_workers"])),
        weights=weights,
    )
    summary = result["summary"]
    objective = _score_summary(summary)
    return {
        "objective": round(float(objective), 6),
        "summary": summary,
        "weights": weights,
        "meta": {
            "cycle_index": int(payload["cycle_index"]),
            "agent_id": int(payload["agent_id"]),
            "strategy": str(payload["strategy"]),
            "seed_start": int(payload["seed_start"]),
            "games": int(payload["games"]),
            "evaluated_at_utc": _utc_now_iso(),
        },
    }


def _evaluate_pending_agents(
    *,
    state: dict[str, Any],
    args: argparse.Namespace,
    record: Path,
) -> None:
    active = state.get("active_cycle")
    if not isinstance(active, dict):
        return

    agents = active.get("agents")
    if not isinstance(agents, list):
        return

    pending: list[dict[str, Any]] = []
    for agent in agents:
        if isinstance(agent, dict) and agent.get("status") == "pending":
            pending.append(agent)

    if not pending:
        return

    payloads = [
        {
            "cycle_index": int(active["cycle_index"]),
            "agent_id": int(agent["agent_id"]),
            "strategy": str(agent["strategy"]),
            "seed_start": int(agent["seed_start"]),
            "games": int(agent["games"]),
            "weights": dict(agent["weights"]),
            "depth": int(args.depth),
            "chance_branch_limit": int(args.chance_branch_limit),
            "max_moves": int(args.max_moves),
            "max_seconds": float(args.max_seconds),
            "benchmark_workers": int(args.benchmark_workers),
        }
        for agent in pending
    ]

    by_id = {int(agent["agent_id"]): agent for agent in pending}

    agent_workers = max(1, min(int(args.agent_workers), len(payloads)))
    if agent_workers == 1:
        for payload in payloads:
            agent_id = int(payload["agent_id"])
            try:
                result = _evaluate_agent_payload(payload)
                by_id[agent_id]["status"] = "done"
                by_id[agent_id]["result"] = result
            except Exception as exc:
                by_id[agent_id]["status"] = "error"
                by_id[agent_id]["result"] = {
                    "error": f"{type(exc).__name__}: {exc}",
                    "meta": {
                        "cycle_index": int(payload["cycle_index"]),
                        "agent_id": agent_id,
                        "strategy": str(payload["strategy"]),
                        "failed_at_utc": _utc_now_iso(),
                    },
                }
            active["games_total_finished"] = sum(
                int(a.get("games", 0)) for a in agents if a.get("status") == "done"
            )
            _save_state(record, state)
        return

    with ProcessPoolExecutor(max_workers=agent_workers) as pool:
        futures = {pool.submit(_evaluate_agent_payload, payload): int(payload["agent_id"]) for payload in payloads}
        try:
            for future in as_completed(futures):
                agent_id = futures[future]
                agent = by_id[agent_id]
                try:
                    result = future.result()
                    agent["status"] = "done"
                    agent["result"] = result
                except Exception as exc:
                    agent["status"] = "error"
                    agent["result"] = {
                        "error": f"{type(exc).__name__}: {exc}",
                        "meta": {
                            "cycle_index": int(active["cycle_index"]),
                            "agent_id": agent_id,
                            "strategy": str(agent["strategy"]),
                            "failed_at_utc": _utc_now_iso(),
                        },
                    }

                active["games_total_finished"] = sum(
                    int(a.get("games", 0)) for a in agents if a.get("status") == "done"
                )
                _save_state(record, state)
        except KeyboardInterrupt:
            for future in futures:
                future.cancel()
            _save_state(record, state)
            raise


def _collect_cycle_results(state: dict[str, Any]) -> list[dict[str, Any]]:
    active = state.get("active_cycle")
    if not isinstance(active, dict):
        return []
    agents = active.get("agents")
    if not isinstance(agents, list):
        return []

    done: list[dict[str, Any]] = []
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        if agent.get("status") != "done":
            continue
        result = agent.get("result")
        if isinstance(result, dict) and "objective" in result and "weights" in result and "summary" in result:
            done.append(result)
    return done


def _run_validation(
    *,
    run_benchmark: Any,
    cycle_index: int,
    args: argparse.Namespace,
    weights: dict[str, float],
) -> dict[str, Any]:
    seed = int(args.seed_start) + 7_000_000_000 + cycle_index * 10_000
    report = run_benchmark(
        games=max(1, int(args.final_validation_games)),
        seed_start=seed,
        depth=max(1, int(args.depth)),
        fast_mode=False,
        chance_branch_limit=max(1, min(16, int(args.chance_branch_limit))),
        max_moves=max(1, int(args.max_moves)),
        max_seconds=max(0.001, float(args.max_seconds)),
        workers=max(1, int(args.benchmark_workers)),
        weights=weights,
    )
    summary = report["summary"]
    return {
        "cycle_index": cycle_index,
        "validated_at_utc": _utc_now_iso(),
        "seed_start": seed,
        "games": int(args.final_validation_games),
        "objective": round(_score_summary(summary), 6),
        "summary": summary,
        "weights": {k: float(v) for k, v in weights.items()},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Adaptive multi-agent Game2048 weight tuner with persistent checkpoints. "
            "Runs cycles over large batches, refines ranges, and stops only after a "
            "1000-game validation reaches the target win-rate."
        )
    )
    parser.add_argument(
        "--record",
        type=Path,
        default=Path("benchmarks/game2048_weight_tuner_state.json"),
        help="Path to persistent tuning state JSON.",
    )
    parser.add_argument("--reset", action="store_true", help="Reset stored state and start from scratch.")
    parser.add_argument("--list-weights", action="store_true", help="Print supported weights and exit.")
    parser.add_argument(
        "--weight",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Initial weight override(s) before first cycle.",
    )

    parser.add_argument("--cycle-games", type=int, default=1000, help="Total game runs per tuning cycle.")
    parser.add_argument(
        "--final-validation-games",
        type=int,
        default=1000,
        help="Game runs for final acceptance check each validation round.",
    )
    parser.add_argument(
        "--target-win-rate",
        type=float,
        default=0.90,
        help="Required 2048 win-rate in final validation to stop.",
    )
    parser.add_argument(
        "--validate-every-cycles",
        type=int,
        default=1,
        help="How often to run final 1000-game validation (in cycle count).",
    )
    parser.add_argument("--max-cycles", type=int, default=100, help="Hard cap on total cycles.")

    parser.add_argument("--agents", type=int, default=8, help="Number of agents (candidates) per cycle.")
    parser.add_argument(
        "--agent-workers",
        type=int,
        default=4,
        help="Parallel worker processes for agent evaluations.",
    )
    parser.add_argument(
        "--benchmark-workers",
        type=int,
        default=1,
        help="Workers inside each benchmark call (keep 1 when agent-workers > 1).",
    )

    parser.add_argument("--depth", type=int, default=3, help="Player-ply depth.")
    parser.add_argument("--chance-branch-limit", type=int, default=8, help="Chance-node branch limit.")
    parser.add_argument("--max-moves", type=int, default=2500, help="Per-game move cap.")
    parser.add_argument("--max-seconds", type=float, default=20.0, help="Per-game time cap.")
    parser.add_argument("--seed-start", type=int, default=2026030100, help="Seed base for reproducibility.")

    parser.add_argument("--sigma", type=float, default=0.14, help="Mutation strength in log-space.")
    parser.add_argument(
        "--mutate-fraction",
        type=float,
        default=0.45,
        help="Fraction of weights mutated in exploit mode (0..1).",
    )
    parser.add_argument(
        "--elite-fraction",
        type=float,
        default=0.35,
        help="Top fraction from each cycle used for range refinement.",
    )
    parser.add_argument(
        "--range-tighten",
        type=float,
        default=0.55,
        help="How strongly to move current ranges toward elite ranges (0..1).",
    )
    parser.add_argument(
        "--range-min-fraction",
        type=float,
        default=0.06,
        help="Minimum range width as fraction of global bound width.",
    )

    parser.add_argument("--top-keep", type=int, default=24, help="How many best entries to keep.")
    parser.add_argument(
        "--history-limit",
        type=int,
        default=300,
        help="How many cycle summaries and validations to keep.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    defaults = get_default_weights()

    if args.list_weights:
        print("Supported Game2048 weights:")
        for key in WEIGHT_KEYS:
            print(f"  {key}={defaults[key]}")
        return 0

    try:
        cli_overrides = _parse_weight_overrides(list(args.weight))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    base_bounds = _weight_bounds()
    config = _snapshot_config(args)
    state = _load_state(args.record, reset=bool(args.reset), bounds=base_bounds, config=config)

    current_bounds = _bounds_from_state(state.get("current_bounds"), base_bounds)

    best_entry = state.get("best")
    if isinstance(best_entry, dict) and isinstance(best_entry.get("weights"), dict):
        best_weights = _clamp_weights(
            {k: float(v) for k, v in dict(best_entry["weights"]).items()},
            current_bounds,
            defaults,
        )
    else:
        best_weights = _clamp_weights(dict(defaults), current_bounds, defaults)
        if cli_overrides:
            best_weights.update(
                _clamp_weights(
                    {**best_weights, **{k: float(v) for k, v in cli_overrides.items()}},
                    current_bounds,
                    defaults,
                )
            )
        state["best"] = _candidate_to_state(
            objective=-1e18,
            summary={},
            weights=best_weights,
            meta={"type": "bootstrap", "created_at_utc": _utc_now_iso()},
        )
        _update_top(state, state["best"], keep=max(4, int(args.top_keep)))
        _save_state(args.record, state)

    run_benchmark = _load_benchmark_runner()

    max_cycles = max(1, int(args.max_cycles))
    while int(state.get("cycle_index", 0)) < max_cycles:
        if state.get("status") == "completed":
            break

        current_bounds = _bounds_from_state(state.get("current_bounds"), base_bounds)
        global_bounds = _bounds_from_state(state.get("global_bounds"), base_bounds)

        active_cycle = state.get("active_cycle")
        if not isinstance(active_cycle, dict):
            cycle_index = int(state.get("cycle_index", 0)) + 1
            best_entry = state.get("best")
            best_weights = _clamp_weights(
                {k: float(v) for k, v in dict(best_entry.get("weights", {})).items()} if isinstance(best_entry, dict) else {},
                current_bounds,
                defaults,
            )
            for key, value in cli_overrides.items():
                best_weights[key] = max(
                    current_bounds[key][0],
                    min(current_bounds[key][1], float(value)),
                )

            top_pool = [
                entry
                for entry in list(state.get("top", []))
                if isinstance(entry, dict) and isinstance(entry.get("weights"), dict)
            ]

            state["active_cycle"] = _build_cycle_plan(
                cycle_index=cycle_index,
                defaults=defaults,
                current_bounds=current_bounds,
                best_weights=best_weights,
                top_pool=top_pool,
                args=args,
            )
            _save_state(args.record, state)
            active_cycle = state["active_cycle"]
            print(
                f"[cycle {cycle_index}] planned agents={len(active_cycle.get('agents', []))} "
                f"games={active_cycle.get('games_total_planned', 0)}"
            )

        _evaluate_pending_agents(state=state, args=args, record=args.record)

        cycle_results = _collect_cycle_results(state)
        if not cycle_results:
            state["status"] = "stopped_error"
            _save_state(args.record, state)
            print("No successful agent results in current cycle. Stopping.", file=sys.stderr)
            return 1

        cycle_index = int(state["active_cycle"]["cycle_index"])
        state["total_candidate_evals"] = int(state.get("total_candidate_evals", 0)) + len(cycle_results)
        state["total_game_runs"] = int(state.get("total_game_runs", 0)) + int(
            sum(int(entry["meta"]["games"]) for entry in cycle_results)
        )

        for entry in cycle_results:
            _update_top(state, entry, keep=max(4, int(args.top_keep)))
            current_best = state.get("best")
            if not isinstance(current_best, dict) or float(entry["objective"]) > float(current_best.get("objective", -1e18)):
                state["best"] = entry

        elite = _select_elite(cycle_results, float(args.elite_fraction))
        best_entry = state["best"]
        champion_weights = _clamp_weights(
            {k: float(v) for k, v in dict(best_entry.get("weights", {})).items()},
            current_bounds,
            defaults,
        )
        refined_bounds = _refine_bounds(
            current_bounds=current_bounds,
            global_bounds=global_bounds,
            elite=elite,
            champion_weights=champion_weights,
            tighten=float(args.range_tighten),
            min_span_fraction=float(args.range_min_fraction),
        )

        cycle_best = max(cycle_results, key=lambda x: float(x["objective"]))
        weighted_win_total = 0.0
        games_total = 0
        for entry in cycle_results:
            games = int(entry["meta"]["games"])
            win_rate = float(entry["summary"]["win_rate_2048"])
            weighted_win_total += win_rate * games
            games_total += games
        cycle_avg_win = weighted_win_total / max(1, games_total)

        cycle_summary = {
            "cycle_index": cycle_index,
            "completed_at_utc": _utc_now_iso(),
            "agents_done": len(cycle_results),
            "games_evaluated": games_total,
            "cycle_avg_win_rate_2048": round(cycle_avg_win, 4),
            "cycle_best_objective": float(cycle_best["objective"]),
            "cycle_best_win_rate_2048": float(cycle_best["summary"]["win_rate_2048"]),
            "champion_objective": float(state["best"]["objective"]),
        }
        state["cycle_history"].append(cycle_summary)
        if len(state["cycle_history"]) > max(20, int(args.history_limit)):
            state["cycle_history"] = state["cycle_history"][-int(args.history_limit) :]

        state["range_history"].append(
            {
                "cycle_index": cycle_index,
                "updated_at_utc": _utc_now_iso(),
                "bounds": _bounds_to_state(refined_bounds),
            }
        )
        if len(state["range_history"]) > max(20, int(args.history_limit)):
            state["range_history"] = state["range_history"][-int(args.history_limit) :]

        state["current_bounds"] = _bounds_to_state(refined_bounds)
        state["cycle_index"] = cycle_index
        state["active_cycle"] = None
        _save_state(args.record, state)

        print(
            f"[cycle {cycle_index}] avg_win={cycle_avg_win:.2%} "
            f"cycle_best={float(cycle_best['summary']['win_rate_2048']):.2%} "
            f"champion_obj={float(state['best']['objective']):.2f}"
        )

        validate_every = max(1, int(args.validate_every_cycles))
        should_validate = cycle_index % validate_every == 0
        if should_validate:
            champion = state["best"]
            champion_weights = _clamp_weights(
                {k: float(v) for k, v in dict(champion["weights"]).items()},
                refined_bounds,
                defaults,
            )
            validation = _run_validation(
                run_benchmark=run_benchmark,
                cycle_index=cycle_index,
                args=args,
                weights=champion_weights,
            )
            state["validation_history"].append(validation)
            if len(state["validation_history"]) > max(20, int(args.history_limit)):
                state["validation_history"] = state["validation_history"][-int(args.history_limit) :]

            validation_win = float(validation["summary"]["win_rate_2048"])
            _save_state(args.record, state)
            print(
                f"[validation] cycle={cycle_index} games={args.final_validation_games} "
                f"win_rate={validation_win:.2%} target={float(args.target_win_rate):.2%}"
            )

            if validation_win >= float(args.target_win_rate):
                state["status"] = "completed"
                state["final"] = {
                    "completed_at_utc": _utc_now_iso(),
                    "target_win_rate": float(args.target_win_rate),
                    "validation": validation,
                    "best": state["best"],
                    "current_bounds": state["current_bounds"],
                }
                _save_state(args.record, state)
                print(
                    f"[done] target reached with {validation_win:.2%} over "
                    f"{args.final_validation_games} games."
                )
                return 0

    if state.get("status") != "completed":
        state["status"] = "stopped_max_cycles"
        _save_state(args.record, state)
        print("[done] max cycles reached without hitting target win-rate.")
        print(f"state file: {args.record}")
        if isinstance(state.get("best"), dict):
            best = state["best"]
            print(f"best objective: {float(best.get('objective', 0.0)):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
