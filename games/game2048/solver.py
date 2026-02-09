"""
2048 AI solver using bitboard expectimax + transposition table.

Design goals:
- Bitboard board representation with precomputed row-move lookup tables.
- Player-ply expectimax with deterministic chance sampling.
- Tunable heuristics for benchmark/CLI-driven weight optimization.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Mapping, Optional

import numpy as np


class Direction(Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


# Direction constants for internal integer paths.
DIR_UP = 0
DIR_DOWN = 1
DIR_LEFT = 2
DIR_RIGHT = 3

# Normalized snake-like gradient (top-left anchor).
GRADIENT_WEIGHTS = np.array(
    [
        [1.0, 0.5, 0.25, 0.125],
        [0.0078125, 0.015625, 0.03125, 0.0625],
        [0.00390625, 0.001953125, 0.0009765625, 0.00048828125],
        [0.000030517578125, 0.00006103515625, 0.0001220703125, 0.000244140625],
    ],
    dtype=np.float64,
)
_FLAT_GRADIENT = tuple(float(v) for v in GRADIENT_WEIGHTS.reshape(16))

# Tunable evaluation weights (CLI-friendly names).
WEIGHT_KEYS = (
    "gradient",
    "corner_bonus",
    "corner_distance_penalty",
    "empty_cells",
    "monotonicity",
    "smoothness",
    "merge",
    "near_2048",
    "left_bias",
    "up_bias",
    "right_penalty",
    "down_penalty",
    "corner_break_penalty",
    "move_score_scale",
    "terminal_penalty",
)

# Index constants for vectorized weight access.
W_GRADIENT = 0
W_CORNER_BONUS = 1
W_CORNER_DIST_PENALTY = 2
W_EMPTY = 3
W_MONOTONICITY = 4
W_SMOOTHNESS = 5
W_MERGE = 6
W_NEAR_2048 = 7
W_LEFT_BIAS = 8
W_UP_BIAS = 9
W_RIGHT_PENALTY = 10
W_DOWN_PENALTY = 11
W_CORNER_BREAK_PENALTY = 12
W_MOVE_SCORE_SCALE = 13
W_TERMINAL_PENALTY = 14

_WEIGHT_INDEX = {key: idx for idx, key in enumerate(WEIGHT_KEYS)}

DEFAULT_WEIGHT_VECTOR = np.array(
    [
        4800.0,  # gradient
        9000.0,  # corner_bonus
        4200.0,  # corner_distance_penalty
        2600.0,  # empty_cells
        1900.0,  # monotonicity
        45.0,  # smoothness
        300.0,  # merge
        1.4,  # near_2048
        120.0,  # left_bias
        95.0,  # up_bias
        80.0,  # right_penalty
        110.0,  # down_penalty
        550.0,  # corner_break_penalty
        0.02,  # move_score_scale
        950000.0,  # terminal_penalty
    ],
    dtype=np.float64,
)

# Bitboard constants.
_MAX_EXP = 15
_TT_MAX_ENTRIES_DEFAULT = 120000

# Precomputed row lookup tables (16-bit row state -> moved row / gain).
_ROW_LEFT: list[int] = [0] * 65536
_ROW_RIGHT: list[int] = [0] * 65536
_ROW_LEFT_GAIN: list[int] = [0] * 65536
_ROW_RIGHT_GAIN: list[int] = [0] * 65536
_ROW_EMPTY: list[int] = [0] * 65536
_ROW_SMOOTH: list[float] = [0.0] * 65536
_ROW_MERGE: list[float] = [0.0] * 65536
_ROW_MONO: list[float] = [0.0] * 65536
_ROW_MAX_EXP: list[int] = [0] * 65536
_ROW_MAX_COL: list[int] = [0] * 65536
_ROW_COUNT_512: list[int] = [0] * 65536
_ROW_COUNT_1024: list[int] = [0] * 65536
_ROW_ADJ_512: list[int] = [0] * 65536
_ROW_ADJ_1024: list[int] = [0] * 65536
_ROW_GRADIENT: tuple[list[float], list[float], list[float], list[float]] = (
    [0.0] * 65536,
    [0.0] * 65536,
    [0.0] * 65536,
    [0.0] * 65536,
)
_TABLES_READY = False

# Compatibility map for public wrappers.
_INT_TO_DIR = {
    DIR_UP: Direction.UP,
    DIR_DOWN: Direction.DOWN,
    DIR_LEFT: Direction.LEFT,
    DIR_RIGHT: Direction.RIGHT,
}
_DIR_TO_INT = {v: k for k, v in _INT_TO_DIR.items()}


def get_default_weights() -> dict[str, float]:
    """Return default solver weights as a plain dictionary."""
    return {key: float(DEFAULT_WEIGHT_VECTOR[idx]) for key, idx in _WEIGHT_INDEX.items()}


def build_weight_vector(overrides: Optional[Mapping[str, float]] = None) -> np.ndarray:
    """
    Build a stable weight vector.

    Unknown keys raise KeyError so CLI tuning fails fast.
    """
    weights = DEFAULT_WEIGHT_VECTOR.copy()
    if overrides:
        for key, value in overrides.items():
            idx = _WEIGHT_INDEX.get(key)
            if idx is None:
                supported = ", ".join(WEIGHT_KEYS)
                raise KeyError(f"Unknown 2048 solver weight '{key}'. Supported: {supported}")
            weights[idx] = float(value)
    return weights


def _coerce_weight_vector(weights: object) -> np.ndarray:
    arr = np.asarray(weights, dtype=np.float64).reshape(-1)
    if arr.size < len(WEIGHT_KEYS):
        raise ValueError(
            f"Weight vector has {arr.size} values, expected at least {len(WEIGHT_KEYS)}."
        )
    if arr.size > len(WEIGHT_KEYS):
        arr = arr[: len(WEIGHT_KEYS)]
    return arr


def _value_to_exp(value: int) -> int:
    if value <= 0:
        return 0
    exp = int(value).bit_length() - 1
    if exp > _MAX_EXP:
        return _MAX_EXP
    return exp


def _grid_to_bitboard(grid: np.ndarray) -> int:
    board = 0
    shift = 0
    for r in range(4):
        for c in range(4):
            exp = _value_to_exp(int(grid[r, c]))
            board |= (exp & 0xF) << shift
            shift += 4
    return board


def _reverse_row16(row: int) -> int:
    return ((row & 0x000F) << 12) | ((row & 0x00F0) << 4) | ((row & 0x0F00) >> 4) | ((row & 0xF000) >> 12)


def _slide_row_left_16(row: int) -> tuple[int, int]:
    exps = [row & 0xF, (row >> 4) & 0xF, (row >> 8) & 0xF, (row >> 12) & 0xF]
    vals: list[int] = [v for v in exps if v != 0]

    merged: list[int] = []
    gain = 0
    i = 0
    while i < len(vals):
        if i + 1 < len(vals) and vals[i] == vals[i + 1]:
            exp = vals[i] + 1
            if exp > _MAX_EXP:
                exp = _MAX_EXP
            merged.append(exp)
            gain += 1 << exp
            i += 2
        else:
            merged.append(vals[i])
            i += 1

    while len(merged) < 4:
        merged.append(0)

    out = merged[0] | (merged[1] << 4) | (merged[2] << 8) | (merged[3] << 12)
    return out, gain


def _ensure_tables() -> None:
    global _TABLES_READY
    if _TABLES_READY:
        return

    for row in range(65536):
        exps = [row & 0xF, (row >> 4) & 0xF, (row >> 8) & 0xF, (row >> 12) & 0xF]

        _ROW_EMPTY[row] = int(exps[0] == 0) + int(exps[1] == 0) + int(exps[2] == 0) + int(exps[3] == 0)
        _ROW_MONO[row] = _line_monotonicity_penalty_nonzero(exps[0], exps[1], exps[2], exps[3])

        smooth = 0.0
        merge = 0.0
        for i in range(3):
            a = exps[i]
            b = exps[i + 1]
            if a > 0 and b > 0:
                diff = abs(float(a - b))
                smooth += diff * diff
                if a == b:
                    merge += float(a)
        _ROW_SMOOTH[row] = smooth
        _ROW_MERGE[row] = merge

        max_exp = 0
        max_col = 0
        for i in range(4):
            if exps[i] > max_exp:
                max_exp = exps[i]
                max_col = i
        _ROW_MAX_EXP[row] = max_exp
        _ROW_MAX_COL[row] = max_col

        count_512 = 0
        count_1024 = 0
        adj_512 = 0
        adj_1024 = 0
        for i in range(4):
            if exps[i] == 9:
                count_512 += 1
            elif exps[i] == 10:
                count_1024 += 1
        for i in range(3):
            if exps[i] == 9 and exps[i + 1] == 9:
                adj_512 = 1
            if exps[i] == 10 and exps[i + 1] == 10:
                adj_1024 = 1
        _ROW_COUNT_512[row] = count_512
        _ROW_COUNT_1024[row] = count_1024
        _ROW_ADJ_512[row] = adj_512
        _ROW_ADJ_1024[row] = adj_1024

        _ROW_GRADIENT[0][row] = (
            float(exps[0]) * _FLAT_GRADIENT[0]
            + float(exps[1]) * _FLAT_GRADIENT[1]
            + float(exps[2]) * _FLAT_GRADIENT[2]
            + float(exps[3]) * _FLAT_GRADIENT[3]
        )
        _ROW_GRADIENT[1][row] = (
            float(exps[0]) * _FLAT_GRADIENT[4]
            + float(exps[1]) * _FLAT_GRADIENT[5]
            + float(exps[2]) * _FLAT_GRADIENT[6]
            + float(exps[3]) * _FLAT_GRADIENT[7]
        )
        _ROW_GRADIENT[2][row] = (
            float(exps[0]) * _FLAT_GRADIENT[8]
            + float(exps[1]) * _FLAT_GRADIENT[9]
            + float(exps[2]) * _FLAT_GRADIENT[10]
            + float(exps[3]) * _FLAT_GRADIENT[11]
        )
        _ROW_GRADIENT[3][row] = (
            float(exps[0]) * _FLAT_GRADIENT[12]
            + float(exps[1]) * _FLAT_GRADIENT[13]
            + float(exps[2]) * _FLAT_GRADIENT[14]
            + float(exps[3]) * _FLAT_GRADIENT[15]
        )

        left_row, left_gain = _slide_row_left_16(row)
        _ROW_LEFT[row] = left_row
        _ROW_LEFT_GAIN[row] = left_gain

        reversed_row = _reverse_row16(row)
        reversed_moved, right_gain = _slide_row_left_16(reversed_row)
        right_row = _reverse_row16(reversed_moved)
        _ROW_RIGHT[row] = right_row
        _ROW_RIGHT_GAIN[row] = right_gain

    _TABLES_READY = True


def _transpose_board(board: int) -> int:
    result = 0
    for r in range(4):
        for c in range(4):
            src_shift = 4 * (r * 4 + c)
            dst_shift = 4 * (c * 4 + r)
            result |= ((board >> src_shift) & 0xF) << dst_shift
    return result


def _move_left_board(board: int) -> tuple[int, int, bool]:
    r0 = board & 0xFFFF
    r1 = (board >> 16) & 0xFFFF
    r2 = (board >> 32) & 0xFFFF
    r3 = (board >> 48) & 0xFFFF

    n0 = _ROW_LEFT[r0]
    n1 = _ROW_LEFT[r1]
    n2 = _ROW_LEFT[r2]
    n3 = _ROW_LEFT[r3]

    new_board = n0 | (n1 << 16) | (n2 << 32) | (n3 << 48)
    gain = _ROW_LEFT_GAIN[r0] + _ROW_LEFT_GAIN[r1] + _ROW_LEFT_GAIN[r2] + _ROW_LEFT_GAIN[r3]
    return new_board, gain, new_board != board


def _move_right_board(board: int) -> tuple[int, int, bool]:
    r0 = board & 0xFFFF
    r1 = (board >> 16) & 0xFFFF
    r2 = (board >> 32) & 0xFFFF
    r3 = (board >> 48) & 0xFFFF

    n0 = _ROW_RIGHT[r0]
    n1 = _ROW_RIGHT[r1]
    n2 = _ROW_RIGHT[r2]
    n3 = _ROW_RIGHT[r3]

    new_board = n0 | (n1 << 16) | (n2 << 32) | (n3 << 48)
    gain = _ROW_RIGHT_GAIN[r0] + _ROW_RIGHT_GAIN[r1] + _ROW_RIGHT_GAIN[r2] + _ROW_RIGHT_GAIN[r3]
    return new_board, gain, new_board != board


def _move_up_board(board: int) -> tuple[int, int, bool]:
    transposed = _transpose_board(board)
    moved, gain, _ = _move_left_board(transposed)
    new_board = _transpose_board(moved)
    return new_board, gain, new_board != board


def _move_down_board(board: int) -> tuple[int, int, bool]:
    transposed = _transpose_board(board)
    moved, gain, _ = _move_right_board(transposed)
    new_board = _transpose_board(moved)
    return new_board, gain, new_board != board


def _simulate_move_board(board: int, direction: int) -> tuple[int, int, bool]:
    if direction == DIR_LEFT:
        return _move_left_board(board)
    if direction == DIR_RIGHT:
        return _move_right_board(board)
    if direction == DIR_UP:
        return _move_up_board(board)
    return _move_down_board(board)


def _get_cell_exp(board: int, idx: int) -> int:
    return (board >> (idx * 4)) & 0xF


def _count_empty_board(board: int) -> int:
    empty = 0
    for idx in range(16):
        if ((board >> (idx * 4)) & 0xF) == 0:
            empty += 1
    return empty


def _max_exp_and_idx(board: int) -> tuple[int, int]:
    max_exp = 0
    max_idx = 0
    for idx in range(16):
        exp = _get_cell_exp(board, idx)
        if exp > max_exp:
            max_exp = exp
            max_idx = idx
    return max_exp, max_idx


def log2_fast(x: int) -> float:
    """Compatibility helper: fast log2 for positive integer values."""
    if x <= 0:
        return 0.0
    return float(int(x).bit_length() - 1)


def _line_monotonicity_penalty_nonzero(v0: int, v1: int, v2: int, v3: int) -> float:
    """Monotonicity penalty over non-zero exponents only (compressed line)."""
    compressed = [v for v in (v0, v1, v2, v3) if v > 0]
    if len(compressed) <= 1:
        return 0.0

    inc = 0.0
    dec = 0.0
    for i in range(len(compressed) - 1):
        a = float(compressed[i])
        b = float(compressed[i + 1])
        if a > b:
            inc += a - b
        else:
            dec += b - a

    return min(inc, dec)


def _global_monotonicity_penalty_board(board: int) -> float:
    penalty = 0.0

    for r in range(4):
        base = r * 4
        penalty += _line_monotonicity_penalty_nonzero(
            _get_cell_exp(board, base),
            _get_cell_exp(board, base + 1),
            _get_cell_exp(board, base + 2),
            _get_cell_exp(board, base + 3),
        )

    for c in range(4):
        penalty += _line_monotonicity_penalty_nonzero(
            _get_cell_exp(board, c),
            _get_cell_exp(board, c + 4),
            _get_cell_exp(board, c + 8),
            _get_cell_exp(board, c + 12),
        )

    return penalty


def _count_target_positions(board: int, target_exp: int) -> list[int]:
    return [idx for idx in range(16) if _get_cell_exp(board, idx) == target_exp]


def _positions_stats(positions: list[int]) -> tuple[bool, int]:
    if len(positions) < 2:
        return False, 99

    has_adjacent = False
    min_dist = 99

    for i in range(len(positions)):
        r1 = positions[i] // 4
        c1 = positions[i] % 4
        for j in range(i + 1, len(positions)):
            r2 = positions[j] // 4
            c2 = positions[j] % 4
            dist = abs(r1 - r2) + abs(c1 - c2)
            if dist == 1:
                has_adjacent = True
            if dist < min_dist:
                min_dist = dist

    return has_adjacent, min_dist


def _near_2048_potential_board(board: int, max_exp: int, max_idx: int, empty_count: int) -> float:
    if max_exp < 9:  # < 512
        return 0.0

    safety = empty_count / 8.0
    safety = max(0.15, min(1.0, safety))

    pos_1024 = _count_target_positions(board, 10)
    pos_512 = _count_target_positions(board, 9)

    adj_1024, dist_1024 = _positions_stats(pos_1024)
    adj_512, dist_512 = _positions_stats(pos_512)

    score = 0.0
    count_1024 = len(pos_1024)
    count_512 = len(pos_512)

    if max_exp >= 10:
        score += count_1024 * 520.0
        if adj_1024:
            score += 4600.0
        elif count_1024 >= 2:
            score += max(0.0, 2600.0 - dist_1024 * 420.0)

        score += count_512 * 140.0
        if count_1024 == 1 and count_512 >= 2:
            score += 900.0
    else:
        score += count_512 * 220.0
        if adj_512:
            score += 1700.0
        elif count_512 >= 2:
            score += max(0.0, 1200.0 - dist_512 * 180.0)

    if max_idx == 0:
        score += 350.0
    elif max_exp >= 10:
        score -= 450.0

    return score * safety


def _near_2048_potential_fast(board: int, rows: tuple[int, int, int, int], cols: tuple[int, int, int, int], max_exp: int, max_idx: int, empty_count: int) -> float:
    """
    Near-2048 tactical term using row-table shortcuts plus optional distance fallback.
    """
    if max_exp < 9:
        return 0.0

    count_1024 = (
        _ROW_COUNT_1024[rows[0]]
        + _ROW_COUNT_1024[rows[1]]
        + _ROW_COUNT_1024[rows[2]]
        + _ROW_COUNT_1024[rows[3]]
    )
    count_512 = (
        _ROW_COUNT_512[rows[0]]
        + _ROW_COUNT_512[rows[1]]
        + _ROW_COUNT_512[rows[2]]
        + _ROW_COUNT_512[rows[3]]
    )

    adj_1024 = (
        _ROW_ADJ_1024[rows[0]]
        or _ROW_ADJ_1024[rows[1]]
        or _ROW_ADJ_1024[rows[2]]
        or _ROW_ADJ_1024[rows[3]]
        or _ROW_ADJ_1024[cols[0]]
        or _ROW_ADJ_1024[cols[1]]
        or _ROW_ADJ_1024[cols[2]]
        or _ROW_ADJ_1024[cols[3]]
    )
    adj_512 = (
        _ROW_ADJ_512[rows[0]]
        or _ROW_ADJ_512[rows[1]]
        or _ROW_ADJ_512[rows[2]]
        or _ROW_ADJ_512[rows[3]]
        or _ROW_ADJ_512[cols[0]]
        or _ROW_ADJ_512[cols[1]]
        or _ROW_ADJ_512[cols[2]]
        or _ROW_ADJ_512[cols[3]]
    )

    dist_1024 = 99
    dist_512 = 99
    if count_1024 >= 2 and not adj_1024:
        _, dist_1024 = _positions_stats(_count_target_positions(board, 10))
    if count_512 >= 2 and not adj_512:
        _, dist_512 = _positions_stats(_count_target_positions(board, 9))

    safety = empty_count / 8.0
    safety = max(0.15, min(1.0, safety))

    score = 0.0
    if max_exp >= 10:
        score += count_1024 * 520.0
        if adj_1024:
            score += 4600.0
        elif count_1024 >= 2:
            score += max(0.0, 2600.0 - dist_1024 * 420.0)

        score += count_512 * 140.0
        if count_1024 == 1 and count_512 >= 2:
            score += 900.0
    else:
        score += count_512 * 220.0
        if adj_512:
            score += 1700.0
        elif count_512 >= 2:
            score += max(0.0, 1200.0 - dist_512 * 180.0)

    if max_idx == 0:
        score += 350.0
    elif max_exp >= 10:
        score -= 450.0

    return score * safety


def _evaluate_board(board: int, weights: np.ndarray, flat_gradient: tuple[float, ...]) -> float:
    r0 = board & 0xFFFF
    r1 = (board >> 16) & 0xFFFF
    r2 = (board >> 32) & 0xFFFF
    r3 = (board >> 48) & 0xFFFF
    rows = (r0, r1, r2, r3)

    # Row-table derived stats.
    empty_count = _ROW_EMPTY[r0] + _ROW_EMPTY[r1] + _ROW_EMPTY[r2] + _ROW_EMPTY[r3]
    gradient_score = (
        _ROW_GRADIENT[0][r0]
        + _ROW_GRADIENT[1][r1]
        + _ROW_GRADIENT[2][r2]
        + _ROW_GRADIENT[3][r3]
    )
    smoothness_penalty = _ROW_SMOOTH[r0] + _ROW_SMOOTH[r1] + _ROW_SMOOTH[r2] + _ROW_SMOOTH[r3]
    merge_score = _ROW_MERGE[r0] + _ROW_MERGE[r1] + _ROW_MERGE[r2] + _ROW_MERGE[r3]
    mono_penalty = _ROW_MONO[r0] + _ROW_MONO[r1] + _ROW_MONO[r2] + _ROW_MONO[r3]

    # Add vertical terms via transposed rows.
    t = _transpose_board(board)
    c0 = t & 0xFFFF
    c1 = (t >> 16) & 0xFFFF
    c2 = (t >> 32) & 0xFFFF
    c3 = (t >> 48) & 0xFFFF
    cols = (c0, c1, c2, c3)
    smoothness_penalty += _ROW_SMOOTH[c0] + _ROW_SMOOTH[c1] + _ROW_SMOOTH[c2] + _ROW_SMOOTH[c3]
    merge_score += _ROW_MERGE[c0] + _ROW_MERGE[c1] + _ROW_MERGE[c2] + _ROW_MERGE[c3]
    mono_penalty += _ROW_MONO[c0] + _ROW_MONO[c1] + _ROW_MONO[c2] + _ROW_MONO[c3]

    # Max tile location from row summaries.
    max_exp = -1
    max_idx = 0
    for row_i, row_bits in enumerate(rows):
        row_exp = _ROW_MAX_EXP[row_bits]
        if row_exp > max_exp:
            max_exp = row_exp
            max_idx = row_i * 4 + _ROW_MAX_COL[row_bits]

    max_r = max_idx // 4
    max_c = max_idx % 4

    score = 0.0
    score += weights[W_GRADIENT] * gradient_score
    if max_idx == 0:
        score += weights[W_CORNER_BONUS]
    else:
        score -= (max_r + max_c) * weights[W_CORNER_DIST_PENALTY]

    score += weights[W_EMPTY] * float(empty_count * empty_count)
    score -= weights[W_MONOTONICITY] * mono_penalty
    score -= weights[W_SMOOTHNESS] * smoothness_penalty
    score += weights[W_MERGE] * merge_score
    score += weights[W_NEAR_2048] * _near_2048_potential_fast(
        board,
        rows,
        cols,
        max_exp,
        max_idx,
        empty_count,
    )
    return score


def near_2048_potential_numba(grid: np.ndarray) -> float:
    """Compatibility wrapper for tests and benchmark tools."""
    np_grid = np.asarray(grid, dtype=np.int64)
    board = _grid_to_bitboard(np_grid)
    max_exp, max_idx = _max_exp_and_idx(board)
    empty_count = _count_empty_board(board)
    return _near_2048_potential_board(board, max_exp, max_idx, empty_count)


def evaluate_grid_numba(grid: np.ndarray, gradient_weights: np.ndarray, weights: np.ndarray) -> float:
    """Compatibility wrapper using bitboard evaluation backend."""
    np_grid = np.asarray(grid, dtype=np.int64)
    board = _grid_to_bitboard(np_grid)
    flat_gradient = tuple(float(v) for v in np.asarray(gradient_weights, dtype=np.float64).reshape(16))
    weight_vec = _coerce_weight_vector(weights)
    return _evaluate_board(board, weight_vec, flat_gradient)


def _board_sampling_seed(board: int, ply: int) -> int:
    """Deterministic 64-bit mix for reproducible chance-node sampling."""
    x = board & 0xFFFFFFFFFFFFFFFF
    x ^= ((ply + 1) * 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
    x ^= (x >> 33)
    x = (x * 0xFF51AFD7ED558CCD) & 0xFFFFFFFFFFFFFFFF
    x ^= (x >> 33)
    x = (x * 0xC4CEB9FE1A85EC53) & 0xFFFFFFFFFFFFFFFF
    x ^= (x >> 33)
    return int(x)


def _sample_positions_deterministic(positions: list[int], sample_count: int, seed: int) -> list[int]:
    if sample_count >= len(positions):
        return positions

    n = len(positions)
    start = seed % n
    step = ((seed >> 8) % n) + 1
    while math.gcd(step, n) != 1:
        step += 1
        if step > n:
            step = 1

    sampled: list[int] = []
    idx = start
    for _ in range(sample_count):
        sampled.append(positions[idx])
        idx = (idx + step) % n
    return sampled


def _direction_bias_board(board: int, direction: int, weights: np.ndarray) -> float:
    bias = 0.0

    if direction == DIR_LEFT:
        bias += weights[W_LEFT_BIAS]
    elif direction == DIR_UP:
        bias += weights[W_UP_BIAS]
    elif direction == DIR_RIGHT:
        bias -= weights[W_RIGHT_PENALTY]
    else:
        bias -= weights[W_DOWN_PENALTY]

    r0 = board & 0xFFFF
    r1 = (board >> 16) & 0xFFFF
    r2 = (board >> 32) & 0xFFFF
    r3 = (board >> 48) & 0xFFFF

    max_exp = -1
    max_idx = 0
    for row_i, row_bits in enumerate((r0, r1, r2, r3)):
        row_exp = _ROW_MAX_EXP[row_bits]
        if row_exp > max_exp:
            max_exp = row_exp
            max_idx = row_i * 4 + _ROW_MAX_COL[row_bits]
    if max_idx == 0:
        below_exp = _get_cell_exp(board, 4)
        right_exp = _get_cell_exp(board, 1)
        if direction == DIR_DOWN and below_exp < max_exp:
            bias -= weights[W_CORNER_BREAK_PENALTY]
        if direction == DIR_RIGHT and right_exp < max_exp:
            bias -= weights[W_CORNER_BREAK_PENALTY]

    return bias


class _BitboardSearcher:
    def __init__(
        self,
        *,
        weight_vector: np.ndarray,
        chance_branch_limit: int,
        gradient_flat: tuple[float, ...],
        tt: Optional[dict[tuple[int, int, int], float]] = None,
        tt_max_entries: int = _TT_MAX_ENTRIES_DEFAULT,
    ) -> None:
        self.weights = weight_vector
        self.chance_branch_limit = max(1, min(16, int(chance_branch_limit)))
        self.gradient_flat = gradient_flat
        self.tt = tt if tt is not None else {}
        self.tt_max_entries = max(0, int(tt_max_entries))

    def _maybe_trim_tt(self) -> None:
        if self.tt_max_entries <= 0:
            return
        if len(self.tt) > self.tt_max_entries:
            self.tt.clear()

    def _player(self, board: int, ply: int) -> float:
        if ply <= 0:
            return _evaluate_board(board, self.weights, self.gradient_flat)

        key = (board, ply, 1)
        cached = self.tt.get(key)
        if cached is not None:
            return cached

        best_score = -1e18
        found_move = False

        for direction in (DIR_LEFT, DIR_UP, DIR_DOWN, DIR_RIGHT):
            new_board, gain, moved = _simulate_move_board(board, direction)
            if not moved:
                continue

            found_move = True
            val = (
                gain * self.weights[W_MOVE_SCORE_SCALE]
                + _direction_bias_board(board, direction, self.weights)
                + self._chance(new_board, ply - 1)
            )
            if val > best_score:
                best_score = val

        if not found_move:
            best_score = _evaluate_board(board, self.weights, self.gradient_flat) - self.weights[W_TERMINAL_PENALTY]

        self.tt[key] = best_score
        return best_score

    def _chance(self, board: int, ply: int) -> float:
        key = (board, ply, 0)
        cached = self.tt.get(key)
        if cached is not None:
            return cached

        empties = [idx for idx in range(16) if _get_cell_exp(board, idx) == 0]
        if not empties:
            value = self._player(board, ply)
            self.tt[key] = value
            return value

        sample_count = min(len(empties), self.chance_branch_limit)
        seed = _board_sampling_seed(board, ply)
        sampled = _sample_positions_deterministic(empties, sample_count, seed)

        total = 0.0
        for idx in sampled:
            shift = idx * 4
            b2 = board | (1 << shift)
            b4 = board | (2 << shift)
            total += 0.9 * self._player(b2, ply)
            total += 0.1 * self._player(b4, ply)

        value = total / float(sample_count)
        self.tt[key] = value
        return value

    def best_move_int(self, board: int, ply: int) -> int:
        self._maybe_trim_tt()

        best_score = -1e18
        best_move = -1
        winning_move = -1
        winning_exp = -1
        winning_gain = -1

        next_ply = max(ply - 1, 0)

        for direction in (DIR_LEFT, DIR_UP, DIR_DOWN, DIR_RIGHT):
            new_board, gain, moved = _simulate_move_board(board, direction)
            if not moved:
                continue

            new_max_exp, _ = _max_exp_and_idx(new_board)
            if new_max_exp >= 11:  # 2048 exponent
                if new_max_exp > winning_exp or (new_max_exp == winning_exp and gain > winning_gain):
                    winning_move = direction
                    winning_exp = new_max_exp
                    winning_gain = gain
                continue

            score = (
                gain * self.weights[W_MOVE_SCORE_SCALE]
                + _direction_bias_board(board, direction, self.weights)
                + self._chance(new_board, next_ply)
            )
            if score > best_score:
                best_score = score
                best_move = direction

        if winning_move != -1:
            return winning_move
        return best_move


def get_best_move_numba(
    grid: np.ndarray,
    ply: int,
    gradient_weights: np.ndarray,
    weights: np.ndarray,
    max_chance_branches: int,
) -> int:
    """
    Compatibility wrapper for previous numba API.

    Returns direction constant (`DIR_*`) or -1.
    """
    _ensure_tables()
    np_grid = np.asarray(grid, dtype=np.int64)
    board = _grid_to_bitboard(np_grid)
    weight_vec = _coerce_weight_vector(weights)
    flat_gradient = tuple(float(v) for v in np.asarray(gradient_weights, dtype=np.float64).reshape(16))
    searcher = _BitboardSearcher(
        weight_vector=weight_vec,
        chance_branch_limit=max_chance_branches,
        gradient_flat=flat_gradient,
        tt={},
        tt_max_entries=0,
    )
    return searcher.best_move_int(board, max(1, int(ply)))


def _warmup_jit() -> None:
    """Compatibility warmup hook used by UI background warmup path."""
    _ensure_tables()
    test_grid = np.array(
        [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]],
        dtype=np.int64,
    )
    _ = get_best_move_numba(test_grid, 2, GRADIENT_WEIGHTS, DEFAULT_WEIGHT_VECTOR, 8)


_jit_warmed_up = False


class Solver2048:
    """
    2048 AI solver with bitboard expectimax + transposition table.

    Parameters:
    - depth: player-ply search depth (chance nodes do not consume ply)
    - fast_mode: reduce depth for lower latency
    - weights: optional overrides for evaluation weights
    - chance_branch_limit: cap sampled empty cells at chance nodes
    - tt_max_entries: max transposition-table entries before reset
    """

    def __init__(
        self,
        depth: int = 3,
        fast_mode: bool = False,
        weights: Optional[Mapping[str, float]] = None,
        chance_branch_limit: int = 8,
        tt_max_entries: int = _TT_MAX_ENTRIES_DEFAULT,
    ) -> None:
        self.depth = max(1, int(depth))
        self.fast_mode = fast_mode
        self.chance_branch_limit = max(1, min(16, int(chance_branch_limit)))
        self.tt_max_entries = max(0, int(tt_max_entries))
        self._weight_vector = build_weight_vector(weights)
        self._tt: dict[tuple[int, int, int], float] = {}

    def get_move(self, grid) -> Optional[Direction]:
        global _jit_warmed_up

        if not _jit_warmed_up:
            _warmup_jit()
            _jit_warmed_up = True

        _ensure_tables()

        np_grid = np.array(grid, dtype=np.int64) if isinstance(grid, list) else np.asarray(grid, dtype=np.int64)
        board = _grid_to_bitboard(np_grid)

        empty_count = _count_empty_board(board)
        max_exp, _ = _max_exp_and_idx(board)

        effective_depth = self.depth
        if self.fast_mode:
            effective_depth = min(effective_depth, 2)
        else:
            if empty_count >= 9:
                effective_depth = max(2, effective_depth - 1)
            elif empty_count <= 4:
                effective_depth = min(effective_depth + 1, 6)

            if max_exp >= 10 and empty_count >= 3:  # >= 1024
                effective_depth = min(effective_depth + 1, 6)
            elif max_exp >= 9 and empty_count >= 5:  # >= 512
                effective_depth = min(effective_depth + 1, 6)

        searcher = _BitboardSearcher(
            weight_vector=self._weight_vector,
            chance_branch_limit=self.chance_branch_limit,
            gradient_flat=_FLAT_GRADIENT,
            tt=self._tt,
            tt_max_entries=self.tt_max_entries,
        )
        move_int = searcher.best_move_int(board, effective_depth)
        if move_int == -1:
            return None
        return _INT_TO_DIR.get(move_int)

    def solve_step(self, game) -> bool:
        if game.game_over:
            return False

        direction = self.get_move(game.grid)
        if direction is None:
            return False

        return game.move(direction)


# Legacy wrappers for compatibility.
def get_empty_cells(grid):
    return [(r, c) for r in range(4) for c in range(4) if grid[r][c] == 0]


def get_best_move(
    grid,
    depth: int = 3,
    weights: Optional[Mapping[str, float]] = None,
    chance_branch_limit: int = 8,
) -> Optional[Direction]:
    solver = Solver2048(
        depth=max(1, int(depth)),
        fast_mode=False,
        weights=weights,
        chance_branch_limit=max(1, min(16, int(chance_branch_limit))),
    )
    return solver.get_move(grid)
