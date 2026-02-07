from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from games.kenken.engine import KenKenSolver
from games.kenken.engine import create_puzzle as create_kenken_puzzle
from games.slitherlink.engine import create_puzzle as create_slitherlink_puzzle
from games.sudoku.engine import SudokuConfig, SudokuSolver
from games.sudoku.engine import create_puzzle as create_sudoku_puzzle


@settings(max_examples=8, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    seed=st.integers(min_value=0, max_value=100_000),
    difficulty=st.sampled_from(["easy", "medium"]),
)
def test_sudoku_generator_returns_consistent_unique_puzzle(seed: int, difficulty: str) -> None:
    state = create_sudoku_puzzle(size=9, difficulty=difficulty, seed=seed)
    solver = SudokuSolver(SudokuConfig.from_size(9))

    assert len(state.board) == 81
    assert len(state.initial) == 81
    assert len(state.solution) == 81

    for idx, is_given in enumerate(state.initial):
        if is_given:
            assert state.board[idx] != 0
            assert state.board[idx] == state.solution[idx]
        else:
            assert state.board[idx] == 0

    assert solver.count_solutions(state.board, limit=2) == 1


@settings(max_examples=8, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    seed=st.integers(min_value=0, max_value=100_000),
    size=st.sampled_from([3, 4]),
)
def test_kenken_generator_returns_consistent_puzzle(seed: int, size: int) -> None:
    state = create_kenken_puzzle(size=size, seed=seed)
    solver = KenKenSolver(state.config, state.cages)
    n = state.size

    assert len(state.board) == n * n
    assert len(state.solution) == n * n
    assert all(value == 0 for value in state.board)

    for cage in state.cages:
        values = [state.solution[row * n + col] for row, col in cage.cells]
        assert cage.check(values)

    assert solver.validate_solution(state.solution)


@settings(max_examples=8, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    seed=st.integers(min_value=0, max_value=100_000),
    difficulty=st.sampled_from(["easy", "medium", "hard"]),
)
def test_slitherlink_generator_embedded_solution_matches_clues(seed: int, difficulty: str) -> None:
    state = create_slitherlink_puzzle(size=6, difficulty=difficulty, seed=seed)
    assert state is not None

    puzzle = state.puzzle
    assert puzzle.solution_h is not None
    assert puzzle.solution_v is not None

    assert len(puzzle.clues) == puzzle.height
    assert all(len(row) == puzzle.width for row in puzzle.clues)
    assert len(puzzle.solution_h) == puzzle.height + 1
    assert all(len(row) == puzzle.width for row in puzzle.solution_h)
    assert len(puzzle.solution_v) == puzzle.height
    assert all(len(row) == puzzle.width + 1 for row in puzzle.solution_v)

    for row in range(puzzle.height):
        for col in range(puzzle.width):
            clue = puzzle.clues[row][col]
            if clue is None:
                continue
            count = (
                int(puzzle.solution_h[row][col])
                + int(puzzle.solution_h[row + 1][col])
                + int(puzzle.solution_v[row][col])
                + int(puzzle.solution_v[row][col + 1])
            )
            assert clue == count
