from __future__ import annotations

import unittest

import numpy as np

from games.game2048.engine import Direction as EngineDirection
from games.game2048.engine import Game2048
from games.game2048.solver import (
    build_weight_vector,
    get_best_move,
    get_default_weights,
    near_2048_potential_numba,
)


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

    def test_weight_vector_overrides_known_key(self) -> None:
        defaults = get_default_weights()
        vector = build_weight_vector({"empty_cells": defaults["empty_cells"] * 1.5})
        default_vector = build_weight_vector()
        self.assertNotEqual(float(vector[3]), float(default_vector[3]))

    def test_weight_vector_rejects_unknown_key(self) -> None:
        with self.assertRaises(KeyError):
            build_weight_vector({"does_not_exist": 1.0})

    def test_get_best_move_accepts_weight_overrides(self) -> None:
        grid = [
            [2, 2, 4, 8],
            [16, 32, 64, 128],
            [256, 0, 0, 2],
            [4, 8, 16, 32],
        ]
        move = get_best_move(
            grid,
            depth=2,
            weights={"left_bias": 200.0, "right_penalty": 20.0},
            chance_branch_limit=6,
        )
        self.assertIsNotNone(move)
        assert move is not None
        self._apply_move(grid, move.value)


if __name__ == "__main__":
    unittest.main()
