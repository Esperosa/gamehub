from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from games.game2048.engine import Direction, create_game
from hub.layer_loader import load_module_from_file

s2048 = load_module_from_file("game2048_solver_analysis_layer", ROOT / "games" / "game2048" / "solver.py")


_DIR_TO_INT = {
    Direction.UP: s2048.DIR_UP,
    Direction.DOWN: s2048.DIR_DOWN,
    Direction.LEFT: s2048.DIR_LEFT,
    Direction.RIGHT: s2048.DIR_RIGHT,
}

_INT_TO_NAME = {
    s2048.DIR_UP: "up",
    s2048.DIR_DOWN: "down",
    s2048.DIR_LEFT: "left",
    s2048.DIR_RIGHT: "right",
}


@dataclass
class CandidateEval:
    direction: str
    score: float
    gain: int
    empty_after: int
    max_exp_after: int



def _as_board(grid: list[list[int]]) -> int:
    return s2048._grid_to_bitboard(s2048.np.asarray(grid, dtype=s2048.np.int64))



def _effective_depth_for_board(solver: s2048.Solver2048, board: int) -> int:
    empty_count = s2048._count_empty_board(board)
    max_exp, _ = s2048._max_exp_and_idx(board)

    effective_depth = solver.depth
    if solver.fast_mode:
        effective_depth = min(max(2, effective_depth), min(3, solver.max_depth_cap))
    else:
        if empty_count >= 10:
            effective_depth = max(2, effective_depth - 1)
        elif empty_count <= 6:
            effective_depth = min(effective_depth + 1, solver.max_depth_cap)
        elif empty_count <= 3:
            effective_depth = min(effective_depth + 2, solver.max_depth_cap)

        if max_exp >= 10 and empty_count >= 3:
            effective_depth = min(effective_depth + 1, solver.max_depth_cap)
        elif max_exp >= 9 and empty_count >= 5:
            effective_depth = min(effective_depth + 1, solver.max_depth_cap)

    return min(max(2, effective_depth), solver.max_depth_cap)



def _evaluate_candidates(
    board: int,
    *,
    depth: int,
    weight_vector,
    chance_branch_limit: int,
    row_gradient,
) -> list[CandidateEval]:
    searcher = s2048._BitboardSearcher(
        weight_vector=weight_vector,
        chance_branch_limit=chance_branch_limit,
        row_gradient=row_gradient,
        tt={},
        tt_max_entries=0,
        deadline_s=None,
    )

    out: list[CandidateEval] = []
    next_ply = max(depth - 1, 0)
    for d in (s2048.DIR_LEFT, s2048.DIR_UP, s2048.DIR_DOWN, s2048.DIR_RIGHT):
        moved_board, gain, moved = s2048._simulate_move_board(board, d)
        if not moved:
            continue
        score = gain * float(weight_vector[s2048.W_MOVE_SCORE_SCALE]) + searcher._chance(
            moved_board,
            next_ply,
        )
        max_exp_after, _ = s2048._max_exp_and_idx(moved_board)
        out.append(
            CandidateEval(
                direction=_INT_TO_NAME[d],
                score=float(score),
                gain=int(gain),
                empty_after=int(s2048._count_empty_board(moved_board)),
                max_exp_after=int(max_exp_after),
            )
        )

    out.sort(key=lambda c: c.score, reverse=True)
    return out



def _classify_error(
    board_before: int,
    board_after: int,
    chosen_dir: str,
    baseline_candidates: list[CandidateEval],
    oracle_candidates: list[CandidateEval],
) -> list[str]:
    tags: list[str] = []

    if not baseline_candidates or not oracle_candidates:
        return ["no_legal_move"]

    oracle_best = oracle_candidates[0]
    chosen_oracle = next((c for c in oracle_candidates if c.direction == chosen_dir), None)
    if chosen_oracle is None:
        tags.append("invalid_choice")
    else:
        if chosen_oracle.score + 1e-9 < oracle_best.score:
            tags.append("suboptimal_vs_oracle")

    before_empty = s2048._count_empty_board(board_before)
    after_empty = s2048._count_empty_board(board_after)
    if before_empty <= 4 and after_empty < before_empty:
        tags.append("space_collapse")

    max_exp_before, max_idx_before = s2048._max_exp_and_idx(board_before)
    max_exp_after, max_idx_after = s2048._max_exp_and_idx(board_after)
    if max_idx_before == 0 and max_idx_after != 0 and max_exp_after <= max_exp_before:
        tags.append("corner_break")

    if chosen_dir in ("right", "down"):
        tags.append("risky_direction")

    if not tags:
        tags.append("no_clear_error")

    return tags



