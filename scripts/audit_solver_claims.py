"""
Audit runtime solver/generator claims against observed behavior.

This script is intentionally deterministic and bounded in runtime so it can be
used in CI/docs refresh flows.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from games.kenken.engine import KenKenConfig, KenKenGenerator, KenKenSolver
from games.nonogram.engine import NonogramSolver, NonogramState, generate_random_puzzle
from games.sudoku.engine import SudokuConfig, SudokuGenerator, SudokuSolver
from hub.solver_contract import SolveStatus


def _status_name(status: SolveStatus) -> str:
    return status.name


def audit_sudoku(samples_per_size: int, base_seed: int) -> Dict[str, Any]:
    """
    Check whether generated puzzles expose alternative solutions.

    For 4/6/9 we run exact alternative checks (no timeout).
    For 16x16 we keep a bounded check budget to avoid long outliers.
    """
    rows: List[Dict[str, Any]] = []
    for size in (4, 6, 9, 16):
        config = SudokuConfig.from_size(size)
        generator = SudokuGenerator(config)
        solver = SudokuSolver(config)
        difficulty = "hard" if size == 16 else "medium"
        verify_timeout_s = 1.5 if size == 16 else None

        alternatives = 0
        inconclusive_timeout = 0
        elapsed_samples: List[float] = []

        for i in range(samples_per_size):
            seed = base_seed + size * 10_000 + i
            state = generator.generate(difficulty=difficulty, seed=seed)

            t0 = time.perf_counter()
            has_alt = solver.has_alternative_solution_with_timeout(
                state.board,
                state.solution,
                timeout_s=verify_timeout_s,
            )
            elapsed_samples.append(time.perf_counter() - t0)

            timed_out = bool(getattr(solver, "_alt_timed_out", False))
            if timed_out:
                inconclusive_timeout += 1
            elif has_alt:
                alternatives += 1

        rows.append(
            {
                "size": size,
                "difficulty": difficulty,
                "samples": samples_per_size,
                "alternatives_found": alternatives,
                "inconclusive_timeout": inconclusive_timeout,
                "verify_timeout_s": verify_timeout_s,
                "avg_verify_ms": round(mean(elapsed_samples) * 1000, 2) if elapsed_samples else 0.0,
                "max_verify_ms": round(max(elapsed_samples) * 1000, 2) if elapsed_samples else 0.0,
            }
        )

    return {"method": "alternative-solution probe", "results": rows}


def audit_kenken(samples_per_size: int, base_seed: int) -> Dict[str, Any]:
    """Measure observed uniqueness ratio for Calcudoku-based KenKen generation."""
    rows: List[Dict[str, Any]] = []
    for size in (4, 6, 8):
        config = KenKenConfig.from_size(size)
        generator = KenKenGenerator(config)
        unique_count = 0
        multiple_count = 0
        timeout_count = 0
        elapsed_samples: List[float] = []

        for i in range(samples_per_size):
            seed = base_seed + size * 20_000 + i
            state = generator.generate(seed=seed)
            solver = KenKenSolver(config, state.cages)
            t0 = time.perf_counter()
            solutions = solver.count_solutions([0] * (size * size), limit=2, timeout=0.8)
            elapsed_samples.append(time.perf_counter() - t0)

            if solutions == 1:
                unique_count += 1
            elif solutions == -1:
                timeout_count += 1
            else:
                multiple_count += 1

        rows.append(
            {
                "size": size,
                "samples": samples_per_size,
                "unique": unique_count,
                "multiple_or_ambiguous": multiple_count,
                "count_timeout": timeout_count,
                "avg_count_ms": round(mean(elapsed_samples) * 1000, 2) if elapsed_samples else 0.0,
                "max_count_ms": round(max(elapsed_samples) * 1000, 2) if elapsed_samples else 0.0,
                "count_timeout_s": 0.8,
            }
        )

    return {"method": "count_solutions(limit=2, timeout=0.8s)", "results": rows}


def audit_nonogram(samples_per_size: int, base_seed: int) -> Dict[str, Any]:
    """Measure observed uniqueness ratio for generated Nonogram puzzles."""
    rows: List[Dict[str, Any]] = []
    for size in (5, 10, 15):
        unique_count = 0
        multiple_count = 0
        timeout_count = 0
        unsat_count = 0
        elapsed_samples: List[float] = []

        for i in range(samples_per_size):
            seed = base_seed + size * 30_000 + i
            puzzle = generate_random_puzzle(size, size, seed=seed)
            state = NonogramState.from_puzzle(puzzle)
            solver = NonogramSolver(state)

            t0 = time.perf_counter()
            result = solver.solve_result(timeout=1.5, detect_multiple=True)
            elapsed_samples.append(time.perf_counter() - t0)

            status = _status_name(result.status)
            if status == SolveStatus.MULTIPLE_SOLUTIONS.name:
                multiple_count += 1
            elif status == SolveStatus.SOLVED.name:
                if result.solutions_found is not None and result.solutions_found > 1:
                    multiple_count += 1
                else:
                    unique_count += 1
            elif status == SolveStatus.TIMEOUT.name:
                timeout_count += 1
            else:
                unsat_count += 1

        rows.append(
            {
                "size": size,
                "samples": samples_per_size,
                "unique": unique_count,
                "multiple_or_ambiguous": multiple_count,
                "solve_timeout": timeout_count,
                "unsolvable": unsat_count,
                "avg_solve_ms": round(mean(elapsed_samples) * 1000, 2) if elapsed_samples else 0.0,
                "max_solve_ms": round(max(elapsed_samples) * 1000, 2) if elapsed_samples else 0.0,
                "solve_timeout_s": 1.5,
            }
        )

    return {"method": "solve_result(timeout=1.5s, detect_multiple=True)", "results": rows}


def run_audit(samples: int, base_seed: int) -> Dict[str, Any]:
    started = time.perf_counter()
    payload = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "samples_per_variant": samples,
        "base_seed": base_seed,
        "sudoku": audit_sudoku(samples, base_seed),
        "kenken": audit_kenken(samples, base_seed),
        "nonogram": audit_nonogram(samples, base_seed),
    }
    payload["total_runtime_s"] = round(time.perf_counter() - started, 3)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit solver/generator claims.")
    parser.add_argument("--samples", type=int, default=20, help="Samples per size/variant.")
    parser.add_argument("--base-seed", type=int, default=20260208, help="Deterministic seed base.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/solver_claims_audit_latest.json"),
        help="JSON output path.",
    )
    args = parser.parse_args()

    result = run_audit(samples=max(1, args.samples), base_seed=args.base_seed)
    text = json.dumps(result, indent=2)
    print(text)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
