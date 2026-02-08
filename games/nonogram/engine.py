"""
Nonogram (Picross/Griddlers) Game Engine

A logic puzzle where you fill in cells based on numeric clues for each row/column.
The clues indicate the lengths of consecutive filled cell blocks in that line.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Set
from pathlib import Path

from hub.solver_contract import Hint, SolveStatus, SolverResult


@dataclass
class NonogramPuzzle:
    """Represents a Nonogram puzzle definition."""
    width: int
    height: int
    row_clues: List[List[int]]  # For each row, list of block lengths
    col_clues: List[List[int]]  # For each column, list of block lengths
    solution: Optional[List[List[bool]]] = None  # True = filled, False = empty
    name: str = ""
    
    def __post_init__(self):
        """Validate puzzle dimensions."""
        assert len(self.row_clues) == self.height
        assert len(self.col_clues) == self.width


@dataclass 
class NonogramState:
    """Represents the current state of a Nonogram puzzle being solved."""
    puzzle: NonogramPuzzle
    # Grid state: 0 = unknown, 1 = filled, -1 = marked empty (X)
    grid: List[List[int]] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.grid:
            self.grid = [[0] * self.puzzle.width for _ in range(self.puzzle.height)]
    
    @classmethod
    def from_puzzle(cls, puzzle: NonogramPuzzle) -> "NonogramState":
        """Create initial state from puzzle."""
        return cls(puzzle=puzzle)
    
    def get_cell(self, row: int, col: int) -> int:
        """Get cell state: 0=unknown, 1=filled, -1=empty."""
        return self.grid[row][col]
    
    def set_cell(self, row: int, col: int, value: int) -> None:
        """Set cell state."""
        self.grid[row][col] = value
    
    def toggle_fill(self, row: int, col: int) -> None:
        """Toggle between unknown and filled."""
        if self.grid[row][col] == 1:
            self.grid[row][col] = 0
        else:
            self.grid[row][col] = 1
    
    def toggle_mark(self, row: int, col: int) -> None:
        """Toggle between unknown and marked empty (X)."""
        if self.grid[row][col] == -1:
            self.grid[row][col] = 0
        else:
            self.grid[row][col] = -1
    
    def clear_cell(self, row: int, col: int) -> None:
        """Clear cell to unknown."""
        self.grid[row][col] = 0
    
    def get_row(self, row: int) -> List[int]:
        """Get a row of the grid."""
        return self.grid[row][:]
    
    def get_col(self, col: int) -> List[int]:
        """Get a column of the grid."""
        return [self.grid[r][col] for r in range(self.puzzle.height)]
    
    def is_complete(self) -> bool:
        """Check if puzzle is completely and correctly solved."""
        for row in range(self.puzzle.height):
            if not self._line_matches_clue(self.get_row(row), self.puzzle.row_clues[row]):
                return False
        for col in range(self.puzzle.width):
            if not self._line_matches_clue(self.get_col(col), self.puzzle.col_clues[col]):
                return False
        return True
    
    def _line_matches_clue(self, line: List[int], clue: List[int]) -> bool:
        """Check if a line matches its clue exactly."""
        # Extract blocks of filled cells
        blocks = []
        current_block = 0
        for cell in line:
            if cell == 1:
                current_block += 1
            else:
                if current_block > 0:
                    blocks.append(current_block)
                    current_block = 0
        if current_block > 0:
            blocks.append(current_block)
        
        # Handle empty line case: clue [0] means no blocks
        if not blocks:
            return clue == [0] or clue == []
        
        return blocks == clue
    
    def check_row_valid(self, row: int) -> bool:
        """Check if row is still solvable (not overconstrained)."""
        return self._line_can_match(self.get_row(row), self.puzzle.row_clues[row])
    
    def check_col_valid(self, col: int) -> bool:
        """Check if column is still solvable."""
        return self._line_can_match(self.get_col(col), self.puzzle.col_clues[col])
    
    def _line_can_match(self, line: List[int], clue: List[int]) -> bool:
        """Check if a partially filled line can still match the clue."""
        # Use constraint propagation to check feasibility
        solver = LineSolver(len(line), clue)
        return solver.can_match(line)
    
    def apply_solution(self) -> None:
        """Apply the known solution to the grid (for testing)."""
        if self.puzzle.solution:
            for r in range(self.puzzle.height):
                for c in range(self.puzzle.width):
                    self.grid[r][c] = 1 if self.puzzle.solution[r][c] else -1


class LineSolver:
    """Solver for a single line (row or column)."""
    
    def __init__(self, length: int, clue: List[int]):
        self.length = length
        self.clue = clue
        self.num_blocks = len(clue)
        
    def solve(self, line: List[int]) -> Optional[List[int]]:
        """
        Apply constraint propagation to determine definite cells.
        Returns updated line with any cells that can be determined.
        """
        if not self.clue or self.clue == [0]:
            # No blocks - all cells must be empty
            return [-1] * self.length
        
        # Find all possible placements
        placements = list(self._generate_placements(line))
        
        if not placements:
            return None  # No valid placement - contradiction
        
        # Find cells that are the same in ALL placements
        result = line[:]
        for i in range(self.length):
            if result[i] != 0:
                continue  # Already determined
            
            all_filled = all(p[i] == 1 for p in placements)
            all_empty = all(p[i] == -1 for p in placements)
            
            if all_filled:
                result[i] = 1
            elif all_empty:
                result[i] = -1
        
        return result
    
    def can_match(self, line: List[int]) -> bool:
        """Check if any valid placement exists for the partial line."""
        for _ in self._generate_placements(line):
            return True  # At least one placement exists
        return False
    
    def _generate_placements(self, constraints: List[int]):
        """Generate all valid block placements given current constraints."""
        if not self.clue or self.clue == [0]:
            # No blocks - check all constraints allow empty
            if all(c != 1 for c in constraints):
                yield [-1] * self.length
            return
        
        # Recursive placement generator
        def place_blocks(pos: int, block_idx: int, current: List[int]):
            if block_idx >= self.num_blocks:
                # All blocks placed - fill rest with empty
                for i in range(pos, self.length):
                    if constraints[i] == 1:
                        return  # Constraint violation
                    current[i] = -1
                yield current[:]
                return
            
            block_len = self.clue[block_idx]
            remaining_blocks = self.clue[block_idx:]
            min_space_needed = sum(remaining_blocks) + len(remaining_blocks) - 1
            
            # Try each starting position for this block
            for start in range(pos, self.length - min_space_needed + 1):
                # Check if we can place block here
                valid = True
                
                # Cells before block must be empty
                for i in range(pos, start):
                    if constraints[i] == 1:
                        valid = False
                        break
                
                if not valid:
                    continue
                
                # Block cells must not be marked empty
                for i in range(start, start + block_len):
                    if constraints[i] == -1:
                        valid = False
                        break
                
                if not valid:
                    continue
                
                # Cell after block (if exists) must not be filled
                if start + block_len < self.length and constraints[start + block_len] == 1:
                    continue
                
                # Place this block
                placement = current[:]
                for i in range(pos, start):
                    placement[i] = -1
                for i in range(start, start + block_len):
                    placement[i] = 1
                if start + block_len < self.length:
                    placement[start + block_len] = -1
                
                # Recurse for next block
                yield from place_blocks(start + block_len + 1, block_idx + 1, placement)
        
        yield from place_blocks(0, 0, [0] * self.length)


class NonogramSolver:
    """Solver for complete Nonogram puzzles with auditable search pipeline."""

    @dataclass(frozen=True)
    class PropagationResult:
        changed: bool
        consistent: bool

        def __bool__(self) -> bool:
            return self.changed and self.consistent

    @dataclass(frozen=True)
    class ConstraintModel:
        row_solvers: List[LineSolver]
        col_solvers: List[LineSolver]

    class _SolveTimeout(Exception):
        pass

    def __init__(self, state: NonogramState):
        self.state = state
        self.puzzle = state.puzzle

    def _clone_state(self, state: NonogramState) -> NonogramState:
        return NonogramState(
            puzzle=state.puzzle,
            grid=[row[:] for row in state.grid],
        )

    def _cell_domain(self, state: NonogramState, row: int, col: int) -> List[int]:
        if state.grid[row][col] != 0:
            return [state.grid[row][col]]

        domain: List[int] = []
        for guess in (1, -1):
            state.grid[row][col] = guess
            row_ok = state.check_row_valid(row)
            col_ok = state.check_col_valid(col)
            state.grid[row][col] = 0
            if row_ok and col_ok:
                domain.append(guess)
        return domain

    def parse(self, state: Optional[NonogramState] = None) -> NonogramState:
        """Validate solver input and return a normalized state object."""
        parsed = state or self.state
        puzzle = parsed.puzzle

        if puzzle.width <= 0 or puzzle.height <= 0:
            raise ValueError("Puzzle dimensions must be positive.")
        if len(parsed.grid) != puzzle.height:
            raise ValueError("Grid height does not match puzzle height.")

        for row in parsed.grid:
            if len(row) != puzzle.width:
                raise ValueError("Grid width does not match puzzle width.")
            for value in row:
                if value not in (-1, 0, 1):
                    raise ValueError(f"Unsupported cell value: {value}")

        if len(puzzle.row_clues) != puzzle.height or len(puzzle.col_clues) != puzzle.width:
            raise ValueError("Clue dimensions do not match puzzle dimensions.")

        for clue in puzzle.row_clues + puzzle.col_clues:
            if clue == [0] or clue == []:
                continue
            if any((not isinstance(v, int)) or v <= 0 for v in clue):
                raise ValueError(f"Invalid clue values: {clue}")

        return parsed

    def encode_constraints(self, state: Optional[NonogramState] = None) -> "NonogramSolver.ConstraintModel":
        """Build reusable per-line solvers from puzzle clues."""
        parsed = self.parse(state)
        puzzle = parsed.puzzle

        row_solvers = [LineSolver(puzzle.width, clue) for clue in puzzle.row_clues]
        col_solvers = [LineSolver(puzzle.height, clue) for clue in puzzle.col_clues]

        assert len(row_solvers) == puzzle.height
        assert len(col_solvers) == puzzle.width

        return NonogramSolver.ConstraintModel(
            row_solvers=row_solvers,
            col_solvers=col_solvers,
        )

    def propagate(
        self,
        state: Optional[NonogramState] = None,
        constraints: Optional["NonogramSolver.ConstraintModel"] = None,
    ) -> "NonogramSolver.PropagationResult":
        """
        Apply one propagation round.

        Returns `PropagationResult(changed, consistent)` where:
        - `changed=True` means new cells were fixed
        - `consistent=False` means a contradiction was found
        """
        work_state = self.parse(state)
        model = constraints or self.encode_constraints(work_state)
        puzzle = work_state.puzzle
        changed = False

        for row in range(puzzle.height):
            line = work_state.get_row(row)
            result = model.row_solvers[row].solve(line)
            if result is None:
                return NonogramSolver.PropagationResult(changed=False, consistent=False)

            for col in range(puzzle.width):
                current = work_state.grid[row][col]
                proposed = result[col]
                if proposed == 0:
                    continue
                if current != 0 and current != proposed:
                    return NonogramSolver.PropagationResult(changed=False, consistent=False)
                if current == 0:
                    work_state.grid[row][col] = proposed
                    changed = True

            if not work_state.check_row_valid(row):
                return NonogramSolver.PropagationResult(changed=False, consistent=False)

        for col in range(puzzle.width):
            line = work_state.get_col(col)
            result = model.col_solvers[col].solve(line)
            if result is None:
                return NonogramSolver.PropagationResult(changed=False, consistent=False)

            for row in range(puzzle.height):
                current = work_state.grid[row][col]
                proposed = result[row]
                if proposed == 0:
                    continue
                if current != 0 and current != proposed:
                    return NonogramSolver.PropagationResult(changed=False, consistent=False)
                if current == 0:
                    work_state.grid[row][col] = proposed
                    changed = True

            if not work_state.check_col_valid(col):
                return NonogramSolver.PropagationResult(changed=False, consistent=False)

        return NonogramSolver.PropagationResult(changed=changed, consistent=True)

    def select_var(
        self,
        state: NonogramState,
        constraints: Optional["NonogramSolver.ConstraintModel"] = None,
    ) -> Optional[Tuple[int, int]]:
        """
        Pick the next unknown cell to branch on using smallest-domain heuristic.
        Returns `(row, col)` or `None` if no unknown cells remain.
        """
        self.parse(state)
        best_cell: Optional[Tuple[int, int]] = None
        best_domain_size = 3

        for row in range(state.puzzle.height):
            for col in range(state.puzzle.width):
                if state.grid[row][col] != 0:
                    continue
                domain = self._cell_domain(state, row, col)
                if not domain:
                    return (row, col)
                if len(domain) < best_domain_size:
                    best_cell = (row, col)
                    best_domain_size = len(domain)
                    if best_domain_size == 1:
                        return best_cell

        return best_cell

    def search(
        self,
        state: NonogramState,
        constraints: Optional["NonogramSolver.ConstraintModel"] = None,
        depth: int = 0,
        deadline: Optional[float] = None,
    ) -> Optional[NonogramState]:
        """Depth-first search with propagation and early contradiction detection."""
        if deadline is not None and time.perf_counter() >= deadline:
            raise NonogramSolver._SolveTimeout()

        work_state = self.parse(state)
        model = constraints or self.encode_constraints(work_state)
        max_depth = work_state.puzzle.width * work_state.puzzle.height + 1
        if depth > max_depth:
            return None

        while True:
            step = self.propagate(work_state, model)
            if not step.consistent:
                return None
            if not step.changed:
                break

        if self.validate_solution(work_state):
            return work_state

        choice = self.select_var(work_state, model)
        if choice is None:
            return None

        row, col = choice
        domain = self._cell_domain(work_state, row, col)
        if not domain:
            return None

        for guess in domain:
            if deadline is not None and time.perf_counter() >= deadline:
                raise NonogramSolver._SolveTimeout()
            candidate = self._clone_state(work_state)
            candidate.grid[row][col] = guess
            solved = self.search(candidate, model, depth + 1, deadline=deadline)
            if solved is not None:
                return solved

        return None

    def _count_solutions_limited(
        self,
        state: NonogramState,
        constraints: "NonogramSolver.ConstraintModel",
        limit: int = 2,
        deadline: Optional[float] = None,
    ) -> int:
        if deadline is not None and time.perf_counter() >= deadline:
            raise NonogramSolver._SolveTimeout()

        work_state = self._clone_state(state)
        while True:
            if deadline is not None and time.perf_counter() >= deadline:
                raise NonogramSolver._SolveTimeout()
            step = self.propagate(work_state, constraints)
            if not step.consistent:
                return 0
            if not step.changed:
                break

        if self.validate_solution(work_state):
            return 1

        choice = self.select_var(work_state, constraints)
        if choice is None:
            return 0

        row, col = choice
        domain = self._cell_domain(work_state, row, col)
        if not domain:
            return 0

        total = 0
        for guess in domain:
            if total >= limit:
                break
            candidate = self._clone_state(work_state)
            candidate.grid[row][col] = guess
            total += self._count_solutions_limited(candidate, constraints, limit - total, deadline=deadline)

        return total

    def validate_solution(self, state: NonogramState) -> bool:
        """Validate final state against clues with no unknown cells left."""
        self.parse(state)

        for row in state.grid:
            if any(cell == 0 for cell in row):
                return False

        for row in range(state.puzzle.height):
            if not state._line_matches_clue(state.get_row(row), state.puzzle.row_clues[row]):
                return False
        for col in range(state.puzzle.width):
            if not state._line_matches_clue(state.get_col(col), state.puzzle.col_clues[col]):
                return False

        return True

    def solve(self) -> Optional[NonogramState]:
        """Fully solve the puzzle using parse/propagate/search pipeline."""
        base_state = self.parse()
        model = self.encode_constraints(base_state)
        solved = self.search(self._clone_state(base_state), model, depth=0, deadline=None)
        if solved is None:
            return None

        self.state.grid = [row[:] for row in solved.grid]
        return self.state

    def solve_result(self, timeout: Optional[float] = None, detect_multiple: bool = True) -> SolverResult:
        """Normalized solver output for hub-level consumption."""
        start = time.perf_counter()
        deadline = None if timeout is None else (start + max(0.0, timeout))

        try:
            base_state = self.parse()
            model = self.encode_constraints(base_state)
            solved = self.search(self._clone_state(base_state), model, depth=0, deadline=deadline)
            elapsed_ms = int((time.perf_counter() - start) * 1000)

            if solved is None:
                return SolverResult(
                    status=SolveStatus.UNSOLVABLE,
                    solution=None,
                    solutions_found=0,
                    elapsed_ms=elapsed_ms,
                    message="No satisfying grid found.",
                )

            solutions_found: Optional[int] = None
            status = SolveStatus.SOLVED
            if detect_multiple:
                solutions_found = self._count_solutions_limited(base_state, model, limit=2, deadline=deadline)
                if solutions_found > 1:
                    status = SolveStatus.MULTIPLE_SOLUTIONS

            self.state.grid = [row[:] for row in solved.grid]
            return SolverResult(
                status=status,
                solution=self.state,
                solutions_found=solutions_found,
                elapsed_ms=elapsed_ms,
                message="Solved" if status == SolveStatus.SOLVED else "Multiple valid solutions found.",
            )
        except NonogramSolver._SolveTimeout:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return SolverResult(
                status=SolveStatus.TIMEOUT,
                solution=None,
                solutions_found=None,
                elapsed_ms=elapsed_ms,
                message="Solver timed out before completion.",
            )

    def get_hint(self) -> Optional[Tuple[int, int, int]]:
        """
        Get one hint as `(row, col, value)`.
        First tries one propagation round; if no progress, falls back to full search.
        """
        base_state = self.parse()
        state_copy = self._clone_state(base_state)
        model = self.encode_constraints(state_copy)
        step = self.propagate(state_copy, model)

        if not step.consistent:
            return None

        for row in range(base_state.puzzle.height):
            for col in range(base_state.puzzle.width):
                if base_state.grid[row][col] == 0 and state_copy.grid[row][col] != 0:
                    return (row, col, state_copy.grid[row][col])

        solved = self.search(self._clone_state(base_state), model, depth=0)
        if solved is None:
            return None

        for row in range(base_state.puzzle.height):
            for col in range(base_state.puzzle.width):
                if base_state.grid[row][col] == 0 and solved.grid[row][col] != 0:
                    return (row, col, solved.grid[row][col])

        return None

    def get_hint_result(self) -> Optional[Hint]:
        hint = self.get_hint()
        if hint is None:
            return None

        row, col, value = hint
        explanation = "Fill this cell." if value == 1 else "Mark this cell as empty."
        return Hint(
            type="cell_state",
            cells=((row, col),),
            explanation=explanation,
            confidence=0.75,
            payload={"value": value},
        )


# =============================================================================
# PUZZLE GENERATOR
# =============================================================================

def _extract_clues(grid: List[List[bool]]) -> Tuple[List[List[int]], List[List[int]]]:
    """Extract row and column clues from a solution grid."""
    height = len(grid)
    width = len(grid[0]) if grid else 0
    
    row_clues = []
    for row in grid:
        blocks = []
        current = 0
        for cell in row:
            if cell:
                current += 1
            else:
                if current > 0:
                    blocks.append(current)
                    current = 0
        if current > 0:
            blocks.append(current)
        row_clues.append(blocks if blocks else [0])
    
    col_clues = []
    for c in range(width):
        blocks = []
        current = 0
        for r in range(height):
            if grid[r][c]:
                current += 1
            else:
                if current > 0:
                    blocks.append(current)
                    current = 0
        if current > 0:
            blocks.append(current)
        col_clues.append(blocks if blocks else [0])
    
    return row_clues, col_clues


def _generate_shape_pattern(size: int) -> List[List[bool]]:
    """
    Generate a recognizable shape pattern.
    Uses geometric shapes, symmetry, and simple objects.
    """
    grid = [[False] * size for _ in range(size)]
    cx, cy = size // 2, size // 2
    
    # Choose a random shape type
    shape_type = random.choice([
        'heart', 'diamond', 'cross', 'arrow_up', 'arrow_down',
        'house', 'tree', 'star', 'circle', 'triangle',
        'cup', 'mushroom', 'boat', 'rocket', 'fish'
    ])
    
    def fill(r, c):
        if 0 <= r < size and 0 <= c < size:
            grid[r][c] = True
    
    def fill_rect(r1, c1, r2, c2):
        for r in range(max(0, r1), min(size, r2 + 1)):
            for c in range(max(0, c1), min(size, c2 + 1)):
                grid[r][c] = True
    
    def fill_circle(cr, cc, radius):
        for r in range(size):
            for c in range(size):
                if (r - cr) ** 2 + (c - cc) ** 2 <= radius ** 2:
                    grid[r][c] = True
    
    def fill_triangle_up(tip_r, tip_c, height):
        for h in range(height):
            r = tip_r + h
            width = h + 1
            for w in range(-width // 2, width // 2 + 1):
                fill(r, tip_c + w)
    
    def fill_triangle_down(tip_r, tip_c, height):
        for h in range(height):
            r = tip_r - h
            width = h + 1
            for w in range(-width // 2, width // 2 + 1):
                fill(r, tip_c + w)
    
    radius = size // 3
    
    if shape_type == 'heart':
        # Two circles on top, triangle below
        r = max(2, size // 4)
        fill_circle(r, cx - r // 2, r)
        fill_circle(r, cx + r // 2, r)
        fill_triangle_down(size - 2, cx, size // 2)
    
    elif shape_type == 'diamond':
        # Diamond shape
        for r in range(size):
            dist = abs(r - cy)
            width = max(0, radius - dist)
            for c in range(cx - width, cx + width + 1):
                fill(r, c)
    
    elif shape_type == 'cross':
        # Plus sign
        thickness = max(1, size // 5)
        fill_rect(0, cx - thickness // 2, size - 1, cx + thickness // 2)
        fill_rect(cy - thickness // 2, 0, cy + thickness // 2, size - 1)
    
    elif shape_type == 'arrow_up':
        # Upward arrow
        fill_triangle_up(1, cx, size // 2)
        fill_rect(size // 2, cx - size // 6, size - 2, cx + size // 6)
    
    elif shape_type == 'arrow_down':
        # Downward arrow
        fill_rect(1, cx - size // 6, size // 2, cx + size // 6)
        fill_triangle_down(size - 2, cx, size // 2)
    
    elif shape_type == 'house':
        # Roof (triangle) + body (rectangle)
        roof_h = size // 3
        fill_triangle_up(1, cx, roof_h)
        fill_rect(roof_h, size // 5, size - 2, size - size // 5 - 1)
        # Door
        door_w = size // 6
        fill_rect(size - size // 3, cx - door_w, size - 2, cx + door_w)
    
    elif shape_type == 'tree':
        # Triangle crown + trunk
        crown_h = size * 2 // 3
        fill_triangle_up(1, cx, crown_h)
        trunk_w = max(1, size // 6)
        fill_rect(crown_h, cx - trunk_w, size - 2, cx + trunk_w)
    
    elif shape_type == 'star':
        # Simple star pattern
        for r in range(size):
            for c in range(size):
                dr, dc = abs(r - cy), abs(c - cx)
                if dr + dc <= radius or (dr <= radius // 2 and dc <= radius // 2):
                    grid[r][c] = True
    
    elif shape_type == 'circle':
        fill_circle(cy, cx, radius)
    
    elif shape_type == 'triangle':
        fill_triangle_up(1, cx, size - 2)
    
    elif shape_type == 'cup':
        # Cup with handle
        fill_rect(2, size // 4, size - 3, size * 3 // 4)
        # Bottom
        fill_rect(size - 3, size // 3, size - 2, size * 2 // 3)
        # Handle
        for r in range(size // 3, size * 2 // 3):
            fill(r, size * 3 // 4 + 1)
    
    elif shape_type == 'mushroom':
        # Cap + stem
        cap_r = size // 3
        fill_circle(cap_r, cx, cap_r)
        stem_w = max(1, size // 5)
        fill_rect(cap_r, cx - stem_w, size - 2, cx + stem_w)
    
    elif shape_type == 'boat':
        # Hull + mast + sail
        hull_top = size * 2 // 3
        # Hull
        for r in range(hull_top, size - 1):
            width = size // 2 - (r - hull_top)
            for c in range(cx - width, cx + width + 1):
                fill(r, c)
        # Mast
        for r in range(2, hull_top):
            fill(r, cx)
        # Sail
        for h in range(hull_top - 3):
            fill(3 + h, cx + 1 + h // 2)
    
    elif shape_type == 'rocket':
        # Nose + body + fins
        fill_triangle_up(1, cx, size // 4)
        fill_rect(size // 4, cx - size // 5, size * 2 // 3, cx + size // 5)
        # Fins
        fin_start = size * 2 // 3
        for i in range(size // 5):
            fill(fin_start + i, cx - size // 4 - i)
            fill(fin_start + i, cx + size // 4 + i)
        # Fire
        fill_rect(size * 2 // 3, cx - size // 6, size - 2, cx + size // 6)
    
    elif shape_type == 'fish':
        # Body + tail
        fill_circle(cy, cx, radius)
        # Tail
        for r in range(cy - radius, cy + radius + 1):
            dist = abs(r - cy)
            for c in range(cx + radius, cx + radius + dist + 1):
                fill(r, c)
        # Eye
        if cy - radius // 2 >= 0 and cx - radius // 2 >= 0:
            grid[cy - radius // 3][cx - radius // 2] = False
    
    return grid


def generate_random_puzzle(width: int, height: int, fill_ratio: float = 0.5,
                           seed: Optional[int] = None) -> NonogramPuzzle:
    """
    Generate a random Nonogram puzzle with recognizable shape.
    
    Args:
        width: Grid width
        height: Grid height
        fill_ratio: Ignored (shapes determine fill)
        seed: Random seed for reproducibility
    
    Returns:
        NonogramPuzzle with a valid reference solution
        (uniqueness is not hard-guaranteed)
    """
    if seed is not None:
        random.seed(seed)
    
    # Generate shape-based solution
    size = max(width, height)
    solution = _generate_shape_pattern(size)
    
    # Crop or pad to exact dimensions
    if height > len(solution):
        solution = solution + [[False] * width for _ in range(height - len(solution))]
    elif height < len(solution):
        solution = solution[:height]
    
    for r in range(len(solution)):
        row = solution[r]
        if width > len(row):
            solution[r] = row + [False] * (width - len(row))
        elif width < len(row):
            solution[r] = row[:width]
    
    # Ensure at least some cells are filled
    filled = sum(sum(row) for row in solution)
    if filled < width * height * 0.1:
        # Fallback: add random structure
        for _ in range(width * height // 5):
            r, c = random.randint(0, height - 1), random.randint(0, width - 1)
            solution[r][c] = True
    
    row_clues, col_clues = _extract_clues(solution)
    
    puzzle = NonogramPuzzle(
        width=width,
        height=height,
        row_clues=row_clues,
        col_clues=col_clues,
        solution=solution,
    )
    
    return puzzle


def generate_pattern_puzzle(pattern: List[str], name: str = "") -> NonogramPuzzle:
    """
    Generate a puzzle from a pattern.
    
    Args:
        pattern: List of strings, '#' = filled, any other char = empty
        name: Optional puzzle name
    
    Returns:
        NonogramPuzzle
    """
    height = len(pattern)
    width = max(len(row) for row in pattern) if pattern else 0
    
    # Pad rows to equal width
    solution = []
    for row in pattern:
        padded = row.ljust(width)
        solution.append([c == '#' for c in padded])
    
    row_clues, col_clues = _extract_clues(solution)
    
    return NonogramPuzzle(
        width=width,
        height=height,
        row_clues=row_clues,
        col_clues=col_clues,
        solution=solution,
        name=name,
    )


# Predefined simple patterns for different sizes
SIMPLE_PATTERNS = {
    "heart_5x5": [
        ".#.#.",
        "#####",
        "#####",
        ".###.",
        "..#..",
    ],
    "smile_5x5": [
        ".###.",
        "#...#",
        "#.#.#",
        "#...#",
        ".###.",
    ],
    "arrow_5x5": [
        "..#..",
        ".###.",
        "#####",
        "..#..",
        "..#..",
    ],
    "star_7x7": [
        "...#...",
        "..###..",
        ".#####.",
        "#######",
        ".#####.",
        "..###..",
        "...#...",
    ],
    "house_7x7": [
        "...#...",
        "..###..",
        ".#####.",
        "#######",
        "#.###.#",
        "#.###.#",
        "#######",
    ],
    "cat_10x10": [
        "#........#",
        "##......##",
        "##########",
        "##.#..#.##",
        "##########",
        "##..##..##",
        "##......##",
        ".########.",
        "..######..",
        "...####...",
    ],
    "boat_10x10": [
        "....##....",
        "....##....",
        "....##....",
        "....##....",
        "#...##...#",
        "##..##..##",
        "###.##.###",
        "##########",
        ".########.",
        "..######..",
    ],
}


def get_preset_puzzle(name: str) -> Optional[NonogramPuzzle]:
    """Get a predefined puzzle by name (deprecated - always returns None)."""
    return None


def list_preset_puzzles() -> List[str]:
    """List available preset puzzle names (deprecated - returns empty)."""
    return []


def create_puzzle(size: int = 10, difficulty: str = "medium") -> Optional[NonogramState]:
    """
    Create a new puzzle for the game.
    
    Args:
        size: Grid size (width and height)
        difficulty: 'easy', 'medium', or 'hard'
    
    Returns:
        NonogramState ready to play
    """
    # Difficulty affects fill ratio - sparser is often easier
    fill_ratios = {
        "easy": 0.35,
        "medium": 0.45,
        "hard": 0.55,
    }
    fill = fill_ratios.get(difficulty, 0.45)
    
    puzzle = generate_random_puzzle(size, size, fill_ratio=fill)
    return NonogramState.from_puzzle(puzzle)
