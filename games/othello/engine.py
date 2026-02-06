"""
Othello (Reversi) game engine.

Rules:
- 8x8 board
- Enclose opponent disks in straight lines (8 directions) to flip them
- If a player has no legal move, they pass
- Game ends when both players cannot move or board is full
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


EMPTY = 0
BLACK = 1
WHITE = -1

BOARD_SIZE = 8

DIRECTIONS = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1),
]


def opponent(player: int) -> int:
    return -player


@dataclass(frozen=True)
class AISkillConfig:
    """Behavior profile for difficulty levels."""

    base_depth: int
    midgame_depth: int
    endgame_depth: int
    top_choice_count: int
    near_best_window: float
    random_pick_chance: float
    blunder_chance: float


AI_SKILL_CONFIGS: Dict[str, AISkillConfig] = {
    # Designed to be friendly for casual players: shallow search + frequent mistakes.
    "easy": AISkillConfig(
        base_depth=1,
        midgame_depth=1,
        endgame_depth=1,
        top_choice_count=6,
        near_best_window=21.6,
        random_pick_chance=1.0,
        blunder_chance=0.504,
    ),
    # Balanced mode for most players (intentionally ~20% weaker than previous tuning).
    "medium": AISkillConfig(
        base_depth=2,
        midgame_depth=2,
        endgame_depth=3,
        top_choice_count=3,
        near_best_window=4.8,
        random_pick_chance=0.36,
        blunder_chance=0.084,
    ),
    # Competitive mode.
    "hard": AISkillConfig(
        base_depth=4,
        midgame_depth=5,
        endgame_depth=6,
        top_choice_count=1,
        near_best_window=0.0,
        random_pick_chance=0.0,
        blunder_chance=0.0,
    ),
}


@dataclass
class OthelloGame:
    """State and logic for a single Othello game."""

    size: int = BOARD_SIZE
    board: List[List[int]] = field(default_factory=list)
    current_player: int = BLACK
    game_over: bool = False
    winner: int = EMPTY
    passes_in_row: int = 0
    move_count: int = 0

    def __post_init__(self) -> None:
        if not self.board:
            self.reset()

    def reset(self) -> None:
        """Reset game to initial position."""
        self.board = [[EMPTY for _ in range(self.size)] for _ in range(self.size)]
        c = self.size // 2
        self.board[c - 1][c - 1] = WHITE
        self.board[c][c] = WHITE
        self.board[c - 1][c] = BLACK
        self.board[c][c - 1] = BLACK

        self.current_player = BLACK
        self.game_over = False
        self.winner = EMPTY
        self.passes_in_row = 0
        self.move_count = 0

    def clone(self) -> "OthelloGame":
        """Return a deep copy suitable for search."""
        return OthelloGame(
            size=self.size,
            board=[row[:] for row in self.board],
            current_player=self.current_player,
            game_over=self.game_over,
            winner=self.winner,
            passes_in_row=self.passes_in_row,
            move_count=self.move_count,
        )

    def in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.size and 0 <= col < self.size

    def score(self) -> Tuple[int, int]:
        """Return (black_count, white_count)."""
        black = 0
        white = 0
        for r in range(self.size):
            for c in range(self.size):
                if self.board[r][c] == BLACK:
                    black += 1
                elif self.board[r][c] == WHITE:
                    white += 1
        return black, white

    def count_empty(self) -> int:
        return sum(1 for r in range(self.size) for c in range(self.size) if self.board[r][c] == EMPTY)

    def captures_for_move(self, row: int, col: int, player: Optional[int] = None) -> List[Tuple[int, int]]:
        """Return list of opponent coordinates that would be flipped by this move."""
        if player is None:
            player = self.current_player
        if not self.in_bounds(row, col) or self.board[row][col] != EMPTY:
            return []

        to_flip: List[Tuple[int, int]] = []
        opp = opponent(player)

        for dr, dc in DIRECTIONS:
            rr = row + dr
            cc = col + dc
            line: List[Tuple[int, int]] = []

            while self.in_bounds(rr, cc) and self.board[rr][cc] == opp:
                line.append((rr, cc))
                rr += dr
                cc += dc

            if line and self.in_bounds(rr, cc) and self.board[rr][cc] == player:
                to_flip.extend(line)

        return to_flip

    def valid_moves(self, player: Optional[int] = None) -> List[Tuple[int, int]]:
        """Return legal moves for player (or current player)."""
        if player is None:
            player = self.current_player
        if self.game_over:
            return []

        moves: List[Tuple[int, int]] = []
        for r in range(self.size):
            for c in range(self.size):
                if self.board[r][c] != EMPTY:
                    continue
                if self.captures_for_move(r, c, player):
                    moves.append((r, c))
        return moves

    def has_valid_move(self, player: Optional[int] = None) -> bool:
        return bool(self.valid_moves(player))

    def make_move(self, row: int, col: int) -> bool:
        """Apply move for current player. Returns True on success."""
        if self.game_over:
            return False

        flips = self.captures_for_move(row, col, self.current_player)
        if not flips:
            return False

        self.board[row][col] = self.current_player
        for rr, cc in flips:
            self.board[rr][cc] = self.current_player

        self.move_count += 1
        self.passes_in_row = 0
        self.current_player = opponent(self.current_player)

        if self.count_empty() == 0:
            self._finish_game()
            return True

        # Auto-pass if next player cannot move.
        if not self.has_valid_move(self.current_player):
            self.passes_in_row += 1
            self.current_player = opponent(self.current_player)
            if not self.has_valid_move(self.current_player):
                self.passes_in_row += 1
                self._finish_game()

        return True

    def pass_turn(self) -> bool:
        """Pass current turn if no legal move exists."""
        if self.game_over or self.has_valid_move(self.current_player):
            return False

        self.passes_in_row += 1
        self.current_player = opponent(self.current_player)

        if not self.has_valid_move(self.current_player):
            self.passes_in_row += 1
            self._finish_game()

        return True

    def _finish_game(self) -> None:
        """Mark game over and compute winner."""
        self.game_over = True
        black, white = self.score()
        if black > white:
            self.winner = BLACK
        elif white > black:
            self.winner = WHITE
        else:
            self.winner = EMPTY


class OthelloAI:
    """Minimax + alpha-beta AI."""

    def __init__(self, depth: Optional[int] = None, skill: str = "medium"):
        self.skill = skill if skill in AI_SKILL_CONFIGS else "medium"
        self._cfg = AI_SKILL_CONFIGS[self.skill]
        self.depth = max(1, depth if depth is not None else self._cfg.base_depth)

    def choose_move(self, game: OthelloGame, player: Optional[int] = None) -> Optional[Tuple[int, int]]:
        if player is None:
            player = game.current_player
        moves = game.valid_moves(player)
        if not moves:
            return None

        depth = self._resolve_depth(game.count_empty())

        alpha = float("-inf")
        beta = float("inf")
        scored_moves: List[Tuple[Tuple[int, int], float]] = []
        best_value = float("-inf")

        for move in self._order_moves(game, moves, player):
            g2 = game.clone()
            g2.current_player = player
            g2.make_move(*move)
            value = self._search(g2, depth - 1, player, alpha, beta)
            scored_moves.append((move, value))
            if value > best_value:
                best_value = value
            alpha = max(alpha, best_value)

        return self._pick_move(scored_moves)

    def _resolve_depth(self, empties: int) -> int:
        depth = self.depth
        if empties <= 14:
            return max(depth, self._cfg.endgame_depth)
        if empties <= 24:
            return max(depth, self._cfg.midgame_depth)
        return depth

    def _pick_move(self, scored_moves: List[Tuple[Tuple[int, int], float]]) -> Optional[Tuple[int, int]]:
        if not scored_moves:
            return None

        ranked = sorted(scored_moves, key=lambda item: item[1], reverse=True)
        if self.skill == "hard":
            return ranked[0][0]

        best_value = ranked[0][1]
        near_best = [item for item in ranked if item[1] >= best_value - self._cfg.near_best_window]
        if not near_best:
            near_best = ranked[:1]

        pool = near_best[:max(1, self._cfg.top_choice_count)]
        chosen = pool[0]

        if len(pool) > 1 and random.random() < self._cfg.random_pick_chance:
            chosen = random.choice(pool)

        if random.random() < self._cfg.blunder_chance and len(ranked) > 2:
            start = max(1, len(ranked) // 2)
            chosen = random.choice(ranked[start:])

        return chosen[0]

    def _search(self, game: OthelloGame, depth: int, maximizing_player: int, alpha: float, beta: float) -> float:
        if depth <= 0 or game.game_over:
            return self._evaluate(game, maximizing_player)

        moves = game.valid_moves(game.current_player)
        if not moves:
            g2 = game.clone()
            if not g2.pass_turn():
                return self._evaluate(g2, maximizing_player)
            return self._search(g2, depth - 1, maximizing_player, alpha, beta)

        maximizing = game.current_player == maximizing_player
        ordered = self._order_moves(game, moves, game.current_player)

        if maximizing:
            value = float("-inf")
            for move in ordered:
                g2 = game.clone()
                g2.make_move(*move)
                value = max(value, self._search(g2, depth - 1, maximizing_player, alpha, beta))
                alpha = max(alpha, value)
                if beta <= alpha:
                    break
            return value

        value = float("inf")
        for move in ordered:
            g2 = game.clone()
            g2.make_move(*move)
            value = min(value, self._search(g2, depth - 1, maximizing_player, alpha, beta))
            beta = min(beta, value)
            if beta <= alpha:
                break
        return value

    def _order_moves(self, game: OthelloGame, moves: List[Tuple[int, int]], player: int) -> List[Tuple[int, int]]:
        corners = {(0, 0), (0, 7), (7, 0), (7, 7)}
        bad_x = {(1, 1), (1, 6), (6, 1), (6, 6)}

        def key(move: Tuple[int, int]) -> float:
            r, c = move
            flips = len(game.captures_for_move(r, c, player))
            score = flips
            if (r, c) in corners:
                score += 100
            if (r, c) in bad_x:
                score -= 20
            if r in (0, 7) or c in (0, 7):
                score += 6
            return score

        return sorted(moves, key=key, reverse=True)

    def _evaluate(self, game: OthelloGame, player: int) -> float:
        opp = opponent(player)
        black, white = game.score()
        my_disks = black if player == BLACK else white
        opp_disks = white if player == BLACK else black

        # Disk parity
        parity = 0.0
        total = my_disks + opp_disks
        if total:
            parity = 100.0 * (my_disks - opp_disks) / total

        # Mobility
        my_moves = len(game.valid_moves(player))
        opp_moves = len(game.valid_moves(opp))
        mobility = 0.0
        if my_moves + opp_moves:
            mobility = 100.0 * (my_moves - opp_moves) / (my_moves + opp_moves)

        # Corner control
        corners = [(0, 0), (0, 7), (7, 0), (7, 7)]
        my_corners = sum(1 for r, c in corners if game.board[r][c] == player)
        opp_corners = sum(1 for r, c in corners if game.board[r][c] == opp)
        corner_score = 25.0 * (my_corners - opp_corners)

        # X-squares (danger next to empty corner)
        x_squares = {
            (0, 0): (1, 1),
            (0, 7): (1, 6),
            (7, 0): (6, 1),
            (7, 7): (6, 6),
        }
        x_penalty = 0.0
        for corner, x in x_squares.items():
            cr, cc = corner
            xr, xc = x
            if game.board[cr][cc] == EMPTY:
                if game.board[xr][xc] == player:
                    x_penalty -= 12.0
                elif game.board[xr][xc] == opp:
                    x_penalty += 12.0

        # Edge control
        edge_cells = []
        for i in range(1, 7):
            edge_cells.extend([(0, i), (7, i), (i, 0), (i, 7)])
        my_edges = sum(1 for r, c in edge_cells if game.board[r][c] == player)
        opp_edges = sum(1 for r, c in edge_cells if game.board[r][c] == opp)
        edge_score = 2.0 * (my_edges - opp_edges)

        empties = game.count_empty()
        if empties > 36:
            # Early game: mobility + corners matter most.
            return mobility * 2.4 + corner_score * 3.0 + x_penalty * 1.2 + edge_score * 0.8 + parity * 0.4
        if empties > 14:
            # Mid game: balanced.
            return mobility * 1.8 + corner_score * 3.2 + x_penalty * 1.4 + edge_score * 1.0 + parity * 1.0
        # Late game: disk parity gets stronger.
        return mobility * 1.2 + corner_score * 3.0 + x_penalty + edge_score + parity * 2.6


def create_game() -> OthelloGame:
    """Factory helper."""
    return OthelloGame()
