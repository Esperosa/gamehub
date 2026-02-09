"""
2048 AI Solver using Expectimax with Numba JIT optimization.

Design goals:
- Keep UI responsive by running heavy kernels in background workers.
- Favor robust board survival (empty-space and monotonicity aware).
- Keep behavior tunable via explicit weight overrides for benchmarking.
"""

from __future__ import annotations

from enum import Enum
from typing import Mapping, Optional

import numpy as np

try:
    from numba import njit
except ImportError:
    # Fallback for environments where numba is not available (e.g. packaged builds).
    def njit(*args, **kwargs):
        def decorator(func):
            return func

        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator


def _jit(*args, **kwargs):
    """
    Shared JIT decorator settings for hot paths.

    `nogil=True` allows heavy numeric kernels to run without holding the
    Python GIL, so UI/event callbacks stay responsive while solver work runs
    in background threads.
    """
    # Do not use disk cache here: this solver is loaded under multiple module
    # aliases (plugin layer vs direct import), and numba cache metadata can
    # then reference a module name that is unavailable in another load path.
    opts = {"nogil": True}
    opts.update(kwargs)
    if args:
        return njit(*args, **opts)
    return njit(**opts)


class Direction(Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


# Direction constants for Numba (cannot use Enum inside njit functions)
DIR_UP = 0
DIR_DOWN = 1
DIR_LEFT = 2
DIR_RIGHT = 3

# Gradient matrix for snake-like board ordering (top-left anchored)
GRADIENT_WEIGHTS = np.array(
    [
        [32768.0, 16384.0, 8192.0, 4096.0],
        [256.0, 512.0, 1024.0, 2048.0],
        [128.0, 64.0, 32.0, 16.0],
        [1.0, 2.0, 4.0, 8.0],
    ],
    dtype=np.float64,
)

# Tunable evaluation weights (CLI-friendly names)
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

# Index constants for numba-friendly vector access
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
        0.85,  # gradient
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


def get_default_weights() -> dict[str, float]:
    """Return default solver weights as a plain dictionary."""
    return {key: float(DEFAULT_WEIGHT_VECTOR[idx]) for key, idx in _WEIGHT_INDEX.items()}


def build_weight_vector(overrides: Optional[Mapping[str, float]] = None) -> np.ndarray:
    """
    Build a numba-friendly weight vector.

    Unknown keys raise KeyError so CLI tuning fails loudly and early.
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


@_jit
def _slide_row_left(row):
    """Slide a row left and return (new_row, score, changed)."""
    result = np.zeros(4, dtype=np.int64)
    score = 0
    pos = 0
    prev = -1

    for i in range(4):
        if row[i] != 0:
            if prev == -1:
                prev = row[i]
            elif prev == row[i]:
                result[pos] = prev * 2
                score += prev * 2
                pos += 1
                prev = -1
            else:
                result[pos] = prev
                pos += 1
                prev = row[i]

    if prev != -1:
        result[pos] = prev

    changed = False
    for i in range(4):
        if result[i] != row[i]:
            changed = True
            break

    return result, score, changed


@_jit
def _rotate_90_cw(grid):
    """Rotate grid 90 degrees clockwise."""
    result = np.zeros((4, 4), dtype=np.int64)
    for i in range(4):
        for j in range(4):
            result[i, j] = grid[3 - j, i]
    return result


@_jit
def _rotate_90_ccw(grid):
    """Rotate grid 90 degrees counter-clockwise."""
    result = np.zeros((4, 4), dtype=np.int64)
    for i in range(4):
        for j in range(4):
            result[i, j] = grid[j, 3 - i]
    return result


@_jit
def simulate_move_numba(grid, direction):
    """Simulate a move without spawning. Returns (new_grid, score, moved)."""
    if direction == DIR_LEFT:
        rotations = 0
    elif direction == DIR_DOWN:
        rotations = 1
    elif direction == DIR_RIGHT:
        rotations = 2
    else:  # DIR_UP
        rotations = 3

    g = grid.copy()
    for _ in range(rotations):
        g = _rotate_90_cw(g)

    new_grid = np.zeros((4, 4), dtype=np.int64)
    total_score = 0
    any_moved = False

    for r in range(4):
        new_row, score, changed = _slide_row_left(g[r])
        new_grid[r] = new_row
        total_score += score
        if changed:
            any_moved = True

    for _ in range(rotations):
        new_grid = _rotate_90_ccw(new_grid)

    return new_grid, total_score, any_moved


@_jit
def count_empty(grid):
    """Count empty cells."""
    count = 0
    for r in range(4):
        for c in range(4):
            if grid[r, c] == 0:
                count += 1
    return count


@_jit
def max_tile_numba(grid):
    """Return maximum tile value on grid."""
    max_tile = 0
    for r in range(4):
        for c in range(4):
            if grid[r, c] > max_tile:
                max_tile = grid[r, c]
    return max_tile


@_jit
def _count_tiles_and_pair_stats(grid, target):
    """
    Return (count, has_adjacent_pair, min_pair_distance) for target value.

    min_pair_distance is only relevant when count >= 2.
    """
    rows = np.empty(16, dtype=np.int64)
    cols = np.empty(16, dtype=np.int64)
    count = 0
    has_adjacent = False
    min_dist = 99

    for r in range(4):
        for c in range(4):
            if grid[r, c] == target:
                rows[count] = r
                cols[count] = c
                count += 1

    if count >= 2:
        for i in range(count):
            r = rows[i]
            c = cols[i]
            if r + 1 < 4 and grid[r + 1, c] == target:
                has_adjacent = True
            if c + 1 < 4 and grid[r, c + 1] == target:
                has_adjacent = True

        for i in range(count):
            for j in range(i + 1, count):
                dist = abs(rows[i] - rows[j]) + abs(cols[i] - cols[j])
                if dist < min_dist:
                    min_dist = dist

    return count, has_adjacent, min_dist


@_jit
def near_2048_potential_numba(grid):
    """
    Adaptive tactical bonus for building/merging 1024 pairs safely.

    This is a soft objective:
    - stronger when board is safe (more empties),
    - weaker when board is cramped (to avoid suicidal play).
    """
    max_tile = max_tile_numba(grid)
    if max_tile < 512:
        return 0.0

    empty_count = count_empty(grid)
    safety = empty_count / 8.0
    if safety > 1.0:
        safety = 1.0
    if safety < 0.15:
        safety = 0.15

    count_1024, adj_1024, dist_1024 = _count_tiles_and_pair_stats(grid, 1024)
    count_512, adj_512, dist_512 = _count_tiles_and_pair_stats(grid, 512)
    score = 0.0

    if max_tile >= 1024:
        score += count_1024 * 520.0
        if adj_1024:
            score += 4600.0
        elif count_1024 >= 2:
            proximity = 2600.0 - dist_1024 * 420.0
            if proximity > 0.0:
                score += proximity

        score += count_512 * 140.0
        if count_1024 == 1 and count_512 >= 2:
            score += 900.0
    else:
        score += count_512 * 220.0
        if adj_512:
            score += 1700.0
        elif count_512 >= 2:
            proximity = 1200.0 - dist_512 * 180.0
            if proximity > 0.0:
                score += proximity

    if grid[0, 0] == max_tile:
        score += 350.0
    elif max_tile >= 1024:
        score -= 450.0

    return score * safety


@_jit
def log2_fast(x):
    """Fast log2 for powers of two integers."""
    if x <= 0:
        return 0.0
    result = 0.0
    while x > 1:
        x = x // 2
        result += 1.0
    return result


@_jit
def _global_monotonicity_penalty(grid):
    """
    Monotonicity penalty across all rows/cols.

    Lower is better; we reward monotonic boards by subtracting this penalty.
    """
    penalty = 0.0

    # Rows
    for r in range(4):
        inc = 0.0
        dec = 0.0
        for c in range(3):
            a = log2_fast(grid[r, c])
            b = log2_fast(grid[r, c + 1])
            if a > b:
                inc += a - b
            else:
                dec += b - a
        penalty += inc if inc < dec else dec

    # Columns
    for c in range(4):
        inc = 0.0
        dec = 0.0
        for r in range(3):
            a = log2_fast(grid[r, c])
            b = log2_fast(grid[r + 1, c])
            if a > b:
                inc += a - b
            else:
                dec += b - a
        penalty += inc if inc < dec else dec

    return penalty


@_jit
def _direction_bias_numba(grid, direction, weights):
    """Soft direction preference; never hard-bans a direction."""
    bias = 0.0

    if direction == DIR_LEFT:
        bias += weights[W_LEFT_BIAS]
    elif direction == DIR_UP:
        bias += weights[W_UP_BIAS]
    elif direction == DIR_RIGHT:
        bias -= weights[W_RIGHT_PENALTY]
    else:  # DIR_DOWN
        bias -= weights[W_DOWN_PENALTY]

    max_tile = 0
    max_r = 0
    max_c = 0
    for r in range(4):
        for c in range(4):
            if grid[r, c] > max_tile:
                max_tile = grid[r, c]
                max_r = r
                max_c = c

    if max_r == 0 and max_c == 0:
        if direction == DIR_DOWN and grid[1, 0] < max_tile:
            bias -= weights[W_CORNER_BREAK_PENALTY]
        if direction == DIR_RIGHT and grid[0, 1] < max_tile:
            bias -= weights[W_CORNER_BREAK_PENALTY]

    return bias


@_jit
def evaluate_grid_numba(grid, gradient_weights, weights):
    """Evaluate board state with balanced heuristics."""
    score = 0.0

    max_tile = 0
    max_r, max_c = 0, 0
    gradient_score = 0.0
    smoothness_penalty = 0.0
    merge_score = 0.0

    # Gradient score + max-tile position tracking + smoothness/merge opportunities.
    for r in range(4):
        for c in range(4):
            cell = grid[r, c]
            if cell > max_tile:
                max_tile = cell
                max_r, max_c = r, c

            if cell > 0:
                log_val = log2_fast(cell)
                gradient_score += gradient_weights[r, c] * log_val

                if c + 1 < 4 and grid[r, c + 1] > 0:
                    diff = abs(log_val - log2_fast(grid[r, c + 1]))
                    smoothness_penalty += diff * diff
                    if cell == grid[r, c + 1]:
                        merge_score += log_val
                if r + 1 < 4 and grid[r + 1, c] > 0:
                    diff = abs(log_val - log2_fast(grid[r + 1, c]))
                    smoothness_penalty += diff * diff
                    if cell == grid[r + 1, c]:
                        merge_score += log_val

    score += weights[W_GRADIENT] * gradient_score

    # Corner anchoring, but less dominant than before.
    if max_r == 0 and max_c == 0:
        score += weights[W_CORNER_BONUS]
    else:
        score -= (max_r + max_c) * weights[W_CORNER_DIST_PENALTY]

    empty_count = count_empty(grid)
    score += weights[W_EMPTY] * float(empty_count * empty_count)

    mono_penalty = _global_monotonicity_penalty(grid)
    score -= weights[W_MONOTONICITY] * mono_penalty

    score -= weights[W_SMOOTHNESS] * smoothness_penalty
    score += weights[W_MERGE] * merge_score

    score += weights[W_NEAR_2048] * near_2048_potential_numba(grid)

    return score


@_jit
def _collect_empty_cells(grid, rows, cols):
    """Collect empty-cell coordinates into preallocated arrays."""
    count = 0
    for r in range(4):
        for c in range(4):
            if grid[r, c] == 0:
                rows[count] = r
                cols[count] = c
                count += 1
    return count


@_jit
def expectimax_player_numba(grid, ply, gradient_weights, weights, max_chance_branches):
    """
    Player node: maximize over legal moves.

    `ply` counts player turns. Chance nodes do not consume ply.
    """
    if ply <= 0:
        return evaluate_grid_numba(grid, gradient_weights, weights)

    best_score = -1e18
    found_move = False

    for direction in (DIR_LEFT, DIR_UP, DIR_DOWN, DIR_RIGHT):
        new_grid, move_score, moved = simulate_move_numba(grid, direction)
        if not moved:
            continue

        found_move = True
        val = (
            move_score * weights[W_MOVE_SCORE_SCALE]
            + _direction_bias_numba(grid, direction, weights)
            + expectimax_chance_numba(
                new_grid,
                ply - 1,
                gradient_weights,
                weights,
                max_chance_branches,
            )
        )
        if val > best_score:
            best_score = val

    if not found_move:
        return evaluate_grid_numba(grid, gradient_weights, weights) - weights[W_TERMINAL_PENALTY]

    return best_score


@_jit
def expectimax_chance_numba(grid, ply, gradient_weights, weights, max_chance_branches):
    """
    Chance node: expected value over spawn outcomes.

    Chance node keeps the same `ply` (player-ply semantics).
    """
    empty_rows = np.empty(16, dtype=np.int64)
    empty_cols = np.empty(16, dtype=np.int64)
    empty_count = _collect_empty_cells(grid, empty_rows, empty_cols)

    if empty_count == 0:
        return expectimax_player_numba(grid, ply, gradient_weights, weights, max_chance_branches)

    sample_count = empty_count
    if max_chance_branches > 0 and sample_count > max_chance_branches:
        sample_count = max_chance_branches

    total = 0.0
    for i in range(sample_count):
        idx = (i * empty_count) // sample_count
        r = empty_rows[idx]
        c = empty_cols[idx]

        g2 = grid.copy()
        g2[r, c] = 2
        total += 0.9 * expectimax_player_numba(
            g2,
            ply,
            gradient_weights,
            weights,
            max_chance_branches,
        )

        g4 = grid.copy()
        g4[r, c] = 4
        total += 0.1 * expectimax_player_numba(
            g4,
            ply,
            gradient_weights,
            weights,
            max_chance_branches,
        )

    return total / float(sample_count)


@_jit
def get_best_move_numba(grid, ply, gradient_weights, weights, max_chance_branches):
    """Return best move direction constant or -1 when no legal move exists."""
    best_score = -1e18
    best_move = -1
    winning_move = -1
    winning_tile = -1
    winning_gain = -1

    next_ply = ply - 1
    if next_ply < 0:
        next_ply = 0

    for direction in (DIR_LEFT, DIR_UP, DIR_DOWN, DIR_RIGHT):
        new_grid, move_score, moved = simulate_move_numba(grid, direction)
        if not moved:
            continue

        # Tactical override: if move immediately reaches 2048+, prioritize it.
        new_max = max_tile_numba(new_grid)
        if new_max >= 2048:
            if new_max > winning_tile or (new_max == winning_tile and move_score > winning_gain):
                winning_move = direction
                winning_tile = new_max
                winning_gain = move_score
            continue

        score = (
            move_score * weights[W_MOVE_SCORE_SCALE]
            + _direction_bias_numba(grid, direction, weights)
            + expectimax_chance_numba(
                new_grid,
                next_ply,
                gradient_weights,
                weights,
                max_chance_branches,
            )
        )
        if score > best_score:
            best_score = score
            best_move = direction

    if winning_move != -1:
        return winning_move

    return best_move


# Map between Direction enum and numba constants
_INT_TO_DIR = {
    DIR_UP: Direction.UP,
    DIR_DOWN: Direction.DOWN,
    DIR_LEFT: Direction.LEFT,
    DIR_RIGHT: Direction.RIGHT,
}


def _warmup_jit():
    """Warm up JIT compilation on first call."""
    test_grid = np.array(
        [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]],
        dtype=np.int64,
    )
    get_best_move_numba(test_grid, 2, GRADIENT_WEIGHTS, DEFAULT_WEIGHT_VECTOR, 8)


# Flag to track whether JIT warmup already happened.
_jit_warmed_up = False


class Solver2048:
    """
    2048 AI solver with expectimax + tunable heuristics.

    Parameters:
    - depth: player-ply search depth (chance nodes do not consume ply)
    - fast_mode: reduce depth for lower latency
    - weights: optional overrides for evaluation weights
    - chance_branch_limit: cap sampled empty cells at chance nodes
    """

    def __init__(
        self,
        depth: int = 2,
        fast_mode: bool = False,
        weights: Optional[Mapping[str, float]] = None,
        chance_branch_limit: int = 8,
    ):
        self.depth = max(1, int(depth))
        self.fast_mode = fast_mode
        self.chance_branch_limit = max(1, min(16, int(chance_branch_limit)))
        self._weight_vector = build_weight_vector(weights)

    def get_move(self, grid) -> Optional[Direction]:
        """Get best move with adaptive player-ply depth."""
        global _jit_warmed_up

        # Lazy warmup - only on first AI use, not on import.
        if not _jit_warmed_up:
            _warmup_jit()
            _jit_warmed_up = True

        # Convert to numpy if needed.
        if isinstance(grid, list):
            np_grid = np.array(grid, dtype=np.int64)
        else:
            np_grid = np.asarray(grid, dtype=np.int64)

        empty_count = count_empty(np_grid)
        max_tile = max_tile_numba(np_grid)

        effective_depth = self.depth
        if self.fast_mode:
            effective_depth = min(effective_depth, 2)
        else:
            # Keep search responsive on open boards; deepen as board tightens.
            if empty_count >= 9:
                effective_depth = max(2, effective_depth - 1)
            elif empty_count <= 3:
                effective_depth = min(effective_depth + 1, 5)

            if max_tile >= 1024 and empty_count >= 4:
                effective_depth = min(effective_depth + 1, 5)
            elif max_tile >= 512 and empty_count >= 6:
                effective_depth = min(effective_depth + 1, 5)

        move_int = get_best_move_numba(
            np_grid,
            effective_depth,
            GRADIENT_WEIGHTS,
            self._weight_vector,
            self.chance_branch_limit,
        )
        if move_int == -1:
            return None

        return _INT_TO_DIR.get(move_int)

    def solve_step(self, game) -> bool:
        """Make one solving step."""
        if game.game_over:
            return False

        direction = self.get_move(game.grid)
        if direction is None:
            return False

        return game.move(direction)


# Legacy wrappers for compatibility.
def get_empty_cells(grid):
    """Get list of empty cell coordinates."""
    return [(r, c) for r in range(4) for c in range(4) if grid[r][c] == 0]


def get_best_move(
    grid,
    depth: int = 2,
    weights: Optional[Mapping[str, float]] = None,
    chance_branch_limit: int = 8,
) -> Optional[Direction]:
    """Get best move with optional heuristic overrides."""
    np_grid = np.array(grid, dtype=np.int64) if isinstance(grid, list) else np.asarray(grid, dtype=np.int64)
    weight_vector = build_weight_vector(weights)
    move_int = get_best_move_numba(
        np_grid,
        max(1, int(depth)),
        GRADIENT_WEIGHTS,
        weight_vector,
        max(1, min(16, int(chance_branch_limit))),
    )
    if move_int == -1:
        return None
    return _INT_TO_DIR.get(move_int)
