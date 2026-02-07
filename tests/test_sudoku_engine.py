from __future__ import annotations

import unittest

from games.sudoku.engine import SudokuConfig, SudokuSolver, create_puzzle
from hub.solver_contract import SolveStatus


KNOWN_PUZZLE = [
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

KNOWN_SOLUTION = [
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


class SudokuEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = SudokuConfig.from_size(9)
        self.solver = SudokuSolver(self.config)

    def _assert_valid_solution_grid(self, board: list[int]) -> None:
        self.assertEqual(len(board), 81)
        expected = set(range(1, 10))

        for row in range(9):
            values = board[row * 9:(row + 1) * 9]
            self.assertEqual(set(values), expected, f"row {row} is invalid")

        for col in range(9):
            values = [board[row * 9 + col] for row in range(9)]
            self.assertEqual(set(values), expected, f"column {col} is invalid")

        for box_row in range(0, 9, 3):
            for box_col in range(0, 9, 3):
                values: list[int] = []
                for row in range(box_row, box_row + 3):
                    for col in range(box_col, box_col + 3):
                        values.append(board[row * 9 + col])
                self.assertEqual(set(values), expected, f"box ({box_row},{box_col}) is invalid")

    def test_solver_solves_known_instance(self) -> None:
        solved = self.solver.solve(KNOWN_PUZZLE)
        self.assertIsNotNone(solved)
        self.assertEqual(solved, KNOWN_SOLUTION)

    def test_generator_returns_consistent_unique_puzzle(self) -> None:
        state = create_puzzle(size=9, difficulty="easy", seed=123)

        self.assertEqual(state.size, 9)
        self.assertEqual(len(state.board), 81)
        self.assertEqual(len(state.solution), 81)
        self.assertEqual(len(state.initial), 81)

        given_count = 0
        for idx, is_given in enumerate(state.initial):
            if is_given:
                given_count += 1
                self.assertNotEqual(state.board[idx], 0)
                self.assertEqual(state.board[idx], state.solution[idx])
            else:
                self.assertEqual(state.board[idx], 0)

        self.assertGreater(given_count, 20)
        self._assert_valid_solution_grid(state.solution)
        self.assertEqual(self.solver.count_solutions(state.board, limit=2), 1)

    def test_normalized_solver_result_for_known_instance(self) -> None:
        result = self.solver.solve_result(KNOWN_PUZZLE, timeout=5.0, detect_multiple=True)
        self.assertEqual(result.status, SolveStatus.SOLVED)
        self.assertEqual(result.solutions_found, 1)
        self.assertEqual(result.solution, KNOWN_SOLUTION)


if __name__ == "__main__":
    unittest.main()

