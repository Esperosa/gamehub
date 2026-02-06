"""
Nonogram (Picross/Griddlers) Game Engine

A logic puzzle where you fill in cells based on numeric clues for each row/column.
The clues indicate the lengths of consecutive filled cell blocks in that line.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Set
from pathlib import Path


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
    """Solver for complete Nonogram puzzles using constraint propagation."""
    
    def __init__(self, state: NonogramState):
        self.state = state
        self.puzzle = state.puzzle
    
    def propagate(self) -> bool:
        """
        Apply constraint propagation to determine definite cells.
        Returns True if any progress was made.
        """
        changed = False
        
        # Process all rows
        for row in range(self.puzzle.height):
            line = self.state.get_row(row)
            solver = LineSolver(self.puzzle.width, self.puzzle.row_clues[row])
            result = solver.solve(line)
            
            if result is None:
                return False  # Contradiction
            
            for col in range(self.puzzle.width):
                if result[col] != 0 and self.state.grid[row][col] == 0:
                    self.state.grid[row][col] = result[col]
                    changed = True
        
        # Process all columns
        for col in range(self.puzzle.width):
            line = self.state.get_col(col)
            solver = LineSolver(self.puzzle.height, self.puzzle.col_clues[col])
            result = solver.solve(line)
            
            if result is None:
                return False  # Contradiction
            
            for row in range(self.puzzle.height):
                if result[row] != 0 and self.state.grid[row][col] == 0:
                    self.state.grid[row][col] = result[row]
                    changed = True
        
        return changed
    
    def solve(self) -> Optional[NonogramState]:
        """
        Fully solve the puzzle using constraint propagation.
        Returns solved state or None if unsolvable.
        """
        import copy
        
        # Apply propagation until no more progress
        while True:
            progress = self.propagate()
            if not progress:
                break
        
        # Check if solved
        if all(self.state.grid[r][c] != 0 
               for r in range(self.puzzle.height) 
               for c in range(self.puzzle.width)):
            return self.state
        
        # Need to guess - find first unknown cell
        for row in range(self.puzzle.height):
            for col in range(self.puzzle.width):
                if self.state.grid[row][col] == 0:
                    # Try filled first
                    for guess in [1, -1]:
                        state_copy = NonogramState(
                            puzzle=self.puzzle,
                            grid=[r[:] for r in self.state.grid]
                        )
                        state_copy.grid[row][col] = guess
                        
                        solver = NonogramSolver(state_copy)
                        result = solver.solve()
                        if result is not None:
                            return result
                    
                    return None  # Both guesses failed
        
        return self.state
    
    def get_hint(self) -> Optional[Tuple[int, int, int]]:
        """
        Get a hint: returns (row, col, value) for a cell that can be determined.
        Returns None if no hint available.
        """
        # Apply one round of propagation on a copy
        import copy
        state_copy = NonogramState(
            puzzle=self.puzzle,
            grid=[r[:] for r in self.state.grid]
        )
        
        solver = NonogramSolver(state_copy)
        solver.propagate()
        
        # Find first cell that was determined
        for row in range(self.puzzle.height):
            for col in range(self.puzzle.width):
                if self.state.grid[row][col] == 0 and state_copy.grid[row][col] != 0:
                    return (row, col, state_copy.grid[row][col])
        
        return None


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
        NonogramPuzzle with unique solution
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
