from __future__ import annotations

import unittest

from games.kenken.engine import Cage, KenKenConfig, KenKenSolver, create_puzzle
from hub.solver_contract import SolveStatus


class KenKenEngineTests(unittest.TestCase):
    def test_generated_cages_match_embedded_solution(self) -> None:
        state = create_puzzle(size=4, seed=21)
        n = state.size

        self.assertGreater(len(state.cages), 0)
        for cage in state.cages:
            values = [state.solution[row * n + col] for row, col in cage.cells]
            self.assertTrue(
                cage.check(values),
                msg=f"cage {cage.operation}{cage.target} does not match generated solution",
            )

    def test_solver_finds_valid_solution_for_generated_puzzle(self) -> None:
        state = create_puzzle(size=4, seed=19)
        solver = KenKenSolver(state.config, state.cages)

        solved = solver.solve(state.board)
        self.assertIsNotNone(solved)
        self.assertTrue(solver.validate_solution(solved))

    def test_forced_single_cell_cages_have_unique_solution(self) -> None:
        n = 3
        config = KenKenConfig.from_size(n)
        solution = [
            1, 2, 3,
            2, 3, 1,
            3, 1, 2,
        ]
        cages = [
            Cage(cells=[(row, col)], target=solution[row * n + col], operation="")
            for row in range(n)
            for col in range(n)
        ]
        solver = KenKenSolver(config, cages)

        solved = solver.solve([0] * (n * n))
        self.assertEqual(solved, solution)
        self.assertEqual(solver.count_solutions([0] * (n * n), limit=2, timeout=1.0), 1)

    def test_normalized_solver_result(self) -> None:
        n = 3
        config = KenKenConfig.from_size(n)
        solution = [
            1, 2, 3,
            2, 3, 1,
            3, 1, 2,
        ]
        cages = [
            Cage(cells=[(row, col)], target=solution[row * n + col], operation="")
            for row in range(n)
            for col in range(n)
        ]
        solver = KenKenSolver(config, cages)

        result = solver.solve_result([0] * (n * n), timeout=2.0, detect_multiple=True)
        self.assertEqual(result.status, SolveStatus.SOLVED)
        self.assertEqual(result.solutions_found, 1)
        self.assertEqual(result.solution, solution)


if __name__ == "__main__":
    unittest.main()

