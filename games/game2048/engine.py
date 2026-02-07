"""
2048 Game Engine

The classic sliding tile puzzle game where you combine tiles to reach 2048.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple


class Direction(Enum):
    """Movement directions."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


@dataclass
class Game2048:
    """Represents a 2048 game state."""

    size: int = 4
    grid: List[List[int]] = field(default_factory=list)
    score: int = 0
    best_tile: int = 0
    moves: int = 0
    game_over: bool = False
    won: bool = False

    def __post_init__(self):
        if not self.grid:
            self.grid = [[0] * self.size for _ in range(self.size)]

    @classmethod
    def new_game(cls, size: int = 4) -> "Game2048":
        """Create a new game with initial tiles."""
        game = cls(size=size)
        # Spawn 2 initial tiles
        game._spawn_tile()
        game._spawn_tile()
        return game

    def _empty_cells(self) -> List[Tuple[int, int]]:
        """Get list of empty cell coordinates."""
        return [(r, c) for r in range(self.size) for c in range(self.size) if self.grid[r][c] == 0]

    def _spawn_tile(self) -> bool:
        """Spawn a new tile (90% chance of 2, 10% chance of 4)."""
        empty = self._empty_cells()
        if not empty:
            return False

        r, c = random.choice(empty)
        self.grid[r][c] = 2 if random.random() < 0.9 else 4
        return True

    def _slide_row_left(self, row: List[int]) -> Tuple[List[int], int]:
        """
        Slide a row to the left, merging tiles.
        Returns (new_row, score_gained).
        """
        # Remove zeros
        tiles = [t for t in row if t != 0]

        # Merge adjacent equal tiles
        merged = []
        score = 0
        i = 0
        while i < len(tiles):
            if i + 1 < len(tiles) and tiles[i] == tiles[i + 1]:
                # Merge
                new_val = tiles[i] * 2
                merged.append(new_val)
                score += new_val
                i += 2
            else:
                merged.append(tiles[i])
                i += 1

        # Pad with zeros
        while len(merged) < len(row):
            merged.append(0)

        return merged, score

    def _rotate_90_cw(self, grid: List[List[int]]) -> List[List[int]]:
        """Rotate grid 90 degrees clockwise."""
        n = len(grid)
        return [[grid[n - 1 - j][i] for j in range(n)] for i in range(n)]

    def _rotate_90_ccw(self, grid: List[List[int]]) -> List[List[int]]:
        """Rotate grid 90 degrees counter-clockwise."""
        n = len(grid)
        return [[grid[j][n - 1 - i] for j in range(n)] for i in range(n)]

    def move(self, direction: Direction) -> bool:
        """
        Make a move in the given direction.
        Returns True if the move was valid (something moved).
        """
        if self.game_over:
            return False

        old_grid = copy.deepcopy(self.grid)
        score_gained = 0

        # Rotate grid so we can always slide left
        if direction == Direction.LEFT:
            rotations = 0
        elif direction == Direction.DOWN:
            rotations = 1
        elif direction == Direction.RIGHT:
            rotations = 2
        elif direction == Direction.UP:
            rotations = 3
        else:
            return False

        # Rotate to align with left slide
        grid = self.grid
        for _ in range(rotations):
            grid = self._rotate_90_cw(grid)

        # Slide all rows left
        new_grid = []
        for row in grid:
            new_row, score = self._slide_row_left(row)
            new_grid.append(new_row)
            score_gained += score

        # Rotate back
        for _ in range(rotations):
            new_grid = self._rotate_90_ccw(new_grid)

        # Check if anything moved
        if new_grid == old_grid:
            # Even if nothing moved, check if game should be over
            if not self._has_valid_moves():
                self.game_over = True
            return False

        # Apply changes
        self.grid = new_grid
        self.score += score_gained
        self.moves += 1

        # Update best tile
        max_tile = max(max(row) for row in self.grid)
        if max_tile > self.best_tile:
            self.best_tile = max_tile

        # Check for win (first time reaching 2048)
        if self.best_tile >= 2048 and not self.won:
            self.won = True

        # Spawn new tile
        self._spawn_tile()

        # Check for game over
        if not self._has_valid_moves():
            self.game_over = True

        return True

    def _has_valid_moves(self) -> bool:
        """Check if any valid moves remain."""
        # Check for empty cells
        if self._empty_cells():
            return True

        # Check for possible merges
        for r in range(self.size):
            for c in range(self.size):
                val = self.grid[r][c]
                # Check right
                if c + 1 < self.size and self.grid[r][c + 1] == val:
                    return True
                # Check down
                if r + 1 < self.size and self.grid[r + 1][c] == val:
                    return True

        return False

    def get_cell(self, row: int, col: int) -> int:
        """Get cell value."""
        return self.grid[row][col]

    def can_continue(self) -> bool:
        """Check if game can continue after winning."""
        return self.won and not self.game_over


def create_game(size: int = 4) -> Game2048:
    """Create a new 2048 game."""
    return Game2048.new_game(size)


# Tile colors for UI (value -> (background, text))
TILE_COLORS = {
    0: ("#CDC1B4", "#CDC1B4"),
    2: ("#EEE4DA", "#776E65"),
    4: ("#EDE0C8", "#776E65"),
    8: ("#F2B179", "#F9F6F2"),
    16: ("#F59563", "#F9F6F2"),
    32: ("#F67C5F", "#F9F6F2"),
    64: ("#F65E3B", "#F9F6F2"),
    128: ("#EDCF72", "#F9F6F2"),
    256: ("#EDCC61", "#F9F6F2"),
    512: ("#EDC850", "#F9F6F2"),
    1024: ("#EDC53F", "#F9F6F2"),
    2048: ("#EDC22E", "#F9F6F2"),
    4096: ("#3C3A32", "#F9F6F2"),
    8192: ("#3C3A32", "#F9F6F2"),
}


def get_tile_colors(value: int) -> Tuple[str, str]:
    """Get (background_color, text_color) for a tile value."""
    if value in TILE_COLORS:
        return TILE_COLORS[value]
    # For values > 8192, use dark background
    return ("#3C3A32", "#F9F6F2")
