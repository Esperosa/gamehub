from __future__ import annotations

import unittest

from games.sudoku.engine import SudokuConfig, SudokuSolver, SudokuState, create_puzzle
from hub.solver_contract import SolveStatus


KNOWN_PUZZLE_9X9 = [
    5, 3, 0, 0, 7, 0, 0, 0, 0,
    6, 0, 0, 1, 9, 5, 0, 0, 0,
    0, 9, 8, 0, 0, 0, 0, 6, 0,
    8, 0, 0, 0, 6, 0, 0, 0, 3,
    4, 0, 0, 8, 0, 3, 0, 0, 1,
    7, 0, 0, 0, 2, 0, 0, 0, 6,
    0, 6, 0, 0, 0, 0, 2, 8, 0,
    0, 0, 0, 4, 1, 9, 0, 0, 5,
    0, 0, 0, 0, 8, 0, 0, 7, 9,
]

KNOWN_SOLUTION_9X9 = [
    5, 3, 4, 6, 7, 8, 9, 1, 2,
    6, 7, 2, 1, 9, 5, 3, 4, 8,
    1, 9, 8, 3, 4, 2, 5, 6, 7,
    8, 5, 9, 7, 6, 1, 4, 2, 3,
    4, 2, 6, 8, 5, 3, 7, 9, 1,
    7, 1, 3, 9, 2, 4, 8, 5, 6,
    9, 6, 1, 5, 3, 7, 2, 8, 4,
    2, 8, 7, 4, 1, 9, 6, 3, 5,
    3, 4, 5, 2, 8, 6, 1, 7, 9,
]

KNOWN_PUZZLE_4X4 = [
    1, 0, 0, 4,
    0, 4, 1, 0,
    2, 1, 0, 0,
    0, 0, 2, 1,
]

KNOWN_SOLUTION_4X4 = [
    1, 2, 3, 4,
    3, 4, 1, 2,
    2, 1, 4, 3,
    4, 3, 2, 1,
]


class SudokuEngineTests(unittest.TestCase):
    def _assert_valid_solution_grid(self, board: list[int], config: SudokuConfig) -> None:
        size = config.size
        expected = set(range(1, size + 1))

        self.assertEqual(len(board), size * size)

        for row in range(size):
            values = board[row * size : (row + 1) * size]
            self.assertEqual(set(values), expected, f"row {row} is invalid for {size}x{size}")

        for col in range(size):
            values = [board[row * size + col] for row in range(size)]
            self.assertEqual(set(values), expected, f"column {col} is invalid for {size}x{size}")

        for box_row in range(0, size, config.box_rows):
            for box_col in range(0, size, config.box_cols):
                values: list[int] = []
                for row in range(box_row, box_row + config.box_rows):
                    for col in range(box_col, box_col + config.box_cols):
                        values.append(board[row * size + col])
                self.assertEqual(
                    set(values),
                    expected,
                    f"box ({box_row},{box_col}) is invalid for {size}x{size}",
                )

    def test_config_maps_standard_sudoku_variants(self) -> None:
        expected_map = {
            4: (2, 2),
            6: (2, 3),
            9: (3, 3),
            16: (4, 4),
        }
        for size, (box_rows, box_cols) in expected_map.items():
            cfg = SudokuConfig.from_size(size)
            self.assertEqual(cfg.box_rows, box_rows)
            self.assertEqual(cfg.box_cols, box_cols)
            self.assertEqual(cfg.num_range, size)

    def test_config_rejects_unsupported_size(self) -> None:
        with self.assertRaises(ValueError):
            SudokuConfig.from_size(3)

    def test_solver_solves_known_9x9_instance(self) -> None:
        solver = SudokuSolver(SudokuConfig.from_size(9))
        solved = solver.solve(KNOWN_PUZZLE_9X9)
        self.assertIsNotNone(solved)
        self.assertEqual(solved, KNOWN_SOLUTION_9X9)

    def test_solver_solves_known_4x4_instance(self) -> None:
        solver = SudokuSolver(SudokuConfig.from_size(4))
        solved = solver.solve(KNOWN_PUZZLE_4X4)
        self.assertIsNotNone(solved)
        self.assertEqual(solved, KNOWN_SOLUTION_4X4)

    def test_generator_returns_consistent_unique_puzzle_for_supported_sizes(self) -> None:
        for size in (4, 6, 9, 16):
            with self.subTest(size=size):
                state = create_puzzle(size=size, difficulty="easy", seed=100 + size)
                solver = SudokuSolver(SudokuConfig.from_size(size))
                total = size * size

                self.assertEqual(state.size, size)
                self.assertEqual(len(state.board), total)
                self.assertEqual(len(state.solution), total)
                self.assertEqual(len(state.initial), total)

                given_count = 0
                for idx, is_given in enumerate(state.initial):
                    if is_given:
                        given_count += 1
                        self.assertNotEqual(state.board[idx], 0)
                        self.assertEqual(state.board[idx], state.solution[idx])
                    else:
                        self.assertEqual(state.board[idx], 0)

                self.assertGreater(given_count, size)
                self._assert_valid_solution_grid(state.solution, state.config)
                self.assertEqual(solver.count_solutions(state.board, limit=2), 1)

    def test_normalized_solver_result_for_known_instance(self) -> None:
        solver = SudokuSolver(SudokuConfig.from_size(9))
        result = solver.solve_result(KNOWN_PUZZLE_9X9, timeout=5.0, detect_multiple=True)
        self.assertEqual(result.status, SolveStatus.SOLVED)
        self.assertEqual(result.solutions_found, 1)
        self.assertEqual(result.solution, KNOWN_SOLUTION_9X9)

    def test_solver_enumerates_multiple_solutions_for_ambiguous_board(self) -> None:
        config = SudokuConfig.from_size(4)
        solver = SudokuSolver(config)
        empty_board = [0] * (config.size * config.size)

        limited = solver.enumerate_solutions(empty_board, limit=3)
        self.assertEqual(len(limited), 3)

        all_solutions = solver.enumerate_solutions(empty_board, limit=None)
        self.assertGreater(len(all_solutions), 3)
        self.assertEqual(len(all_solutions), len({tuple(solution) for solution in all_solutions}))
        for solution in all_solutions[:10]:
            self._assert_valid_solution_grid(solution, config)

    def test_state_completion_accepts_any_valid_solution_not_only_embedded_one(self) -> None:
        config = SudokuConfig.from_size(4)
        solver = SudokuSolver(config)
        ambiguous_board = [0] * (config.size * config.size)
        solutions = solver.enumerate_solutions(ambiguous_board, limit=2)
        self.assertEqual(len(solutions), 2)

        embedded_solution, alternate_solution = solutions
        self.assertNotEqual(embedded_solution, alternate_solution)

        state = SudokuState(
            config=config,
            board=alternate_solution.copy(),
            initial=[False] * (config.size * config.size),
            solution=embedded_solution,
            seed=123,
        )
        self.assertTrue(state.is_complete())

        differing_index = next(
            idx for idx, (embedded, alt) in enumerate(zip(embedded_solution, alternate_solution)) if embedded != alt
        )
        givens = [False] * (config.size * config.size)
        givens[differing_index] = True
        state_with_conflicting_given = SudokuState(
            config=config,
            board=alternate_solution.copy(),
            initial=givens,
            solution=embedded_solution,
            seed=124,
        )
        self.assertFalse(state_with_conflicting_given.is_complete())


if __name__ == "__main__":
    unittest.main()
