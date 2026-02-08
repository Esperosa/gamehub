"""
Benchmark Sudoku puzzle generation speed for a fixed variant.

Example:
    python scripts/benchmark_sudoku_generation.py --size 16 --difficulty hard --count 30 --seed-start 2026020800
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from games.sudoku.engine import SudokuConfig, SudokuGenerator


def _pctl(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    if q <= 0.0:
        return min(values)
    if q >= 1.0:
        return max(values)
    sorted_vals = sorted(values)
    idx = int(q * len(sorted_vals)) - 1
    if idx < 0:
        idx = 0
    return sorted_vals[idx]


def run_benchmark(size: int, difficulty: str, seed_start: int, count: int) -> Dict[str, Any]:
    seeds = [seed_start + i for i in range(count)]
    gen = SudokuGenerator(SudokuConfig.from_size(size))

    durations: List[float] = []
    empties: List[int] = []

    for seed in seeds:
        t0 = time.perf_counter()
        state = gen.generate(difficulty, seed=seed)
        durations.append(time.perf_counter() - t0)
        empties.append(state.count_empty())

    rounded_01 = [round(v, 1) for v in durations]
    mode_time = Counter(rounded_01).most_common(1)[0] if rounded_01 else (0.0, 0)
    mode_empty = Counter(empties).most_common(1)[0] if empties else (0, 0)

    return {
        "size": size,
        "difficulty": difficulty,
        "seed_start": seed_start,
        "count": count,
        "avg_s": statistics.mean(durations) if durations else 0.0,
        "median_s": statistics.median(durations) if durations else 0.0,
        "min_s": min(durations) if durations else 0.0,
        "max_s": max(durations) if durations else 0.0,
        "p95_s": _pctl(durations, 0.95),
        "most_common_0_1s_bin": {"seconds": mode_time[0], "hits": mode_time[1]},
        "avg_empty": statistics.mean(empties) if empties else 0.0,
        "min_empty": min(empties) if empties else 0,
        "max_empty": max(empties) if empties else 0,
        "most_common_empty": {"empty": mode_empty[0], "hits": mode_empty[1]},
        "durations_s": durations,
        "empties": empties,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Sudoku generation.")
    parser.add_argument("--size", type=int, default=16, help="Board size (4, 6, 9, 16).")
    parser.add_argument("--difficulty", type=str, default="hard", help="Difficulty name.")
    parser.add_argument("--seed-start", type=int, default=2026020800, help="Base seed for deterministic runs.")
    parser.add_argument("--count", type=int, default=30, help="How many puzzles to generate.")
    parser.add_argument("--label", type=str, default="", help="Optional run label.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path.")
    args = parser.parse_args()

    result = run_benchmark(args.size, args.difficulty, args.seed_start, args.count)
    if args.label:
        result["label"] = args.label

    text = json.dumps(result, indent=2)
    print(text)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
