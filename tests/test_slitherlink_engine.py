from __future__ import annotations

import unittest

from games.slitherlink.engine import (
    SlitherlinkPuzzle,
    SlitherlinkSolver,
    SlitherlinkState,
    count_solutions,
    solve_with_sat,
)
from hub.solver_contract import SolveStatus


def _sat_available() -> bool:
    try:
        from pysat.card import CardEnc  # noqa: F401
        from pysat.solvers import Solver  # noqa: F401
        return True
    except Exception:
        return False


class SlitherlinkEngineTests(unittest.TestCase):
    def test_single_loop_validation_accepts_square(self) -> None:
        puzzle = SlitherlinkPuzzle(width=1, height=1, clues=[[None]])
        state = SlitherlinkState.from_puzzle(puzzle)

        state.h_edges[0][0] = 1
        state.h_edges[1][0] = 1
        state.v_edges[0][0] = 1
        state.v_edges[0][1] = 1

        complete, message = state.is_complete()
        self.assertTrue(complete, message)

    def test_validation_rejects_multiple_loops(self) -> None:
        puzzle = SlitherlinkPuzzle(width=3, height=1, clues=[[None, None, None]])
        state = SlitherlinkState.from_puzzle(puzzle)

        # Left loop around cell (0,0).
        state.h_edges[0][0] = 1
        state.h_edges[1][0] = 1
        state.v_edges[0][0] = 1
        state.v_edges[0][1] = 1

        # Right loop around cell (0,2).
        state.h_edges[0][2] = 1
        state.h_edges[1][2] = 1
        state.v_edges[0][2] = 1
        state.v_edges[0][3] = 1

        complete, _ = state.is_complete()
        self.assertFalse(complete)

    @unittest.skipUnless(_sat_available(), "python-sat dependency is missing")
    def test_sat_solver_finds_solution_for_simple_case(self) -> None:
        puzzle = SlitherlinkPuzzle(width=2, height=2, clues=[[2, 2], [2, 2]])
        solved = solve_with_sat(SlitherlinkState.from_puzzle(puzzle))

        self.assertIsNotNone(solved)
        complete, message = solved.is_complete()  # type: ignore[union-attr]
        self.assertTrue(complete, message)

    @unittest.skipUnless(_sat_available(), "python-sat dependency is missing")
    def test_solution_counter_reports_solution_for_simple_case(self) -> None:
        puzzle = SlitherlinkPuzzle(width=2, height=2, clues=[[2, 2], [2, 2]])
        count = count_solutions(puzzle, limit=2)
        self.assertGreaterEqual(count, 1)
        self.assertLessEqual(count, 2)

    @unittest.skipUnless(_sat_available(), "python-sat dependency is missing")
    def test_normalized_solver_result(self) -> None:
        puzzle = SlitherlinkPuzzle(width=2, height=2, clues=[[2, 2], [2, 2]])
        state = SlitherlinkState.from_puzzle(puzzle)
        result = SlitherlinkSolver(state).solve_result(timeout=5.0, detect_multiple=True)

        self.assertIn(result.status, {SolveStatus.SOLVED, SolveStatus.MULTIPLE_SOLUTIONS})
        self.assertIsNotNone(result.solution)


if __name__ == "__main__":
    unittest.main()

