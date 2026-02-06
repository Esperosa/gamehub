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
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Set
from copy import deepcopy


@dataclass
class SudokuConfig:
    """Configuration for a sudoku puzzle.
    
    All sudoku variants use numbers 1-9.
    Box sizes create symmetric visual divisions:
    - 3×3: 1 box (entire grid), numbers 1-9 (only 3 unique per row/col)
    - 6×6: 4 boxes in 2×2 layout (each 3×3), cross pattern
    - 9×9: 9 boxes in 3×3 layout (classic sudoku)
    """
    size: int  # 3, 6, or 9
    box_rows: int = 3  # rows per box (always 3 for symmetric boxes)
    box_cols: int = 3  # cols per box (always 3 for symmetric boxes)
    
    @property
    def num_range(self) -> int:
        """Numbers used: always 1-9."""
        return 9
    
    @staticmethod
    def from_size(size: int) -> 'SudokuConfig':
        """Create config with 3×3 boxes for all sizes."""
        # All sizes use 3×3 boxes
        # 3×3: 1 box total (the whole grid is one box)
        # 6×6: 4 boxes (2×2 arrangement) - cross pattern dividers
        # 9×9: 9 boxes (3×3 arrangement) - classic sudoku
        return SudokuConfig(size=size, box_rows=3, box_cols=3)


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
        if not self.initial[idx]:
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
    
    def is_complete(self) -> bool:
        """Check if puzzle is correctly completed."""
        return self.board == self.solution
    
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
        
        # Box conflicts - handle cases where box might extend beyond board
        box_start_r = (row // box_r) * box_r
        box_start_c = (col // box_c) * box_c
        box_end_r = min(box_start_r + box_r, size)
        box_end_c = min(box_start_c + box_c, size)
        for r in range(box_start_r, box_end_r):
            for c in range(box_start_c, box_end_c):
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
    
    def is_valid(self, board: List[int], row: int, col: int, num: int) -> bool:
        """Check if placing num at (row, col) is valid."""
        size = self.size
        idx = row * size + col
        
        # Row check
        for c in range(size):
            if board[row * size + c] == num:
                return False
        
        # Column check
        for r in range(size):
            if board[r * size + col] == num:
                return False
        
        # Box check - handle cases where box might extend beyond board
        box_start_r = (row // self.box_r) * self.box_r
        box_start_c = (col // self.box_c) * self.box_c
        box_end_r = min(box_start_r + self.box_r, size)
        box_end_c = min(box_start_c + self.box_c, size)
        for r in range(box_start_r, box_end_r):
            for c in range(box_start_c, box_end_c):
                if board[r * size + c] == num:
                    return False
        
        return True
    
    def solve(self, board: List[int]) -> Optional[List[int]]:
        """Solve the puzzle, return solution or None if unsolvable."""
        board = board.copy()
        if self._solve_recursive(board):
            return board
        return None
    
    def _solve_recursive(self, board: List[int]) -> bool:
        """Recursive backtracking solver."""
        size = self.size
        
        # Find empty cell
        empty_idx = -1
        for i in range(size * size):
            if board[i] == 0:
                empty_idx = i
                break
        
        if empty_idx == -1:
            return True  # Solved
        
        row = empty_idx // size
        col = empty_idx % size
        
        # Always use 1-9 for all sudoku sizes
        for num in range(1, 10):
            if self.is_valid(board, row, col, num):
                board[empty_idx] = num
                if self._solve_recursive(board):
                    return True
                board[empty_idx] = 0
        
        return False
    
    def count_solutions(self, board: List[int], limit: int = 2) -> int:
        """Count solutions up to limit. Returns exact count if <= limit."""
        self._solution_count = 0
        self._solution_limit = limit
        board = board.copy()
        self._count_recursive(board)
        return self._solution_count
    
    def _count_recursive(self, board: List[int]) -> bool:
        """Returns True if should stop counting."""
        if self._solution_count >= self._solution_limit:
            return True
        
        size = self.size
        
        # Find empty cell with minimum remaining values (MRV heuristic)
        empty_idx = -1
        for i in range(size * size):
            if board[i] == 0:
                empty_idx = i
                break
        
        if empty_idx == -1:
            self._solution_count += 1
            return self._solution_count >= self._solution_limit
        
        row = empty_idx // size
        col = empty_idx % size
        
        # Always use 1-9 for all sudoku sizes
        for num in range(1, 10):
            if self.is_valid(board, row, col, num):
                board[empty_idx] = num
                if self._count_recursive(board):
                    board[empty_idx] = 0
                    return True
                board[empty_idx] = 0
        
        return False


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
        board, initial = self._remove_cells(solution.copy(), difficulty, rng)
        
        return SudokuState(
            config=self.config,
            board=board,
            initial=initial,
            solution=solution,
            seed=seed,
        )
    
    def _generate_complete(self, rng: random.Random) -> List[int]:
        """Generate a complete valid sudoku board using backtracking."""
        size = self.size
        board = [0] * (size * size)
        
        # Use pure backtracking with randomization - works for all sizes
        self._solve_with_rng(board, rng)
        
        return board
    
    def _solve_with_rng(self, board: List[int], rng: random.Random) -> bool:
        """Solve board with randomized number order."""
        size = self.size
        
        # Find empty cell
        empty_idx = -1
        for i in range(size * size):
            if board[i] == 0:
                empty_idx = i
                break
        
        if empty_idx == -1:
            return True
        
        row = empty_idx // size
        col = empty_idx % size
        
        # Always use 1-9 for all sudoku sizes
        nums = list(range(1, 10))
        rng.shuffle(nums)
        
        for num in nums:
            if self.solver.is_valid(board, row, col, num):
                board[empty_idx] = num
                if self._solve_with_rng(board, rng):
                    return True
                board[empty_idx] = 0
        
        return False
    
    def _remove_cells(self, board: List[int], difficulty: str, 
                      rng: random.Random) -> Tuple[List[int], List[bool]]:
        """Remove cells to create puzzle, ensuring unique solution.
        
        Difficulty analysis:
        - More empty cells = harder (more possibilities to consider)
        - Strategic clue placement matters:
          - Center clues are harder to deduce
          - Corner/edge clues are easier starting points
          - Balanced distribution per row/col helps beginners
        
        Target percentages (% of cells to leave empty):
        - Easy:   35-42% empty - plenty of clues, easy deduction
        - Medium: 50-57% empty - balanced challenge
        - Hard:   60-68% empty - minimal clues, requires advanced techniques
        """
        size = self.size
        total = size * size
        
        # Target empty cells based on difficulty with slight randomness
        # The range allows for puzzle variation while keeping consistent difficulty
        difficulty_targets = {
            "easy":   (0.35, 0.42),
            "medium": (0.50, 0.57),
            "hard":   (0.60, 0.68)
        }
        
        pct_min, pct_max = difficulty_targets.get(difficulty, (0.50, 0.57))
        target_pct = rng.uniform(pct_min, pct_max)
        
        # Special case for 3x3: limited by unique solution constraint
        if size == 3:
            # 3×3 has only 9 cells, so we use fixed counts
            target_empty = {"easy": 2, "medium": 4, "hard": 6}.get(difficulty, 4)
        else:
            target_empty = int(total * target_pct)
        
        initial = [True] * total
        removed = 0
        
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
            
            # Check if still has unique solution
            if self.solver.count_solutions(board, limit=2) == 1:
                initial[idx] = False
                removed += 1
            else:
                board[idx] = old_val  # Restore - can't remove this cell
        
        return board, initial
    
    def _get_strategic_removal_order(self, size: int, rng: random.Random, 
                                      prefer_center: bool) -> List[int]:
        """Get cell indices ordered by strategic importance."""
        cells = list(range(size * size))
        center = size // 2
        
        def distance_from_center(idx):
            r, c = idx // size, idx % size
            return abs(r - center) + abs(c - center)
        
        # Sort by distance from center
        cells.sort(key=distance_from_center, reverse=not prefer_center)
        
        # Add some randomness within similar distances
        result = []
        i = 0
        while i < len(cells):
            # Group cells with same distance
            j = i
            while j < len(cells) and distance_from_center(cells[j]) == distance_from_center(cells[i]):
                j += 1
            group = cells[i:j]
            rng.shuffle(group)
            result.extend(group)
            i = j
        
        return result


def create_puzzle(size: int = 9, difficulty: str = "medium", 
                  seed: Optional[int] = None) -> SudokuState:
    """Convenience function to create a new puzzle."""
    config = SudokuConfig.from_size(size)
    generator = SudokuGenerator(config)
    return generator.generate(difficulty, seed)
