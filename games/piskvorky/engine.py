"""
Piškvorky / Gomoku Game Engine - Optimized Version

Game Modes:
- 3×3 board: Need 3 in a row (classic Tic-Tac-Toe)
- 8×8 board: Need 4 in a row  
- 13×13 board: Need 5 in a row (Gomoku)

Optimizations:
- Incremental line sum updates for O(1) win detection
- Pre-computed cell-to-line mappings
- Fast threat detection
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Set


Line = List[int]
Coords = List[Tuple[int, int]]


# Game mode configurations: board_size -> win_length
GAME_MODES = {
    3: 3,   # 3×3, need 3 in a row
    8: 4,   # 8×8, need 4 in a row
    13: 5,  # 13×13, need 5 in a row
}


def get_win_length(n: int) -> int:
    """Get required consecutive pieces to win for given board size."""
    if n in GAME_MODES:
        return GAME_MODES[n]
    # Fallback
    if n <= 3:
        return 3
    elif n <= 8:
        return 4
    else:
        return 5


def generate_all_lines(n: int, win_len: int) -> List[Line]:
    """
    Generate ALL possible winning lines of length win_len on n×n board.
    Uses sliding window approach.
    """
    lines: List[Line] = []
    
    # Horizontal lines
    for r in range(n):
        for start_c in range(n - win_len + 1):
            line = [r * n + (start_c + i) for i in range(win_len)]
            lines.append(line)
    
    # Vertical lines
    for c in range(n):
        for start_r in range(n - win_len + 1):
            line = [(start_r + i) * n + c for i in range(win_len)]
            lines.append(line)
    
    # Diagonal lines (top-left to bottom-right)
    for start_r in range(n - win_len + 1):
        for start_c in range(n - win_len + 1):
            line = [(start_r + i) * n + (start_c + i) for i in range(win_len)]
            lines.append(line)
    
    # Anti-diagonal lines (top-right to bottom-left)
    for start_r in range(n - win_len + 1):
        for start_c in range(win_len - 1, n):
            line = [(start_r + i) * n + (start_c - i) for i in range(win_len)]
            lines.append(line)
    
    return lines


# Cache lines per board configuration
_LINES_CACHE: dict = {}


def get_cached_lines(n: int, win_len: int) -> List[Line]:
    """Get or create cached lines for board config."""
    key = (n, win_len)
    if key not in _LINES_CACHE:
        _LINES_CACHE[key] = generate_all_lines(n, win_len)
    return _LINES_CACHE[key]


def line_to_coords(n: int, line: Line) -> Coords:
    """Convert line indices to (row, col) coordinates."""
    return [(idx // n, idx % n) for idx in line]


# Pre-compute which lines pass through each cell
_CELL_LINES_CACHE: dict = {}


def get_cell_lines(n: int, win_len: int) -> List[List[int]]:
    """Get list of line indices that pass through each cell."""
    key = (n, win_len)
    if key not in _CELL_LINES_CACHE:
        lines = get_cached_lines(n, win_len)
        cell_lines = [[] for _ in range(n * n)]
        for line_idx, line in enumerate(lines):
            for cell in line:
                cell_lines[cell].append(line_idx)
        _CELL_LINES_CACHE[key] = cell_lines
    return _CELL_LINES_CACHE[key]


@dataclass
class GameState:
    """Represents the current state of a Piškvorky/Gomoku game."""
    n: int              # Board size
    win_len: int        # How many in a row to win
    board: List[int]    # 0=empty, 1=X, -1=O
    to_move: int        # 1 or -1
    
    # Cached line sums for fast evaluation [sum of values in each line]
    _line_sums: Optional[List[int]] = field(default=None, repr=False)
    # Track blocked lines (lines with both X and O) for optimization
    _blocked_lines: Optional[Set[int]] = field(default=None, repr=False)

    @classmethod
    def new(cls, n: int, to_move: int = 1) -> "GameState":
        win_len = get_win_length(n)
        lines = get_cached_lines(n, win_len)
        return cls(
            n=n, 
            win_len=win_len, 
            board=[0] * (n * n), 
            to_move=to_move,
            _line_sums=[0] * len(lines),
            _blocked_lines=set()
        )

    def clone(self) -> "GameState":
        return GameState(
            n=self.n, 
            win_len=self.win_len, 
            board=self.board.copy(), 
            to_move=self.to_move,
            _line_sums=self._line_sums.copy() if self._line_sums else None,
            _blocked_lines=self._blocked_lines.copy() if self._blocked_lines else None
        )

    def get_lines(self) -> List[Line]:
        return get_cached_lines(self.n, self.win_len)

    def legal_moves(self) -> List[int]:
        return [i for i, v in enumerate(self.board) if v == 0]
    
    def smart_moves(self, radius: int = 2) -> List[int]:
        """Get moves near existing pieces (smarter for large boards)."""
        if self.move_count() == 0:
            # First move - center
            center = self.n // 2
            return [center * self.n + center]
        
        near_pieces: Set[int] = set()
        for idx, val in enumerate(self.board):
            if val != 0:
                r, c = idx // self.n, idx % self.n
                for dr in range(-radius, radius + 1):
                    for dc in range(-radius, radius + 1):
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < self.n and 0 <= nc < self.n:
                            ni = nr * self.n + nc
                            if self.board[ni] == 0:
                                near_pieces.add(ni)
        
        return list(near_pieces) if near_pieces else self.legal_moves()

    def apply(self, move: int) -> None:
        """Apply a move and update cached line sums."""
        if self.board[move] != 0:
            raise ValueError("Illegal move")
        
        player = self.to_move
        self.board[move] = player
        
        # Update line sums incrementally
        if self._line_sums is not None:
            cell_lines = get_cell_lines(self.n, self.win_len)
            lines = self.get_lines()
            for line_idx in cell_lines[move]:
                self._line_sums[line_idx] += player
                
                # Check if line becomes blocked
                if self._blocked_lines is not None:
                    line = lines[line_idx]
                    has_x = any(self.board[i] == 1 for i in line)
                    has_o = any(self.board[i] == -1 for i in line)
                    if has_x and has_o:
                        self._blocked_lines.add(line_idx)
        
        self.to_move *= -1

    def undo(self, move: int) -> None:
        """Undo a move (for search algorithms)."""
        if self.board[move] == 0:
            raise ValueError("Cell is already empty")
        
        # Switch turn back first (before accessing player)
        self.to_move *= -1
        player = self.board[move]
        self.board[move] = 0
        
        # Update line sums incrementally
        if self._line_sums is not None:
            cell_lines = get_cell_lines(self.n, self.win_len)
            lines = self.get_lines()
            for line_idx in cell_lines[move]:
                self._line_sums[line_idx] -= player
                
                # Re-check blocked status
                if self._blocked_lines is not None and line_idx in self._blocked_lines:
                    line = lines[line_idx]
                    has_x = any(self.board[i] == 1 for i in line)
                    has_o = any(self.board[i] == -1 for i in line)
                    if not (has_x and has_o):
                        self._blocked_lines.discard(line_idx)

    def is_full(self) -> bool:
        return all(v != 0 for v in self.board)

    def move_count(self) -> int:
        return sum(1 for v in self.board if v != 0)
    
    def get_line_sum(self, line_idx: int) -> int:
        """Get the sum of a line (fast with caching)."""
        if self._line_sums is not None:
            return self._line_sums[line_idx]
        lines = self.get_lines()
        return sum(self.board[i] for i in lines[line_idx])
    
    def is_line_blocked(self, line_idx: int) -> bool:
        """Check if a line is blocked (contains both X and O)."""
        if self._blocked_lines is not None:
            return line_idx in self._blocked_lines
        line = self.get_lines()[line_idx]
        has_x = any(self.board[i] == 1 for i in line)
        has_o = any(self.board[i] == -1 for i in line)
        return has_x and has_o


def check_winner(state: GameState) -> Tuple[Optional[int], Optional[Coords], bool]:
    """
    Check if game has ended using cached line sums.
    
    Returns:
        (winner, winning_coords, is_draw)
    """
    n = state.n
    win_len = state.win_len
    lines = state.get_lines()
    
    # Use cached line sums for fast check
    if state._line_sums is not None:
        for line_idx, total in enumerate(state._line_sums):
            if total == win_len:
                return 1, line_to_coords(n, lines[line_idx]), False
            if total == -win_len:
                return -1, line_to_coords(n, lines[line_idx]), False
    else:
        # Fallback to direct calculation
        b = state.board
        for line in lines:
            total = sum(b[i] for i in line)
            if total == win_len:
                return 1, line_to_coords(n, line), False
            if total == -win_len:
                return -1, line_to_coords(n, line), False
    
    if state.is_full():
        return None, None, True
    
    return None, None, False


def check_winner_fast(state: GameState) -> Optional[int]:
    """
    Fast winner check without coords (for AI search).
    Returns: 1, -1, or None
    """
    win_len = state.win_len
    
    if state._line_sums is not None:
        for total in state._line_sums:
            if total == win_len:
                return 1
            if total == -win_len:
                return -1
        return None
    
    # Fallback
    b = state.board
    for line in state.get_lines():
        total = sum(b[i] for i in line)
        if total == win_len:
            return 1
        if total == -win_len:
            return -1
    return None


def find_winning_move(state: GameState, player: int) -> Optional[int]:
    """
    Find a move that wins immediately for player.
    Optimized using line sums - only considers unblocked lines.
    """
    win_len = state.win_len
    b = state.board
    lines = state.get_lines()
    
    # Target sum: player needs win_len-1 of their pieces
    # A line with sum = player * (win_len - 1) has exactly win_len-1 player pieces
    # and no opponent pieces (because opponent would add ∓1 to the sum)
    target_sum = player * (win_len - 1)
    
    if state._line_sums is not None:
        for line_idx, line_sum in enumerate(state._line_sums):
            # Skip blocked lines
            if state._blocked_lines and line_idx in state._blocked_lines:
                continue
                
            if line_sum == target_sum:
                # This line has win_len-1 pieces of player and no opponent
                line = lines[line_idx]
                empty_cells = [i for i in line if b[i] == 0]
                if len(empty_cells) == 1:
                    return empty_cells[0]
    else:
        # Fallback without optimization
        for line in lines:
            my_count = sum(1 for i in line if b[i] == player)
            opp_count = sum(1 for i in line if b[i] == -player)
            empty_cells = [i for i in line if b[i] == 0]
            
            # Must have exactly win_len-1 pieces and NO opponent pieces
            if my_count == win_len - 1 and opp_count == 0 and len(empty_cells) == 1:
                return empty_cells[0]
    
    return None


def find_all_winning_moves(state: GameState, player: int) -> List[int]:
    """Find all moves that win immediately for player."""
    win_len = state.win_len
    b = state.board
    lines = state.get_lines()
    winning_moves: Set[int] = set()
    
    target_sum = player * (win_len - 1)
    
    if state._line_sums is not None:
        for line_idx, line_sum in enumerate(state._line_sums):
            if state._blocked_lines and line_idx in state._blocked_lines:
                continue
            if line_sum == target_sum:
                line = lines[line_idx]
                empty_cells = [i for i in line if b[i] == 0]
                if len(empty_cells) == 1:
                    winning_moves.add(empty_cells[0])
    
    return list(winning_moves)


def count_threats(state: GameState, player: int, level: int) -> List[int]:
    """
    Find cells that are part of threat lines at given level.
    level = how many pieces player has in line (e.g., win_len-2 for "almost winning")
    
    Returns list of empty cells in threat lines.
    """
    win_len = state.win_len
    b = state.board
    lines = state.get_lines()
    threat_moves: Set[int] = set()
    
    # Target: line with `level` player pieces, no opponent pieces
    target_sum = player * level
    
    if state._line_sums is not None:
        for line_idx, line_sum in enumerate(state._line_sums):
            if state._blocked_lines and line_idx in state._blocked_lines:
                continue
            if line_sum == target_sum:
                line = lines[line_idx]
                empty_cells = [i for i in line if b[i] == 0]
                if len(empty_cells) > 0:
                    threat_moves.update(empty_cells)
    else:
        for line in lines:
            my_count = sum(1 for i in line if b[i] == player)
            opp_count = sum(1 for i in line if b[i] == -player)
            empty_cells = [i for i in line if b[i] == 0]
            
            if opp_count == 0 and my_count == level and len(empty_cells) > 0:
                threat_moves.update(empty_cells)
    
    return list(threat_moves)


def find_fork_moves(state: GameState, player: int) -> List[int]:
    """
    Find moves that create a "fork" - multiple winning threats at once.
    These are devastating as opponent can only block one.
    """
    win_len = state.win_len
    b = state.board
    moves = state.smart_moves()
    fork_moves: List[int] = []
    
    for move in moves:
        if b[move] != 0:
            continue
            
        # Simulate the move
        state.board[move] = player
        
        # Update line sums temporarily
        cell_lines = get_cell_lines(state.n, win_len)
        if state._line_sums is not None:
            for line_idx in cell_lines[move]:
                state._line_sums[line_idx] += player
        
        # Count how many winning threats this creates
        threats = 0
        target_sum = player * (win_len - 1)
        lines = state.get_lines()
        
        if state._line_sums is not None:
            for line_idx in cell_lines[move]:
                if state._blocked_lines and line_idx in state._blocked_lines:
                    continue
                if state._line_sums[line_idx] == target_sum:
                    line = lines[line_idx]
                    empty_cells = [i for i in line if state.board[i] == 0]
                    if len(empty_cells) == 1:
                        threats += 1
        
        # Undo the simulation
        state.board[move] = 0
        if state._line_sums is not None:
            for line_idx in cell_lines[move]:
                state._line_sums[line_idx] -= player
        
        # Fork if 2+ threats
        if threats >= 2:
            fork_moves.append(move)
    
    return fork_moves


def is_draw_certain(state: GameState) -> bool:
    """Check if a draw is certain (all remaining lines are blocked)."""
    if state._blocked_lines is not None:
        lines = state.get_lines()
        return len(state._blocked_lines) == len(lines)
    
    # Fallback
    for line in state.get_lines():
        has_x = any(state.board[i] == 1 for i in line)
        has_o = any(state.board[i] == -1 for i in line)
        if not (has_x and has_o):
            return False  # This line can still be won
    return True
