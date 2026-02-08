"""
Sudoku Engine - Generation and Solving

Supports multiple board sizes:
- 4×4 (2×2 boxes) - Easy intro
- 6×6 (2×3 boxes) - Medium
- 9×9 (3×3 boxes) - Classic
- 16×16 (4×4 boxes) - Expert

All puzzles are guaranteed to have exactly one solution.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple, Set

from hub.solver_contract import Hint, SolveStatus, SolverResult


_SIZE_TO_BOX = {
    4: (2, 2),
    6: (2, 3),
    9: (3, 3),
    16: (4, 4),
}

_DIFFICULTY_EMPTY_RANGES = {
    4: {
        "easy": (0.30, 0.38),
        "medium": (0.42, 0.50),
        "hard": (0.52, 0.60),
    },
    6: {
        "easy": (0.34, 0.42),
        "medium": (0.47, 0.55),
        "hard": (0.56, 0.64),
    },
    9: {
        "easy": (0.35, 0.42),
        "medium": (0.50, 0.57),
        "hard": (0.60, 0.68),
    },
    16: {
        "easy": (0.35, 0.43),
        "medium": (0.44, 0.52),
        "hard": (0.53, 0.60),
    },
}

_UNIQUENESS_CHECK_TIMEOUT_S = {
    16: {
        "easy": 0.03,
        "medium": 0.05,
        "hard": 0.05,
    },
}


@dataclass
class SudokuConfig:
    """Configuration for a Sudoku puzzle variant."""

    size: int  # 4, 6, 9, or 16
    box_rows: int
    box_cols: int

    def __post_init__(self) -> None:
        if self.box_rows * self.box_cols != self.size:
            raise ValueError(
                f"Invalid Sudoku box geometry: {self.box_rows}x{self.box_cols} for size {self.size}."
            )

    @property
    def num_range(self) -> int:
        """Numbers used for this variant: 1..N."""
        return self.size

    @staticmethod
    def from_size(size: int) -> "SudokuConfig":
        """Create config for supported standard Sudoku sizes."""
        try:
            box_rows, box_cols = _SIZE_TO_BOX[size]
        except KeyError as exc:
            supported = ", ".join(str(v) for v in sorted(_SIZE_TO_BOX))
            raise ValueError(f"Unsupported Sudoku size {size}. Supported sizes: {supported}.") from exc
        return SudokuConfig(size=size, box_rows=box_rows, box_cols=box_cols)


@dataclass
class SudokuState:
    """State of a sudoku game."""
    config: SudokuConfig
    board: List[int]  # 0 = empty, 1-N = filled
    initial: List[bool]  # True = given clue, can't be changed
    solution: List[int]  # The correct solution
    seed: int
    
    @property
    def size(self) -> int:
        return self.config.size
    
    def get(self, row: int, col: int) -> int:
        return self.board[row * self.size + col]
    
    def set(self, row: int, col: int, value: int) -> None:
        idx = row * self.size + col
        if not self.initial[idx] and 0 <= value <= self.config.num_range:
            self.board[idx] = value
    
    def is_initial(self, row: int, col: int) -> bool:
        return self.initial[row * self.size + col]
    
    def is_correct(self, row: int, col: int) -> bool:
        idx = row * self.size + col
        return self.board[idx] == self.solution[idx]
    
    def get_hint(self) -> Optional[Tuple[int, int, int]]:
        """Get a hint: (row, col, correct_value) for an empty or wrong cell."""
        # First try empty cells
        empty = []
        wrong = []
        for r in range(self.size):
            for c in range(self.size):
                idx = r * self.size + c
                if not self.initial[idx]:
                    if self.board[idx] == 0:
                        empty.append((r, c))
                    elif self.board[idx] != self.solution[idx]:
                        wrong.append((r, c))
        
        # Prioritize wrong cells, then empty
        if wrong:
            r, c = random.choice(wrong)
        elif empty:
            r, c = random.choice(empty)
        else:
            return None
        
        idx = r * self.size + c
        return (r, c, self.solution[idx])

    def get_hint_result(self) -> Optional[Hint]:
        hint = self.get_hint()
        if hint is None:
            return None
        row, col, value = hint
        return Hint(
            type="cell_value",
            cells=((row, col),),
            explanation=f"Place value {value} in this cell.",
            confidence=0.95,
            payload={"value": int(value)},
        )
    
    def is_complete(self) -> bool:
        """Check if puzzle is fully filled and satisfies Sudoku constraints."""
        size = self.size
        expected = set(range(1, self.config.num_range + 1))

        # Must be fully filled and within valid range.
        for v in self.board:
            if v < 1 or v > self.config.num_range:
                return False

        # Given clues must stay unchanged.
        for idx, is_given in enumerate(self.initial):
            if is_given and self.board[idx] != self.solution[idx]:
                return False

        # Rows
        for r in range(size):
            row_vals = self.board[r * size : (r + 1) * size]
            if set(row_vals) != expected:
                return False

        # Columns
        for c in range(size):
            col_vals = [self.board[r * size + c] for r in range(size)]
            if set(col_vals) != expected:
                return False

        # Boxes
        box_r = self.config.box_rows
        box_c = self.config.box_cols
        for start_r in range(0, size, box_r):
            for start_c in range(0, size, box_c):
                vals: List[int] = []
                for r in range(start_r, start_r + box_r):
                    for c in range(start_c, start_c + box_c):
                        vals.append(self.board[r * size + c])
                if set(vals) != expected:
                    return False

        return True
    
    def count_filled(self) -> int:
        return sum(1 for v in self.board if v != 0)
    
    def count_empty(self) -> int:
        return sum(1 for v in self.board if v == 0)
    
    def get_conflicts(self, row: int, col: int) -> Set[Tuple[int, int]]:
        """Get cells that conflict with the given cell."""
        conflicts = set()
        val = self.get(row, col)
        if val == 0:
            return conflicts
        
        size = self.size
        box_r = self.config.box_rows
        box_c = self.config.box_cols
        
        # Row conflicts
        for c in range(size):
            if c != col and self.get(row, c) == val:
                conflicts.add((row, c))
        
        # Column conflicts
        for r in range(size):
            if r != row and self.get(r, col) == val:
                conflicts.add((r, col))
        
        # Box conflicts
        box_start_r = (row // box_r) * box_r
        box_start_c = (col // box_c) * box_c
        for r in range(box_start_r, box_start_r + box_r):
            for c in range(box_start_c, box_start_c + box_c):
                if (r, c) != (row, col) and self.get(r, c) == val:
                    conflicts.add((r, c))
        
        return conflicts
    
    def has_any_conflict(self) -> bool:
        """Check if any cell has conflicts."""
        for r in range(self.size):
            for c in range(self.size):
                if self.get(r, c) != 0 and self.get_conflicts(r, c):
                    return True
        return False


class SudokuSolver:
    """Backtracking sudoku solver."""
    
    def __init__(self, config: SudokuConfig):
        self.config = config
        self.size = config.size
        self.box_r = config.box_rows
        self.box_c = config.box_cols
        self.values = list(range(1, config.num_range + 1))
        self._full_mask = (1 << self.size) - 1
        box_cols = self.size // self.box_c
        self._box_index = [
            ((idx // self.size) // self.box_r) * box_cols + ((idx % self.size) // self.box_c)
            for idx in range(self.size * self.size)
        ]
    
    def is_valid(self, board: List[int], row: int, col: int, num: int) -> bool:
        """Check if placing num at (row, col) is valid."""
        size = self.size
        # Row check
        for c in range(size):
            if board[row * size + c] == num:
                return False
        
        # Column check
        for r in range(size):
            if board[r * size + col] == num:
                return False
        
        # Box check
        box_start_r = (row // self.box_r) * self.box_r
        box_start_c = (col // self.box_c) * self.box_c
        for r in range(box_start_r, box_start_r + self.box_r):
            for c in range(box_start_c, box_start_c + self.box_c):
                if board[r * size + c] == num:
                    return False
        
        return True
    
    def solve(self, board: List[int]) -> Optional[List[int]]:
        """Solve the puzzle, return solution or None if unsolvable."""
        prepared = self._prepare_search_state(board)
        if prepared is None:
            return None
        work, row_free, col_free, box_free = prepared
        if self._solve_mask_recursive(work, row_free, col_free, box_free):
            return work
        return None

    def enumerate_solutions(
        self,
        board: List[int],
        limit: Optional[int] = None,
    ) -> List[List[int]]:
        """
        Enumerate valid solutions for a puzzle.

        If `limit` is set, stops once that many solutions are found.
        """
        work = board.copy()
        out: List[List[int]] = []
        self._enumerate_recursive(work, out, limit)
        return out

    def solve_result(
        self,
        board: List[int],
        timeout: Optional[float] = None,
        detect_multiple: bool = True,
    ) -> SolverResult:
        """Normalized solver output for hub-level consumption."""
        start = time.perf_counter()
        if timeout is not None and timeout <= 0:
            return SolverResult(
                status=SolveStatus.TIMEOUT,
                solution=None,
                solutions_found=None,
                elapsed_ms=0,
                message="Timeout budget is zero.",
            )

        solved = self.solve(board)
        elapsed = time.perf_counter() - start
        elapsed_ms = int(elapsed * 1000)
        if timeout is not None and elapsed > timeout:
            return SolverResult(
                status=SolveStatus.TIMEOUT,
                solution=None,
                solutions_found=None,
                elapsed_ms=elapsed_ms,
                message="Solver timed out before completion.",
            )

        if solved is None:
            return SolverResult(
                status=SolveStatus.UNSOLVABLE,
                solution=None,
                solutions_found=0,
                elapsed_ms=elapsed_ms,
                message="No satisfying assignment found.",
            )

        status = SolveStatus.SOLVED
        solutions_found: Optional[int] = None
        if detect_multiple:
            count = self.count_solutions(board, limit=2)
            solutions_found = count
            elapsed = time.perf_counter() - start
            elapsed_ms = int(elapsed * 1000)
            if timeout is not None and elapsed > timeout:
                return SolverResult(
                    status=SolveStatus.TIMEOUT,
                    solution=None,
                    solutions_found=None,
                    elapsed_ms=elapsed_ms,
                    message="Solution counting timed out.",
                )
            if count > 1:
                status = SolveStatus.MULTIPLE_SOLUTIONS

        return SolverResult(
            status=status,
            solution=solved,
            solutions_found=solutions_found,
            elapsed_ms=elapsed_ms,
            message="Solved" if status == SolveStatus.SOLVED else "Multiple valid solutions found.",
        )
    
    def _solve_recursive(self, board: List[int]) -> bool:
        """Recursive backtracking solver."""
        empty_idx, candidates = self._next_empty_with_candidates(board)
        if empty_idx == -1:
            return True  # Solved
        if not candidates:
            return False

        for num in candidates:
            board[empty_idx] = num
            if self._solve_recursive(board):
                return True
            board[empty_idx] = 0

        return False

    def _enumerate_recursive(
        self,
        board: List[int],
        out: List[List[int]],
        limit: Optional[int],
    ) -> bool:
        """Returns True if enumeration should stop early."""
        if limit is not None and len(out) >= limit:
            return True

        empty_idx, candidates = self._next_empty_with_candidates(board)
        if empty_idx == -1:
            out.append(board.copy())
            return limit is not None and len(out) >= limit
        if not candidates:
            return False

        for num in candidates:
            board[empty_idx] = num
            should_stop = self._enumerate_recursive(board, out, limit)
            board[empty_idx] = 0
            if should_stop:
                return True
        return False
    
    def count_solutions(self, board: List[int], limit: int = 2) -> int:
        """Count solutions up to limit. Returns exact count if <= limit."""
        if limit <= 0:
            return 0
        prepared = self._prepare_search_state(board)
        if prepared is None:
            return 0
        work, row_free, col_free, box_free = prepared
        return self._count_mask_recursive(work, row_free, col_free, box_free, limit)

    def has_alternative_solution(self, board: List[int], reference_solution: List[int]) -> bool:
        """
        Return True when puzzle has any valid solution different from reference_solution.

        This is equivalent to uniqueness testing when reference_solution is known valid.
        """
        return self.has_alternative_solution_with_timeout(board, reference_solution, timeout_s=None)

    def has_alternative_solution_with_timeout(
        self,
        board: List[int],
        reference_solution: List[int],
        timeout_s: Optional[float],
    ) -> bool:
        """
        Return True when puzzle has any valid alternative solution.

        If timeout_s is set and the check exceeds the budget, returns True conservatively.
        """
        if len(reference_solution) != self.size * self.size:
            return False
        prepared = self._prepare_search_state(board)
        if prepared is None:
            return False
        work, row_free, col_free, box_free = prepared
        self._alt_deadline = None if timeout_s is None else (time.perf_counter() + timeout_s)
        self._alt_clock_budget = 0
        self._alt_timed_out = False
        found = self._exists_alternative_recursive(work, row_free, col_free, box_free, reference_solution, False)
        if self._alt_timed_out:
            return True
        return found
    
    def _count_recursive(self, board: List[int]) -> bool:
        """Returns True if should stop counting."""
        if self._solution_count >= self._solution_limit:
            return True

        empty_idx, candidates = self._next_empty_with_candidates(board)
        if empty_idx == -1:
            self._solution_count += 1
            return self._solution_count >= self._solution_limit
        if not candidates:
            return False

        for num in candidates:
            board[empty_idx] = num
            if self._count_recursive(board):
                board[empty_idx] = 0
                return True
            board[empty_idx] = 0

        return False

    def _prepare_search_state(
        self, board: List[int]
    ) -> Optional[Tuple[List[int], List[int], List[int], List[int]]]:
        total = self.size * self.size
        if len(board) != total:
            return None

        work = [int(v) for v in board]
        row_free = [self._full_mask] * self.size
        col_free = [self._full_mask] * self.size
        box_free = [self._full_mask] * self.size

        for idx, val in enumerate(work):
            if val == 0:
                continue
            if val < 1 or val > self.size:
                return None
            bit = 1 << (val - 1)
            row = idx // self.size
            col = idx % self.size
            box = self._box_index[idx]
            if (row_free[row] & bit) == 0 or (col_free[col] & bit) == 0 or (box_free[box] & bit) == 0:
                return None
            row_free[row] &= ~bit
            col_free[col] &= ~bit
            box_free[box] &= ~bit

        return work, row_free, col_free, box_free

    def _select_cell_mask(
        self, board: List[int], row_free: List[int], col_free: List[int], box_free: List[int]
    ) -> Tuple[int, int]:
        best_idx = -1
        best_mask = 0
        best_count = self.size + 1

        for idx, value in enumerate(board):
            if value != 0:
                continue
            row = idx // self.size
            col = idx % self.size
            box = self._box_index[idx]
            mask = row_free[row] & col_free[col] & box_free[box]
            count = mask.bit_count()
            if count == 0:
                return idx, 0
            if count < best_count:
                best_count = count
                best_idx = idx
                best_mask = mask
                if count == 1:
                    break

        return best_idx, best_mask

    def _solve_mask_recursive(
        self, board: List[int], row_free: List[int], col_free: List[int], box_free: List[int]
    ) -> bool:
        idx, mask = self._select_cell_mask(board, row_free, col_free, box_free)
        if idx == -1:
            return True
        if mask == 0:
            return False

        row = idx // self.size
        col = idx % self.size
        box = self._box_index[idx]

        while mask:
            bit = mask & -mask
            mask ^= bit
            val = bit.bit_length()
            board[idx] = val
            row_free[row] &= ~bit
            col_free[col] &= ~bit
            box_free[box] &= ~bit

            if self._solve_mask_recursive(board, row_free, col_free, box_free):
                return True

            row_free[row] |= bit
            col_free[col] |= bit
            box_free[box] |= bit
            board[idx] = 0

        return False

    def _count_mask_recursive(
        self,
        board: List[int],
        row_free: List[int],
        col_free: List[int],
        box_free: List[int],
        limit: int,
    ) -> int:
        if limit <= 0:
            return 0

        idx, mask = self._select_cell_mask(board, row_free, col_free, box_free)
        if idx == -1:
            return 1
        if mask == 0:
            return 0

        row = idx // self.size
        col = idx % self.size
        box = self._box_index[idx]
        count = 0

        while mask and count < limit:
            bit = mask & -mask
            mask ^= bit
            val = bit.bit_length()
            board[idx] = val
            row_free[row] &= ~bit
            col_free[col] &= ~bit
            box_free[box] &= ~bit

            count += self._count_mask_recursive(board, row_free, col_free, box_free, limit - count)

            row_free[row] |= bit
            col_free[col] |= bit
            box_free[box] |= bit
            board[idx] = 0

        return count

    def _exists_alternative_recursive(
        self,
        board: List[int],
        row_free: List[int],
        col_free: List[int],
        box_free: List[int],
        reference_solution: List[int],
        differs: bool,
    ) -> bool:
        if self._alt_deadline is not None:
            self._alt_clock_budget -= 1
            if self._alt_clock_budget <= 0:
                self._alt_clock_budget = 64
                if time.perf_counter() >= self._alt_deadline:
                    self._alt_timed_out = True
                    return True

        idx, mask = self._select_cell_mask(board, row_free, col_free, box_free)
        if idx == -1:
            return differs
        if mask == 0:
            return False

        row = idx // self.size
        col = idx % self.size
        box = self._box_index[idx]
        ref_val = int(reference_solution[idx])
        ref_bit = 0
        if 1 <= ref_val <= self.size:
            ref_bit = 1 << (ref_val - 1)

        # Try values different from the reference first to find alternatives early.
        non_ref_mask = mask & ~ref_bit
        while non_ref_mask:
            bit = non_ref_mask & -non_ref_mask
            non_ref_mask ^= bit
            val = bit.bit_length()
            board[idx] = val
            row_free[row] &= ~bit
            col_free[col] &= ~bit
            box_free[box] &= ~bit

            if self._exists_alternative_recursive(
                board,
                row_free,
                col_free,
                box_free,
                reference_solution,
                True,
            ):
                return True

            row_free[row] |= bit
            col_free[col] |= bit
            box_free[box] |= bit
            board[idx] = 0

        # Also allow following the reference path; alternative may appear deeper.
        if ref_bit and (mask & ref_bit):
            bit = ref_bit
            board[idx] = ref_val
            row_free[row] &= ~bit
            col_free[col] &= ~bit
            box_free[box] &= ~bit

            if self._exists_alternative_recursive(
                board,
                row_free,
                col_free,
                box_free,
                reference_solution,
                differs,
            ):
                return True

            row_free[row] |= bit
            col_free[col] |= bit
            box_free[box] |= bit
            board[idx] = 0

        return False

    def _next_empty_with_candidates(self, board: List[int]) -> Tuple[int, List[int]]:
        """Return (index, candidates) using MRV. index=-1 when solved."""
        best_idx = -1
        best_candidates: List[int] = []
        size = self.size

        for idx, value in enumerate(board):
            if value != 0:
                continue
            row = idx // size
            col = idx % size
            candidates = [num for num in self.values if self.is_valid(board, row, col, num)]
            if not candidates:
                return idx, []
            if best_idx == -1 or len(candidates) < len(best_candidates):
                best_idx = idx
                best_candidates = candidates
                if len(best_candidates) == 1:
                    break

        return best_idx, best_candidates


class SudokuGenerator:
    """Generate valid sudoku puzzles with unique solutions."""
    
    def __init__(self, config: SudokuConfig):
        self.config = config
        self.solver = SudokuSolver(config)
        self.size = config.size
    
    def generate(self, difficulty: str = "medium", seed: Optional[int] = None) -> SudokuState:
        """Generate a new puzzle with the given difficulty."""
        if seed is None:
            seed = random.randint(0, 2**31 - 1)
        
        rng = random.Random(seed)
        
        # Generate a complete valid board
        solution = self._generate_complete(rng)
        
        # Remove cells based on difficulty
        board, initial = self._remove_cells(solution.copy(), solution, difficulty, rng)
        
        return SudokuState(
            config=self.config,
            board=board,
            initial=initial,
            solution=solution,
            seed=seed,
        )
    
    def _generate_complete(self, rng: random.Random) -> List[int]:
        """Generate a complete valid Sudoku board using pattern + permutations."""
        size = self.size
        box_r = self.config.box_rows
        box_c = self.config.box_cols

        row_group_count = size // box_r
        col_group_count = size // box_c

        row_groups = list(range(row_group_count))
        col_groups = list(range(col_group_count))
        rng.shuffle(row_groups)
        rng.shuffle(col_groups)

        rows: List[int] = []
        cols: List[int] = []

        for g in row_groups:
            inner = list(range(box_r))
            rng.shuffle(inner)
            rows.extend(g * box_r + i for i in inner)

        for g in col_groups:
            inner = list(range(box_c))
            rng.shuffle(inner)
            cols.extend(g * box_c + i for i in inner)

        symbols = list(range(1, size + 1))
        rng.shuffle(symbols)

        board = [0] * (size * size)
        for out_r, src_r in enumerate(rows):
            for out_c, src_c in enumerate(cols):
                pattern_idx = (src_r * box_c + (src_r // box_r) + src_c) % size
                board[out_r * size + out_c] = symbols[pattern_idx]

        return board
    
    def _remove_cells(self, board: List[int], reference_solution: List[int], difficulty: str, 
                      rng: random.Random) -> Tuple[List[int], List[bool]]:
        """Remove cells to create puzzle, ensuring unique solution.
        
        Difficulty analysis:
        - More empty cells = harder (more possibilities to consider)
        - Strategic clue placement matters:
          - Center clues are harder to deduce
          - Corner/edge clues are easier starting points
          - Balanced distribution per row/col helps beginners
        
        Target percentages (% of cells to leave empty) are tuned per board size.
        """
        size = self.size
        total = size * size

        size_targets = _DIFFICULTY_EMPTY_RANGES.get(size)
        if size_targets is None:
            raise ValueError(f"No difficulty targets configured for Sudoku size {size}.")

        pct_min, pct_max = size_targets.get(
            difficulty,
            size_targets["medium"],
        )
        target_empty = int(total * rng.uniform(pct_min, pct_max))
        
        initial = [True] * total
        removed = 0
        uniqueness_timeout = _UNIQUENESS_CHECK_TIMEOUT_S.get(size, {}).get(difficulty)
        
        # Get removal order based on difficulty
        if difficulty == "hard":
            # Hard: remove from center first (harder to deduce)
            cells = self._get_strategic_removal_order(size, rng, prefer_center=True)
        elif difficulty == "easy":
            # Easy: remove from edges first, keep center clues (easier patterns)
            cells = self._get_strategic_removal_order(size, rng, prefer_center=False)
        else:
            # Medium: random order
            cells = list(range(total))
            rng.shuffle(cells)
        
        # Try to remove cells while maintaining unique solution
        for idx in cells:
            if removed >= target_empty:
                break
            
            old_val = board[idx]
            board[idx] = 0
            
            # Unique iff no alternative solution exists besides the known reference.
            if not self.solver.has_alternative_solution_with_timeout(
                board,
                reference_solution,
                timeout_s=uniqueness_timeout,
            ):
                initial[idx] = False
                removed += 1
            else:
                board[idx] = old_val  # Restore - can't remove this cell
        
        return board, initial
    
    def _get_strategic_removal_order(self, size: int, rng: random.Random, 
                                      prefer_center: bool) -> List[int]:
        """
        Get cell indices in a difficulty-biased but still varied order.

        The bias controls whether center or edge cells are more likely to be removed
        first, while randomness prevents near-identical clue layouts across runs.
        """
        cells = list(range(size * size))
        center = (size - 1) / 2.0
        max_dist = abs(0 - center) + abs(0 - center)

        weighted: List[Tuple[float, int]] = []
        for idx in cells:
            r, c = divmod(idx, size)
            dist = abs(r - center) + abs(c - center)
            norm_dist = (dist / max_dist) if max_dist > 0 else 0.0

            # Easy prefers keeping center clues (remove edges first).
            # Hard prefers removing center clues first.
            bias = (1.0 - norm_dist) if prefer_center else norm_dist

            # Keep meaningful bias but preserve strong variability.
            weight = 0.35 + 0.65 * bias
            key = rng.random() ** (1.0 / weight)
            weighted.append((key, idx))

        weighted.sort(reverse=True)
        return [idx for _, idx in weighted]


def create_puzzle(size: int = 9, difficulty: str = "medium", 
                  seed: Optional[int] = None) -> SudokuState:
    """Convenience function to create a new puzzle."""
    config = SudokuConfig.from_size(size)
    generator = SudokuGenerator(config)
    return generator.generate(difficulty, seed)
