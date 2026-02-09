from __future__ import annotations

import unittest

import numpy as np

from games.game2048.engine import Direction as EngineDirection
from games.game2048.engine import Game2048
from games.game2048.solver import (
    GRADIENT_WEIGHTS,
    build_weight_vector,
    evaluate_grid_numba,
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

    def test_monotonicity_ignores_zero_gaps(self) -> None:
        only_mono = build_weight_vector(
            {
                "gradient": 0.0,
                "corner_bonus": 0.0,
                "corner_distance_penalty": 0.0,
                "empty_cells": 0.0,
                "monotonicity": 1.0,
                "smoothness": 0.0,
                "merge": 0.0,
                "near_2048": 0.0,
                "left_bias": 0.0,
                "up_bias": 0.0,
                "right_penalty": 0.0,
                "down_penalty": 0.0,
                "corner_break_penalty": 0.0,
                "move_score_scale": 0.0,
                "terminal_penalty": 1.0,
            }
        )

        # Both boards have same non-zero order in first row: 8 > 4 > 2.
        board_a = np.array(
            [
                [8, 4, 2, 0],
                [0, 0, 0, 0],
                [0, 0, 0, 0],
                [0, 0, 0, 0],
            ],
            dtype=np.int64,
        )
        board_b = np.array(
            [
                [8, 0, 4, 2],
                [0, 0, 0, 0],
                [0, 0, 0, 0],
                [0, 0, 0, 0],
            ],
            dtype=np.int64,
        )

        score_a = float(evaluate_grid_numba(board_a, GRADIENT_WEIGHTS, only_mono))
        score_b = float(evaluate_grid_numba(board_b, GRADIENT_WEIGHTS, only_mono))
        self.assertAlmostEqual(score_a, score_b, places=6)

    def test_gradient_weights_are_applied_in_evaluation(self) -> None:
        only_gradient = build_weight_vector(
            {
                "gradient": 1.0,
                "corner_bonus": 0.0,
                "corner_distance_penalty": 0.0,
                "empty_cells": 0.0,
                "monotonicity": 0.0,
                "smoothness": 0.0,
                "merge": 0.0,
                "near_2048": 0.0,
                "left_bias": 0.0,
                "up_bias": 0.0,
                "right_penalty": 0.0,
                "down_penalty": 0.0,
                "corner_break_penalty": 0.0,
                "move_score_scale": 0.0,
                "terminal_penalty": 1.0,
            }
        )
        board = np.array(
            [
                [512, 0, 0, 2],
                [0, 0, 0, 0],
                [0, 0, 0, 0],
                [4, 0, 0, 16],
            ],
            dtype=np.int64,
        )
        reversed_gradient = np.flip(GRADIENT_WEIGHTS)

        score_default = float(evaluate_grid_numba(board, GRADIENT_WEIGHTS, only_gradient))
        score_reversed = float(evaluate_grid_numba(board, reversed_gradient, only_gradient))
        self.assertNotAlmostEqual(score_default, score_reversed, places=6)

    def test_chance_sampling_is_deterministic_for_same_board(self) -> None:
        grid = [
            [2, 4, 8, 16],
            [32, 64, 128, 0],
            [0, 2, 4, 8],
            [16, 32, 64, 128],
        ]

        m1 = get_best_move(grid, depth=3, chance_branch_limit=6)
        m2 = get_best_move(grid, depth=3, chance_branch_limit=6)
        self.assertEqual(m1, m2)


if __name__ == "__main__":
    unittest.main()