def _analyze_game(
    seed: int,
    solver: s2048.Solver2048,
    oracle_extra_depth: int,
    max_moves: int,
) -> dict[str, Any]:
    random.seed(seed)
    game = create_game(4)

    s2048._ensure_tables()
    row_gradient = s2048._get_row_gradient_table(s2048._FLAT_GRADIENT)

    history: list[dict[str, Any]] = []

    while not game.game_over and game.moves < max_moves:
        grid_before = [row[:] for row in game.grid]
        board_before = _as_board(grid_before)

        effective_depth = _effective_depth_for_board(solver, board_before)
        baseline_candidates = _evaluate_candidates(
            board_before,
            depth=effective_depth,
            weight_vector=solver._weight_vector,
            chance_branch_limit=solver.chance_branch_limit,
            row_gradient=row_gradient,
        )

        oracle_depth = min(effective_depth + max(1, oracle_extra_depth), solver.max_depth_cap + 2)
        oracle_candidates = _evaluate_candidates(
            board_before,
            depth=oracle_depth,
            weight_vector=solver._weight_vector,
            chance_branch_limit=16,
            row_gradient=row_gradient,
        )

        chosen_move = solver.get_move(grid_before)
        if chosen_move is None:
            break

        chosen_dir_name = chosen_move.value
        moved = game.move(chosen_move)
        if not moved:
            break

        board_after = _as_board(game.grid)

        chosen_baseline = next((c for c in baseline_candidates if c.direction == chosen_dir_name), None)
        chosen_oracle = next((c for c in oracle_candidates if c.direction == chosen_dir_name), None)

        history.append(
            {
                "move_index": int(game.moves),
                "grid_before": grid_before,
                "chosen": chosen_dir_name,
                "effective_depth": int(effective_depth),
                "oracle_depth": int(oracle_depth),
                "baseline_top": [c.__dict__ for c in baseline_candidates],
                "oracle_top": [c.__dict__ for c in oracle_candidates],
                "baseline_chosen_score": float(chosen_baseline.score) if chosen_baseline else None,
                "oracle_chosen_score": float(chosen_oracle.score) if chosen_oracle else None,
                "error_tags": _classify_error(
                    board_before,
                    board_after,
                    chosen_dir_name,
                    baseline_candidates,
                    oracle_candidates,
                ),
            }
        )

    won = bool(game.best_tile >= 2048)
    loss_slice = history[-8:] if not won and history else []

    return {
        "seed": int(seed),
        "won_2048": won,
        "score": int(game.score),
        "best_tile": int(game.best_tile),
        "moves": int(game.moves),
        "history_len": len(history),
        "last_8_before_loss": loss_slice,
    }



def run_analysis(args: argparse.Namespace) -> dict[str, Any]:
    weights = dict(s2048.get_default_weights())
    for item in args.weight:
        if "=" not in item:
            raise ValueError(f"Invalid --weight '{item}', expected key=value")
        key, raw = item.split("=", 1)
        if key not in weights:
            raise ValueError(f"Unknown weight key '{key}'")
        weights[key] = float(raw)

    solver = s2048.Solver2048(
        depth=args.depth,
        fast_mode=args.fast_mode,
        weights=weights,
        chance_branch_limit=args.chance_branch_limit,
        max_depth_cap=args.max_depth_cap,
        iterative_deepening=args.iterative_deepening,
        move_time_budget_ms=args.move_time_budget_ms,
        fast_time_budget_ms=args.fast_time_budget_ms,
    )

    games: list[dict[str, Any]] = []
    for i in range(args.games):
        seed = args.seed_start + i
        games.append(
            _analyze_game(
                seed=seed,
                solver=solver,
                oracle_extra_depth=args.oracle_extra_depth,
                max_moves=args.max_moves,
            )
        )

    losses = [g for g in games if not g["won_2048"]]
    wins = len(games) - len(losses)

    tag_counts: dict[str, int] = {}
    for g in losses:
        for step in g["last_8_before_loss"]:
            for tag in step["error_tags"]:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

    return {
        "config": {
            "games": args.games,
            "seed_start": args.seed_start,
            "depth": args.depth,
            "max_depth_cap": args.max_depth_cap,
            "fast_mode": args.fast_mode,
            "iterative_deepening": args.iterative_deepening,
            "move_time_budget_ms": args.move_time_budget_ms,
            "fast_time_budget_ms": args.fast_time_budget_ms,
            "chance_branch_limit": args.chance_branch_limit,
            "oracle_extra_depth": args.oracle_extra_depth,
            "weights": weights,
        },
        "summary": {
            "games": len(games),
            "wins_2048": wins,
            "win_rate_2048": round(wins / max(1, len(games)), 4),
            "losses": len(losses),
            "error_tags_last8": tag_counts,
            "avg_score": round(sum(int(g["score"]) for g in games) / max(1, len(games)), 2),
            "avg_best_tile": round(sum(int(g["best_tile"]) for g in games) / max(1, len(games)), 2),
        },
        "games": games,
    }



def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Analyze 2048 solver losses and last-8 decisions.")
    p.add_argument("--games", type=int, default=20)
    p.add_argument("--seed-start", type=int, default=2026041001)
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--max-depth-cap", type=int, default=8)
    p.add_argument("--chance-branch-limit", type=int, default=8)
    p.add_argument("--max-moves", type=int, default=4000)
    p.add_argument("--fast-mode", action="store_true")
    p.add_argument("--no-iterative-deepening", action="store_true")
    p.add_argument("--iterative-deepening", action="store_true")
    p.add_argument("--move-time-budget-ms", type=float, default=24.0)
    p.add_argument("--fast-time-budget-ms", type=float, default=10.0)
    p.add_argument("--oracle-extra-depth", type=int, default=2)
    p.add_argument("--weight", action="append", default=[])
    p.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/game2048_loss_analysis_latest.json"),
    )
    return p.parse_args()



def main() -> int:
    args = parse_args()
    if args.no_iterative_deepening:
        args.iterative_deepening = False
    elif not args.iterative_deepening:
        args.iterative_deepening = True

    result = run_analysis(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = result["summary"]
    print(f"[ok] report: {args.output}")
    print(
        "[summary] "
        f"games={summary['games']} "
        f"wins={summary['wins_2048']} "
        f"win_rate_2048={summary['win_rate_2048']:.2%} "
        f"avg_score={summary['avg_score']}"
    )
    if summary["error_tags_last8"]:
        ordered = sorted(summary["error_tags_last8"].items(), key=lambda kv: kv[1], reverse=True)
        top = ", ".join(f"{k}:{v}" for k, v in ordered[:6])
        print(f"[errors] {top}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
