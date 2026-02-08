from __future__ import annotations

import unittest

from games.game2048.engine import Direction as EngineDirection
from games.game2048.engine import Game2048
from games.game2048.solver import get_best_move


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


if __name__ == "__main__":
    unittest.main()
