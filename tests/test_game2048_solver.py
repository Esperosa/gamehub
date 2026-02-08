from __future__ import annotations

import unittest

import numpy as np

from games.game2048.engine import Direction as EngineDirection
from games.game2048.engine import Game2048
from games.game2048.solver import get_best_move, near_2048_potential_numba


class Game2048SolverTests(unittest.TestCase):
    def _apply_move(self, grid: list[list[int]], direction_value: str) -> Game2048:
        game = Game2048(size=4, grid=[row[:] for row in grid], best_tile=max(max(row) for row in grid))
        moved = game.move(EngineDirection(direction_value))
        self.assertTrue(moved, "Solver returned an invalid/non-moving direction.")
        return game

    def test_solver_takes_immediate_2048_when_available(self) -> None:
        grid = [
            [1024, 1024, 2, 4],
            [8, 16, 32, 64],
            [2, 4, 8, 16],
            [0, 0, 0, 0],
        ]

        move = get_best_move(grid, depth=4)
        self.assertIsNotNone(move)
        assert move is not None

        game_after = self._apply_move(grid, move.value)
        self.assertGreaterEqual(game_after.best_tile, 2048)

    def test_solver_returns_legal_move_on_regular_position(self) -> None:
        grid = [
            [2, 4, 8, 16],
            [32, 64, 128, 0],
            [0, 2, 4, 8],
            [16, 32, 64, 128],
        ]

        move = get_best_move(grid, depth=3)
        self.assertIsNotNone(move)
        assert move is not None
        self._apply_move(grid, move.value)

    def test_near_2048_potential_prefers_adjacent_1024_pair(self) -> None:
        adjacent = np.array(
            [
                [1024, 1024, 0, 0],
                [256, 128, 64, 32],
                [2, 4, 8, 16],
                [0, 0, 0, 0],
            ],
            dtype=np.int64,
        )
        separated = np.array(
            [
                [1024, 0, 0, 0],
                [256, 128, 64, 32],
                [2, 4, 8, 16],
                [0, 0, 0, 1024],
            ],
            dtype=np.int64,
        )

        self.assertGreater(
            near_2048_potential_numba(adjacent),
            near_2048_potential_numba(separated),
        )

    def test_near_2048_potential_is_lower_on_cramped_board(self) -> None:
        open_board = np.array(
            [
                [1024, 1024, 0, 0],
                [0, 0, 0, 0],
                [0, 0, 0, 0],
                [2, 4, 8, 16],
            ],
            dtype=np.int64,
        )
        cramped_board = np.array(
            [
                [1024, 1024, 2, 4],
                [8, 16, 32, 64],
                [128, 256, 512, 2],
                [4, 8, 16, 32],
            ],
            dtype=np.int64,
        )

        self.assertGreater(
            near_2048_potential_numba(open_board),
            near_2048_potential_numba(cramped_board),
        )


if __name__ == "__main__":
    unittest.main()
